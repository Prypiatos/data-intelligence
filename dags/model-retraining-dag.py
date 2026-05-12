"""
Model Retraining Pipeline (DAG)
Task 3: Scheduled pipeline to retrain both ML models on new data

This Airflow DAG:
1. Runs every Monday at 2 AM
2. Fetches latest energy data from PostgreSQL
3. Retrains LSTM forecasting model  } in parallel
4. Retrains anomaly detection model }
5. Evaluates both models and promotes to production if metrics improve
6. Logs results to MLflow

Dependencies:
- Task #12: Load forecasting model baseline
- Task #15: MLflow experiment tracking
- Task #2: Feature engineering pipeline
"""

import logging
import os
from datetime import datetime, timedelta

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "energy_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "energy_pass")
POSTGRES_DB = os.getenv("POSTGRES_DB", "energy_db")

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
MLFLOW_FORECASTING_EXPERIMENT = "load-forecasting"
MLFLOW_ANOMALY_EXPERIMENT = "anomaly-detection"

LOOKBACK_DAYS = 30
TEST_SPLIT = 0.2
SEQ_LEN = 10  # must match lstm_model.py SEQ_LEN
PRED_LEN = 24
STEP = 1  # stride=1 here (small 90-day window); standalone trainer uses 2 for large RECON-SL

MODEL_PATH = "/opt/airflow/models/lstm_model.pth"
SCALER_PATH = "/opt/airflow/models/lstm_scaler.pkl"
ANOMALY_MODEL_PATH = "/opt/airflow/models/anomaly"


def fetch_training_data(**context):
    """Fetch energy_features and telemetry_readings from PostgreSQL."""
    logger.info("Task 1: Fetching Training Data")

    import pandas as pd
    from sqlalchemy import create_engine

    connection_string = (
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@"
        f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    engine = create_engine(connection_string)

    features_df = pd.read_sql(
        f"""
        SELECT *
        FROM energy_features
        WHERE timestamp >= EXTRACT(EPOCH FROM NOW() - INTERVAL '{LOOKBACK_DAYS} days') * 1000
        ORDER BY node_id, timestamp
        """,
        engine,
    )
    logger.info(f"Fetched {len(features_df):,} rows from energy_features")

    telemetry_df = pd.read_sql(
        f"""
        SELECT node_id, timestamp, voltage, current, power, energy_wh
        FROM telemetry_readings
        WHERE timestamp >= EXTRACT(EPOCH FROM NOW() - INTERVAL '{LOOKBACK_DAYS} days') * 1000
        ORDER BY timestamp
        """,
        engine,
    )
    logger.info(f"Fetched {len(telemetry_df):,} rows from telemetry_readings")

    features_path = "/opt/airflow/data/training_features.csv"
    telemetry_path = "/opt/airflow/data/training_telemetry.csv"
    features_df.to_csv(features_path, index=False)
    telemetry_df.to_csv(telemetry_path, index=False)

    ti = context["task_instance"]
    ti.xcom_push(key="features_path", value=features_path)
    ti.xcom_push(key="telemetry_path", value=telemetry_path)

    return {
        "status": "success",
        "feature_rows": len(features_df),
        "telemetry_rows": len(telemetry_df),
    }


def retrain_lstm_model(**context):
    """Retrain LSTM forecasting model, log to MLflow, register if better."""
    logger.info("Task 2: Retraining LSTM Model")

    import pickle
    import numpy as np
    import torch
    import mlflow
    import mlflow.pytorch
    import pandas as pd
    from pathlib import Path

    from src.models.forecasting.lstm_model import train_from_df, SEQ_LEN, PRED_LEN

    ti = context["task_instance"]
    features_path = ti.xcom_pull(task_ids="fetch_training_data", key="features_path")

    df = pd.read_csv(features_path).sort_values(["node_id", "timestamp"])

    # Per-node time-based split — last TEST_SPLIT fraction of each node held out
    train_parts, test_parts = [], []
    for _, grp in df.groupby("node_id"):
        split = int(len(grp) * (1 - TEST_SPLIT))
        train_parts.append(grp.iloc[:split])
        test_parts.append(grp.iloc[split:])

    df_train = pd.concat(train_parts).rename(columns={"avg_power": "power_w"})
    df_test = pd.concat(test_parts)

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_FORECASTING_EXPERIMENT)

    run_name = f"lstm_retrain_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_params(
            {
                "model_type": "LSTM",
                "epochs": 50,
                "seq_len": SEQ_LEN,
                "pred_len": PRED_LEN,
                "lookback_days": LOOKBACK_DAYS,
                "training_rows": len(df_train),
            }
        )

        model, scaler = train_from_df(df_train, epochs=50)

        # Evaluate on held-out test data, respecting node boundaries
        model.eval()
        device = next(model.parameters()).device
        all_preds, all_truths = [], []
        for _, grp in df_test.groupby("node_id"):
            vals = grp["avg_power"].values.astype(np.float32)
            if len(vals) < SEQ_LEN + PRED_LEN:
                continue
            for i in range(0, len(vals) - SEQ_LEN - PRED_LEN + 1, STEP):
                x_norm = scaler.transform(
                    vals[i : i + SEQ_LEN].reshape(-1, 1)
                ).flatten()
                y_norm = scaler.transform(
                    vals[i + SEQ_LEN : i + SEQ_LEN + PRED_LEN].reshape(-1, 1)
                ).flatten()
                X = torch.FloatTensor(x_norm).unsqueeze(0).unsqueeze(-1).to(device)
                with torch.no_grad():
                    pred = model(X).cpu().numpy().flatten()
                all_preds.append(pred)
                all_truths.append(y_norm)

        if all_preds:
            preds = np.array(all_preds)
            truths = np.array(all_truths)
            rmse = float(np.sqrt(np.mean((preds - truths) ** 2)))
            mape = float(np.mean(np.abs((truths - preds) / (np.abs(truths) + 1e-8))))
        else:
            rmse, mape = 0.0, 0.0

        mlflow.log_metrics({"test_rmse": rmse, "test_mape": mape})
        mlflow.pytorch.log_model(model, "lstm_model")
        logger.info(f"LSTM — RMSE: {rmse:.4f}, MAPE: {mape:.4f}")

        Path(MODEL_PATH).parent.mkdir(parents=True, exist_ok=True)
        torch.save(model, MODEL_PATH)
        with open(SCALER_PATH, "wb") as f:
            pickle.dump(scaler, f)
        logger.info("Saved model → %s, scaler → %s", MODEL_PATH, SCALER_PATH)

        ti.xcom_push(key="lstm_metrics", value={"rmse": rmse, "mape": mape})
        ti.xcom_push(key="lstm_run_id", value=run.info.run_id)

    return {"status": "success", "rmse": rmse, "mape": mape}


def retrain_anomaly_model(**context):
    """Retrain IsolationForest anomaly detector on latest telemetry, log to MLflow."""
    logger.info("Task 3: Retraining Anomaly Detection Model")

    import pandas as pd
    import mlflow

    from src.models.anomaly.model import AnomalyDetector
    from src.models.anomaly.trainer import _compute_metrics

    ti = context["task_instance"]
    telemetry_path = ti.xcom_pull(task_ids="fetch_training_data", key="telemetry_path")

    df = pd.read_csv(telemetry_path)
    readings = df.to_dict(orient="records")
    logger.info(f"Training anomaly detector on {len(readings):,} readings")

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_ANOMALY_EXPERIMENT)

    run_name = f"anomaly_retrain_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    with mlflow.start_run(run_name=run_name) as run:
        contamination = float(os.getenv("ANOMALY_CONTAMINATION", "0.01"))
        detector = AnomalyDetector(contamination=contamination, n_estimators=100)
        detector.fit(readings)

        mlflow.log_params(
            {
                **detector.params,
                "n_readings": len(readings),
                "lookback_days": LOOKBACK_DAYS,
            }
        )

        predictions = detector.predict(readings)
        metrics = _compute_metrics(predictions)
        mlflow.log_metrics(metrics)

        # Save to the path the anomaly pipeline reads from
        detector.save(ANOMALY_MODEL_PATH)
        mlflow.log_artifact(f"{ANOMALY_MODEL_PATH}/detector.pkl", artifact_path="model")
        logger.info("Saved anomaly model → %s", ANOMALY_MODEL_PATH)

        logger.info(
            f"Anomaly — anomaly_rate: {metrics['anomaly_rate']:.4f}, mean_score: {metrics['mean_score']:.4f}"
        )

        ti.xcom_push(key="anomaly_metrics", value=metrics)
        ti.xcom_push(key="anomaly_run_id", value=run.info.run_id)

    return {"status": "success", **metrics}


def evaluate_and_promote(**context):
    """Compare new models against previous best and promote to production if improved."""
    logger.info("Task 4: Evaluate and Promote Models")

    import mlflow
    from mlflow.tracking import MlflowClient

    ti = context["task_instance"]
    lstm_metrics = ti.xcom_pull(task_ids="retrain_lstm_model", key="lstm_metrics")
    lstm_run_id = ti.xcom_pull(task_ids="retrain_lstm_model", key="lstm_run_id")
    anomaly_metrics = ti.xcom_pull(
        task_ids="retrain_anomaly_model", key="anomaly_metrics"
    )
    anomaly_run_id = ti.xcom_pull(
        task_ids="retrain_anomaly_model", key="anomaly_run_id"
    )

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()

    # --- LSTM promotion ---
    lstm_promoted = False
    experiment = mlflow.get_experiment_by_name(MLFLOW_FORECASTING_EXPERIMENT)
    if experiment:
        runs = mlflow.search_runs(
            experiment_ids=[experiment.experiment_id],
            order_by=["metrics.test_mape ASC"],
            max_results=10,
        )
        # Current run is row 0 (best MAPE); compare against row 1 (previous best)
        if len(runs) > 1 and lstm_metrics["mape"] < runs.iloc[1]["metrics.test_mape"]:
            mv = mlflow.register_model(
                f"runs:/{lstm_run_id}/lstm_model", "LSTMForecaster"
            )
            client.set_registered_model_alias(
                "LSTMForecaster", "production", mv.version
            )
            lstm_promoted = True
            logger.info(
                f"LSTM promoted to production (version {mv.version}, MAPE {lstm_metrics['mape']:.4f})"
            )
        else:
            logger.info(
                f"LSTM not promoted — MAPE {lstm_metrics['mape']:.4f} did not improve"
            )

    # --- Anomaly promotion ---
    anomaly_promoted = False
    anomaly_exp = mlflow.get_experiment_by_name(MLFLOW_ANOMALY_EXPERIMENT)
    if anomaly_exp:
        runs = mlflow.search_runs(
            experiment_ids=[anomaly_exp.experiment_id],
            order_by=["metrics.anomaly_rate ASC"],
            max_results=10,
        )
        if (
            len(runs) > 1
            and anomaly_metrics["anomaly_rate"] < runs.iloc[1]["metrics.anomaly_rate"]
        ):
            mv = mlflow.register_model(
                f"runs:/{anomaly_run_id}/model/detector.pkl", "AnomalyDetector"
            )
            client.set_registered_model_alias(
                "AnomalyDetector", "production", mv.version
            )
            anomaly_promoted = True
            logger.info(
                f"Anomaly detector promoted to production (version {mv.version})"
            )
        else:
            logger.info(
                f"Anomaly detector not promoted — rate {anomaly_metrics['anomaly_rate']:.4f} did not improve"
            )

    return {
        "status": "success",
        "lstm_promoted": lstm_promoted,
        "anomaly_promoted": anomaly_promoted,
    }


default_args = {
    "owner": "E2_Data_Intelligence",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "start_date": pendulum.datetime(2025, 1, 1, tz="UTC"),
    "email_on_failure": False,
    "email_on_retry": False,
}

dag = DAG(
    "model_retraining_pipeline",
    default_args=default_args,
    description="Retrain LSTM forecasting and anomaly detection models weekly",
    schedule="0 2 * * 1",
    catchup=False,
    tags=["E2", "ML", "retraining"],
)

fetch_data_task = PythonOperator(
    task_id="fetch_training_data",
    python_callable=fetch_training_data,
    dag=dag,
)

retrain_lstm_task = PythonOperator(
    task_id="retrain_lstm_model",
    python_callable=retrain_lstm_model,
    dag=dag,
)

retrain_anomaly_task = PythonOperator(
    task_id="retrain_anomaly_model",
    python_callable=retrain_anomaly_model,
    dag=dag,
)

evaluate_task = PythonOperator(
    task_id="evaluate_and_promote",
    python_callable=evaluate_and_promote,
    dag=dag,
)

cleanup_task = BashOperator(
    task_id="cleanup",
    bash_command="rm -f /opt/airflow/data/training_features.csv /opt/airflow/data/training_telemetry.csv",
    dag=dag,
)

# fetch → [lstm, anomaly in parallel] → evaluate → cleanup
(
    fetch_data_task
    >> [retrain_lstm_task, retrain_anomaly_task]
    >> evaluate_task
    >> cleanup_task
)
