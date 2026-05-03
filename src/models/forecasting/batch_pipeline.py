import os
import logging
import torch
import pandas as pd
import numpy as np
from datetime import datetime
from sqlalchemy import create_engine
import mlflow
import mlflow.pytorch
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "energy_db")

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")

MODEL_PATH = "models/lstm_model.pth"
FORECAST_HORIZON = 24  # 24-hour forecast


class LSTMForecastingModel:
    """LSTM model wrapper for forecasting"""

    def __init__(self, model_path):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = torch.load(model_path, map_location=self.device)
        self.model.eval()
        logger.info(f"✅ Loaded model from {model_path}")

    def predict(self, features_sequence):
        """
        Generate forecast from features sequence

        Args:
            features_sequence: numpy array of shape (1, seq_len, num_features)

        Returns:
            predictions: numpy array of forecasted values
        """
        with torch.no_grad():
            X = torch.FloatTensor(features_sequence).to(self.device)
            predictions = self.model(X)
            return predictions.cpu().numpy()


def get_postgres_connection():
    """Create PostgreSQL connection"""
    connection_string = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    engine = create_engine(connection_string)
    logger.info("✅ Connected to PostgreSQL")
    return engine


def fetch_latest_features(engine, lookback_hours=168):
    """
    Fetch latest energy features from PostgreSQL

    Args:
        engine: SQLAlchemy engine
        lookback_hours: How many hours of history to fetch

    Returns:
        DataFrame with features grouped by node_id
    """
    query = f"""
    SELECT 
        node_id,
        timestamp,
        avg_power,
        avg_voltage,
        avg_current,
        min_power,
        max_power,
        std_power,
        avg_energy_wh,
        reading_count,
        hour,
        day_of_week,
        day_of_month,
        lag_1h,
        lag_24h,
        lag_168h,
        rolling_avg_1d,
        rolling_avg_7d,
        rolling_avg_30d,
        rolling_min_24h,
        rolling_max_24h,
        rolling_std_24h
    FROM energy_features
    WHERE timestamp >= (EXTRACT(EPOCH FROM NOW()) - {lookback_hours * 3600}) * 1000
    ORDER BY node_id, timestamp DESC
    """

    df = pd.read_sql(query, engine)
    logger.info(
        f"✅ Fetched {len(df)} feature rows from {df['node_id'].nunique()} nodes"
    )

    return df


def prepare_forecast_input(features_df, seq_len=24):
    """
    Prepare input sequences for LSTM prediction

    Args:
        features_df: DataFrame with features
        seq_len: Sequence length for LSTM

    Returns:
        dict: {node_id: input_array}
    """
    node_sequences = {}

    for node_id in features_df["node_id"].unique():
        node_data = features_df[features_df["node_id"] == node_id].sort_values(
            "timestamp"
        )

        if len(node_data) < seq_len:
            logger.warning(
                f"⚠️  Node {node_id} has insufficient data ({len(node_data)} < {seq_len})"
            )
            continue

        # Select feature columns (exclude timestamp and node_id)
        feature_cols = [
            "avg_power",
            "avg_voltage",
            "avg_current",
            "min_power",
            "max_power",
            "std_power",
            "avg_energy_wh",
            "reading_count",
            "hour",
            "day_of_week",
            "day_of_month",
            "lag_1h",
            "lag_24h",
            "lag_168h",
            "rolling_avg_1d",
            "rolling_avg_7d",
            "rolling_avg_30d",
            "rolling_min_24h",
            "rolling_max_24h",
            "rolling_std_24h",
        ]

        # Get latest seq_len rows
        sequence = node_data[feature_cols].tail(seq_len).values

        # Normalize if needed (optional - depends on model training)
        node_sequences[node_id] = np.expand_dims(
            sequence, axis=0
        )  # Add batch dimension

    logger.info(f"✅ Prepared sequences for {len(node_sequences)} nodes")
    return node_sequences


def generate_forecasts(model, node_sequences):
    """
    Generate 24-hour forecasts for all nodes

    Args:
        model: LSTMForecastingModel instance
        node_sequences: dict of {node_id: input_array}

    Returns:
        DataFrame with forecasts
    """
    forecasts = []
    current_timestamp = int(datetime.now().timestamp() * 1000)  # BIGINT milliseconds

    for node_id, sequence in node_sequences.items():
        try:
            # Generate predictions
            predictions = model.predict(sequence)

            # Flatten predictions to 1D
            predictions = predictions.flatten()[:FORECAST_HORIZON]

            # Create forecast rows
            for hour_offset in range(len(predictions)):
                forecast_timestamp = current_timestamp + (hour_offset * 3600 * 1000)

                forecasts.append(
                    {
                        "node_id": node_id,
                        "timestamp": forecast_timestamp,
                        "predicted_consumption": float(predictions[hour_offset]),
                    }
                )

        except Exception as e:
            logger.error(f"❌ Error generating forecast for {node_id}: {str(e)}")
            continue

    df_forecasts = pd.DataFrame(forecasts)
    logger.info(f"✅ Generated {len(df_forecasts)} forecast rows")

    return df_forecasts


def write_forecasts_to_db(engine, df_forecasts):
    """
    Write predictions to PostgreSQL forecasts table

    Args:
        engine: SQLAlchemy engine
        df_forecasts: DataFrame with predictions
    """
    try:
        df_forecasts.to_sql("forecasts", engine, if_exists="append", index=False)
        logger.info(f"✅ Written {len(df_forecasts)} forecast rows to PostgreSQL")

    except Exception as e:
        logger.error(f"❌ Error writing forecasts: {str(e)}")
        raise


def log_to_mlflow(model_path, num_predictions, forecast_horizon):
    """
    Log batch pipeline run to MLflow

    Args:
        model_path: Path to trained model
        num_predictions: Number of predictions generated
        forecast_horizon: Forecast horizon (hours)
    """
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("batch-forecasting")

    with mlflow.start_run():
        mlflow.log_param("model_path", model_path)
        mlflow.log_param("forecast_horizon", forecast_horizon)
        mlflow.log_metric("num_predictions", num_predictions)
        mlflow.log_metric("timestamp", int(datetime.now().timestamp()))

        mlflow.log_artifact(model_path, artifact_path="model")

        logger.info("✅ Logged batch pipeline run to MLflow")


def run_batch_pipeline():
    """
    Main batch forecasting pipeline
    """
    logger.info("=" * 80)
    logger.info("Starting Batch Forecasting Pipeline")
    logger.info("=" * 80)

    try:
        # 1. Load model
        logger.info("Step 1: Loading trained LSTM model...")
        model = LSTMForecastingModel(MODEL_PATH)

        # 2. Connect to PostgreSQL
        logger.info("Step 2: Connecting to PostgreSQL...")
        engine = get_postgres_connection()

        # 3. Fetch latest features
        logger.info("Step 3: Fetching latest energy features...")
        df_features = fetch_latest_features(engine, lookback_hours=168)

        if df_features.empty:
            logger.error("❌ No features found in database!")
            return False

        # 4. Prepare input sequences
        logger.info("Step 4: Preparing input sequences for LSTM...")
        node_sequences = prepare_forecast_input(df_features, seq_len=24)

        if not node_sequences:
            logger.error("❌ No valid sequences prepared!")
            return False

        # 5. Generate forecasts
        logger.info("Step 5: Generating 24-hour forecasts...")
        df_forecasts = generate_forecasts(model, node_sequences)

        if df_forecasts.empty:
            logger.error("❌ No forecasts generated!")
            return False

        # 6. Write to database
        logger.info("Step 6: Writing forecasts to PostgreSQL...")
        write_forecasts_to_db(engine, df_forecasts)

        # 7. Log to MLflow
        logger.info("Step 7: Logging to MLflow...")
        log_to_mlflow(MODEL_PATH, len(df_forecasts), FORECAST_HORIZON)

        logger.info("=" * 80)
        logger.info("✅ Batch Forecasting Pipeline Completed Successfully!")
        logger.info(
            f"   Generated {len(df_forecasts)} forecasts across {len(node_sequences)} nodes"
        )
        logger.info("=" * 80)

        return True

    except Exception as e:
        logger.error(f"❌ Pipeline failed: {str(e)}")
        logger.error("=" * 80)
        return False


if __name__ == "__main__":
    success = run_batch_pipeline()
    exit(0 if success else 1)
