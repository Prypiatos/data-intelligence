import os
import pickle
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sqlalchemy import create_engine
import mlflow
import mlflow.pytorch
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "energy_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "energy_pass")
POSTGRES_DB = os.getenv("POSTGRES_DB", "energy_db")

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")

MODEL_PATH = os.getenv("MODEL_PATH", "models/lstm_model.pth")
SCALER_PATH = os.getenv("SCALER_PATH", "models/lstm_scaler.pkl")
FORECAST_HORIZON = 24
SEQ_LEN = 10
FORECAST_COLD_START_DAYS = int(os.getenv("FORECAST_COLD_START_DAYS", "30"))


class LSTMForecastingModel:
    def __init__(self, model_path: str, scaler_path: str):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = torch.load(
            model_path, map_location=self.device, weights_only=False
        )
        self.model.eval()
        with open(scaler_path, "rb") as f:
            self.scaler = pickle.load(f)
        logger.info("Loaded model from %s", model_path)

    def predict(self, power_sequence: np.ndarray) -> np.ndarray:
        """
        Args:
            power_sequence: 1-D array of SEQ_LEN hourly power readings in watts
        Returns:
            1-D array of FORECAST_HORIZON denormalized watt predictions
        """
        normalized = self.scaler.transform(power_sequence.reshape(-1, 1))
        X = (
            torch.FloatTensor(normalized).unsqueeze(0).to(self.device)
        )  # (1, seq_len, 1)
        with torch.no_grad():
            output = self.model(X)
        forecast = self.scaler.inverse_transform(
            output.cpu().numpy()[0].reshape(-1, 1)
        ).flatten()
        return np.maximum(forecast, 0)


def _try_cold_start(engine) -> bool:
    """Train LSTM from energy_features when FORECAST_COLD_START_DAYS of data exists.
    Saves model and scaler to disk. Returns True if training succeeded.
    """
    from src.models.forecasting.lstm_model import (
        SEQ_LEN as _SEQ,
        PRED_LEN as _PRED,
        train_from_df,
    )

    df = pd.read_sql(
        "SELECT node_id, timestamp, avg_power FROM energy_features WHERE avg_power IS NOT NULL ORDER BY node_id, timestamp",
        engine,
    )
    if df.empty:
        logger.info("Cold start: no energy_features data yet")
        return False

    span_days = (df["timestamp"].max() - df["timestamp"].min()) / (24 * 3600 * 1000)
    if span_days < FORECAST_COLD_START_DAYS:
        logger.info(
            "Cold start: need %d days, have %.1f — waiting",
            FORECAST_COLD_START_DAYS,
            span_days,
        )
        return False

    min_rows = _SEQ + _PRED
    if (df.groupby("node_id").size() >= min_rows).sum() == 0:
        logger.info("Cold start: no node has %d hourly rows yet", min_rows)
        return False

    logger.info(
        "Cold start: training LSTM on %.1f days of real data (%d rows)",
        span_days,
        len(df),
    )
    df_train = df.rename(columns={"avg_power": "power_w"})
    model, scaler = train_from_df(df_train)

    Path(MODEL_PATH).parent.mkdir(parents=True, exist_ok=True)
    torch.save(model, MODEL_PATH)
    with open(SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)
    logger.info("Cold start complete — model saved to %s", MODEL_PATH)
    return True


def get_postgres_connection():
    url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    engine = create_engine(url)
    logger.info("Connected to PostgreSQL")
    return engine


def fetch_latest_features(engine, seq_len: int = SEQ_LEN) -> pd.DataFrame:
    """Fetch the last seq_len hours of avg_power per node from energy_features."""
    lookback_ms = seq_len * 3600 * 1000 + 3600 * 1000  # extra hour buffer
    query = f"""
        SELECT node_id, timestamp, avg_power
        FROM energy_features
        WHERE timestamp >= EXTRACT(EPOCH FROM NOW()) * 1000 - {lookback_ms}
        ORDER BY node_id, timestamp ASC
    """
    df = pd.read_sql(query, engine)
    logger.info("Fetched %d rows for %d nodes", len(df), df["node_id"].nunique())
    return df


def prepare_forecast_input(features_df: pd.DataFrame, seq_len: int = SEQ_LEN) -> dict:
    """Return {node_id: power_array} for nodes with enough history."""
    node_sequences = {}
    for node_id, grp in features_df.groupby("node_id"):
        grp = grp.sort_values("timestamp")
        if len(grp) < seq_len:
            logger.warning(
                "Node %s has insufficient data (%d < %d)", node_id, len(grp), seq_len
            )
            continue
        node_sequences[node_id] = (
            grp["avg_power"].tail(seq_len).values.astype(np.float32)
        )
    logger.info("Prepared sequences for %d nodes", len(node_sequences))
    return node_sequences


def generate_forecasts(
    model: LSTMForecastingModel, node_sequences: dict
) -> pd.DataFrame:
    forecasts = []
    current_timestamp = int(datetime.now().timestamp() * 1000)

    for node_id, sequence in node_sequences.items():
        try:
            predictions = model.predict(sequence)[:FORECAST_HORIZON]
            for hour_offset, value in enumerate(predictions):
                forecasts.append(
                    {
                        "node_id": node_id,
                        "timestamp": current_timestamp + hour_offset * 3600 * 1000,
                        "predicted_consumption": float(value),
                    }
                )
        except Exception as e:
            logger.error("Error generating forecast for %s: %s", node_id, e)

    df = pd.DataFrame(forecasts)
    logger.info("Generated %d forecast rows", len(df))
    return df


def write_forecasts_to_db(engine, df_forecasts: pd.DataFrame) -> None:
    try:
        df_forecasts.to_sql("forecasts", engine, if_exists="append", index=False)
        logger.info("Written %d forecast rows to PostgreSQL", len(df_forecasts))
    except Exception as e:
        logger.error("Error writing forecasts: %s", e)
        raise


def log_to_mlflow(model_path: str, num_predictions: int, forecast_horizon: int) -> None:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("batch-forecasting")
    with mlflow.start_run():
        mlflow.log_param("model_path", model_path)
        mlflow.log_param("forecast_horizon", forecast_horizon)
        mlflow.log_metric("num_predictions", num_predictions)
        mlflow.log_metric("timestamp", int(datetime.now().timestamp()))
    logger.info("Logged batch pipeline run to MLflow")


def run_batch_pipeline() -> bool:
    logger.info("=" * 60)
    logger.info("Starting Batch Forecasting Pipeline")
    logger.info("=" * 60)

    try:
        if not Path(MODEL_PATH).exists() or not Path(SCALER_PATH).exists():
            logger.info("Model not found — attempting cold-start training ...")
            cold_engine = get_postgres_connection()
            if not _try_cold_start(cold_engine):
                logger.info("Not enough data for cold-start yet — skipping this run")
                return False

        logger.info("Step 1: Loading trained LSTM model and scaler ...")
        model = LSTMForecastingModel(MODEL_PATH, SCALER_PATH)

        logger.info("Step 2: Connecting to PostgreSQL ...")
        engine = get_postgres_connection()

        logger.info("Step 3: Fetching latest energy features ...")
        df_features = fetch_latest_features(engine)
        if df_features.empty:
            logger.error("No features found in database")
            return False

        logger.info("Step 4: Preparing input sequences ...")
        node_sequences = prepare_forecast_input(df_features)
        if not node_sequences:
            logger.error("No valid sequences prepared")
            return False

        logger.info("Step 5: Generating 24-hour forecasts ...")
        df_forecasts = generate_forecasts(model, node_sequences)
        if df_forecasts.empty:
            logger.error("No forecasts generated")
            return False

        logger.info("Step 6: Writing forecasts to PostgreSQL ...")
        write_forecasts_to_db(engine, df_forecasts)

        logger.info("Step 7: Logging to MLflow ...")
        log_to_mlflow(MODEL_PATH, len(df_forecasts), FORECAST_HORIZON)

        logger.info("=" * 60)
        logger.info(
            "Batch Forecasting Pipeline completed — %d forecasts across %d nodes",
            len(df_forecasts),
            len(node_sequences),
        )
        logger.info("=" * 60)
        return True

    except Exception as e:
        logger.error("Pipeline failed: %s", e)
        return False


if __name__ == "__main__":
    success = run_batch_pipeline()
    exit(0 if success else 1)
