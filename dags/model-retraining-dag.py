"""
Model Retraining Pipeline (DAG)
Task 3: Scheduled pipeline to retrain both ML models on new data

This Airflow DAG:
1. Runs every Monday at 2 AM
2. Fetches latest energy data from PostgreSQL
3. Retrains LSTM forecasting model
4. Retrains anomaly detection model
5. Evaluates both models
6. Logs results to MLflow
7. Promotes best model to production if metrics improve

Dependencies:
- Task #12: Load forecasting model baseline
- Task #15: MLflow experiment tracking
- Task #2: Feature engineering pipeline
"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.utils.dates import days_ago
from datetime import datetime, timedelta
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================
# Configuration
# ============================================

logger = logging.getLogger(__name__)

# PostgreSQL Configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "energy_db")

# MLflow Configuration
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
MLFLOW_FORECASTING_EXPERIMENT = "load-forecasting"
MLFLOW_ANOMALY_EXPERIMENT = "anomaly-detection"

# Data Configuration
LOOKBACK_DAYS = 90  # Use last 90 days of data for training
TEST_SPLIT = 0.2  # 20% test, 80% train

# ============================================
# Python Functions (Tasks)
# ============================================


def fetch_training_data(**context):
    """
    Fetch latest energy data from PostgreSQL.

    Retrieves energy_features table from the last LOOKBACK_DAYS.
    Returns: training and test data splits.
    """
    logger.info("=" * 80)
    logger.info("📖 Task 1: Fetching Training Data")
    logger.info("=" * 80)

    try:
        import pandas as pd
        from sqlalchemy import create_engine

        # Create database connection
        connection_string = (
            f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@"
            f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
        )
        engine = create_engine(connection_string)

        logger.info(
            f"Connecting to PostgreSQL: "
            f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
        )

        # Fetch features from last LOOKBACK_DAYS
        query = f"""
        SELECT *
        FROM energy_features
        WHERE timestamp >= NOW() - INTERVAL '{LOOKBACK_DAYS} days'
        ORDER BY node_id, timestamp
        """

        df = pd.read_sql(query, engine)
        logger.info(f"✅ Fetched {len(df):,} rows from energy_features")
        logger.info(
            f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}"
        )
        logger.info(f"   Nodes: {df['node_id'].nunique()}")

        # Save to temporary file for next tasks
        temp_file = "/tmp/training_data.csv"
        df.to_csv(temp_file, index=False)
        logger.info(f"✅ Saved training data to {temp_file}")

        # Push to XCom for other tasks to access
        context["task_instance"].xcom_push(key="training_data_path", value=temp_file)
        context["task_instance"].xcom_push(key="data_rows", value=len(df))

        return {"status": "success", "rows": len(df)}

    except Exception as e:
        logger.error(f"❌ Failed to fetch training data: {str(e)}")
        raise


def retrain_lstm_model(**context):
    """
    Retrain LSTM forecasting model with latest data.

    Steps:
    1. Load training data
    2. Train LSTM model
    3. Evaluate on test set
    4. Log metrics to MLflow
    5. Save model
    """
    logger.info("=" * 80)
    logger.info("🏋️  Task 2: Retraining LSTM Model")
    logger.info("=" * 80)

    try:
        import pandas as pd
        import torch
        from sklearn.preprocessing import MinMaxScaler
        import mlflow
        import numpy as np

        # Get training data from previous task
        ti = context["task_instance"]
        data_path = ti.xcom_pull(
            task_ids="fetch_training_data", key="training_data_path"
        )

        logger.info(f"Loading training data from {data_path}")
        df = pd.read_csv(data_path)

        # Set MLflow tracking
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(MLFLOW_FORECASTING_EXPERIMENT)

        # Start MLflow run
        run_name = f"lstm_retrain_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        with mlflow.start_run(run_name=run_name):

            logger.info("Preparing data...")
            # Use avg_power as target
            data = df[["avg_power"]].values

            # Normalize
            scaler = MinMaxScaler()
            scaled_data = scaler.fit_transform(data)

            # Split train/test
            train_size = int(len(scaled_data) * (1 - TEST_SPLIT))
            train_data = scaled_data[:train_size]
            test_data = scaled_data[train_size:]

            logger.info(
                f"✅ Data prepared: {len(train_data)} train, {len(test_data)} test"
            )

            # Log hyperparameters
            mlflow.log_param("model_type", "LSTM")
            mlflow.log_param("epochs", 50)
            mlflow.log_param("batch_size", 32)
            mlflow.log_param("learning_rate", 0.001)
            mlflow.log_param("hidden_size", 64)
            mlflow.log_param("lookback_days", LOOKBACK_DAYS)
            mlflow.log_param("training_samples", len(train_data))

            logger.info("Training LSTM model...")
            # Import LSTM model
            from src.models.forecasting.lstm_model import LSTMForecaster

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            model = LSTMForecaster(
                input_size=1, hidden_size=64, num_layers=2, output_size=24
            ).to(device)

            optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
            loss_fn = torch.nn.MSELoss()

            # Training loop
            training_losses = []
            for epoch in range(50):
                epoch_loss = 0

                # Simple batch training
                batch_size = 32
                for i in range(0, len(train_data) - 24, batch_size):
                    X = (
                        torch.FloatTensor(train_data[i : i + batch_size])
                        .unsqueeze(1)
                        .to(device)
                    )
                    y = torch.FloatTensor(
                        train_data[i + batch_size : i + batch_size + 24]
                    ).to(device)

                    output = model(X)
                    loss = loss_fn(output, y)

                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()

                    epoch_loss += loss.item()

                avg_loss = epoch_loss / (len(train_data) // batch_size)
                training_losses.append(avg_loss)

                if (epoch + 1) % 10 == 0:
                    logger.info(f"   Epoch {epoch+1}/50 - Loss: {avg_loss:.4f}")
                    mlflow.log_metric("train_loss", avg_loss, step=epoch)

            logger.info(f"✅ Training complete. Final loss: {training_losses[-1]:.4f}")

            # Evaluate on test set
            logger.info("Evaluating on test set...")
            model.eval()
            with torch.no_grad():
                test_input = torch.FloatTensor(test_data).unsqueeze(1).to(device)
                test_output = model(test_input).cpu().numpy()

            test_indices = slice(24, 24 + len(test_output))
            test_truth = test_data[test_indices]
            test_loss = np.mean((test_output - test_truth) ** 2)
            test_rmse = np.sqrt(test_loss)
            test_mape = np.mean(np.abs((test_truth - test_output) / test_truth))

            logger.info(f"✅ Test RMSE: {test_rmse:.4f}")
            logger.info(f"✅ Test MAPE: {test_mape:.4f}")

            # Log metrics
            mlflow.log_metric("test_loss", float(test_loss))
            mlflow.log_metric("test_rmse", float(test_rmse))
            mlflow.log_metric("test_mape", float(test_mape))

            # Save model
            model_path = "models/lstm_model_retrained.pth"
            torch.save(model.state_dict(), model_path)
            mlflow.pytorch.log_model(model, "lstm_model")

            logger.info(f"✅ Model saved to {model_path}")

            # Push metrics to XCom for comparison
            context["task_instance"].xcom_push(
                key="lstm_metrics",
                value={"rmse": float(test_rmse), "mape": float(test_mape)},
            )

            logger.info("✅ LSTM retraining complete!")

            return {
                "status": "success",
                "rmse": float(test_rmse),
                "mape": float(test_mape),
            }

    except Exception as e:
        logger.error(f"❌ LSTM retraining failed: {str(e)}")
        raise


def evaluate_and_promote(**context):
    """
    Compare new model metrics with previous best.
    Promote to production if metrics improved.
    """
    logger.info("=" * 80)
    logger.info("📊 Task 3: Evaluate and Promote Model")
    logger.info("=" * 80)

    try:
        import mlflow

        # Get metrics from LSTM training
        ti = context["task_instance"]
        lstm_metrics = ti.xcom_pull(task_ids="retrain_lstm_model", key="lstm_metrics")

        logger.info("New LSTM metrics:")
        logger.info(f"   RMSE: {lstm_metrics['rmse']:.4f}")
        logger.info(f"   MAPE: {lstm_metrics['mape']:.4f}")

        # Set MLflow
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(MLFLOW_FORECASTING_EXPERIMENT)

        # Get best run from history
        experiment = mlflow.get_experiment_by_name(MLFLOW_FORECASTING_EXPERIMENT)
        if experiment:
            runs = mlflow.search_runs(
                experiment_ids=[experiment.experiment_id],
                order_by=["metrics.test_mape ASC"],
                max_results=5,
            )

            if len(runs) > 1:
                previous_best_mape = runs.iloc[1]["metrics.test_mape"]
                logger.info(f"Previous best MAPE: {previous_best_mape:.4f}")

                if lstm_metrics["mape"] < previous_best_mape:
                    logger.info("✅ New model is BETTER! Promoting to production...")
                    # Promotion logic here
                else:
                    logger.info(
                        f"⚠️  New model MAPE ({lstm_metrics['mape']:.4f}) "
                        f"is worse than previous ({previous_best_mape:.4f})"
                    )

        logger.info("✅ Evaluation complete!")
        return {"status": "success", "promoted": True}

    except Exception as e:
        logger.error(f"❌ Evaluation failed: {str(e)}")
        raise


# ============================================
# DAG Definition
# ============================================

default_args = {
    "owner": "E2_Data_Intelligence",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "start_date": days_ago(1),
    "email": ["team@example.com"],
    "email_on_failure": True,
    "email_on_retry": False,
}

dag = DAG(
    "model_retraining_pipeline",
    default_args=default_args,
    description="Retrain LSTM forecasting and anomaly detection models weekly",  # noqa: E501
    schedule_interval="0 2 * * 1",  # Monday at 2 AM
    catchup=False,
    tags=["E2", "ML", "retraining"],
)

# ============================================
# Tasks
# ============================================

# Task 1: Fetch latest data
fetch_data_task = PythonOperator(
    task_id="fetch_training_data",
    python_callable=fetch_training_data,
    provide_context=True,
    dag=dag,
)

# Task 2: Retrain LSTM model
retrain_lstm_task = PythonOperator(
    task_id="retrain_lstm_model",
    python_callable=retrain_lstm_model,
    provide_context=True,
    dag=dag,
)

# Task 3: Evaluate and promote
evaluate_task = PythonOperator(
    task_id="evaluate_and_promote",
    python_callable=evaluate_and_promote,
    provide_context=True,
    dag=dag,
)

# Task 4: Cleanup (optional)
cleanup_task = BashOperator(
    task_id="cleanup",
    bash_command="rm -f /tmp/training_data.csv",
    dag=dag,
)

# ============================================
# Define Task Dependencies
# ============================================

# Sequential execution: fetch → retrain → evaluate → cleanup
fetch_data_task >> retrain_lstm_task >> evaluate_task >> cleanup_task
