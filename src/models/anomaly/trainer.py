"""
Train the anomaly detection model against UCI household power consumption data.

Dataset: UCI Individual Household Electric Power Consumption
Place the raw file at: data/uci-household-power.txt
Download: https://archive.ics.uci.edu/static/public/235/individual+household+electric+power+consumption.zip

Usage:
    python -m src.models.anomaly.trainer

MLflow UI:
    mlflow ui --backend-store-uri ./mlruns
    open http://localhost:5000
"""

import os
from pathlib import Path

import mlflow  # type: ignore[attr-defined]
import numpy as np
import pandas as pd

from .model import AnomalyDetector

EXPERIMENT_NAME = "anomaly-detection"
MODEL_OUTPUT_DIR = Path("models/anomaly")
UCI_DATA_PATH = Path("data/uci-household-power.txt")

# Single household — treat as one node
_NODE_ID = "uci-household-main"


def _load_uci_readings(path: Path) -> list[dict]:
    """Load and map UCI dataset columns to our telemetry schema."""
    df = pd.read_csv(path, sep=";", low_memory=False)

    # Drop rows with missing values (marked as '?' in the raw file)
    df = df.replace("?", pd.NA).dropna()

    df["voltage"] = df["Voltage"].astype(float)
    df["current"] = df["Global_intensity"].astype(float)
    # Global_active_power is in kW — convert to W
    df["power"] = df["Global_active_power"].astype(float) * 1000
    # Sub-metering values are in watt-hours per minute; sum all three circuits
    df["energy_wh"] = (
        df["Sub_metering_1"].astype(float)
        + df["Sub_metering_2"].astype(float)
        + df["Sub_metering_3"].astype(float)
    )
    df["timestamp"] = (
        pd.to_datetime(df["Date"] + " " + df["Time"], dayfirst=True).astype("int64")
        // 10**6
    )  # epoch ms

    readings = []
    for row in df[["timestamp", "voltage", "current", "power", "energy_wh"]].itertuples(
        index=False
    ):
        readings.append(
            {
                "node_id": _NODE_ID,
                "timestamp": int(row.timestamp),
                "voltage": round(row.voltage, 2),
                "current": round(row.current, 3),
                "power": round(row.power, 2),
                "energy_wh": round(row.energy_wh, 4),
            }
        )

    return readings


def _compute_metrics(predictions: list[dict]) -> dict:
    scores = [p["anomaly_score"] for p in predictions]
    severities = [p["severity"] for p in predictions]
    return {
        "n_readings": len(predictions),
        "n_anomalies": sum(1 for s in severities if s != "normal"),
        "anomaly_rate": round(
            sum(1 for s in severities if s != "normal") / len(predictions), 4
        ),
        "mean_score": round(float(np.mean(scores)), 6),
        "min_score": round(float(np.min(scores)), 6),
        "max_score": round(float(np.max(scores)), 6),
    }


def train(
    contamination: float = 0.05,
    n_estimators: int = 100,
    data_path: Path = UCI_DATA_PATH,
    output_dir: Path = MODEL_OUTPUT_DIR,
) -> AnomalyDetector:
    if not data_path.exists():
        raise FileNotFoundError(
            f"UCI dataset not found at {data_path}. "
            "Download from https://archive.ics.uci.edu/static/public/235/individual+household+electric+power+consumption.zip "
            "and place the extracted .txt file at data/uci-household-power.txt"
        )

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "mlruns"))  # type: ignore[attr-defined]
    mlflow.set_experiment(EXPERIMENT_NAME)  # type: ignore[attr-defined]

    print(f"Loading UCI dataset from {data_path} ...")
    readings = _load_uci_readings(data_path)
    print(f"Loaded {len(readings):,} readings after dropping missing values")

    with mlflow.start_run():  # type: ignore[attr-defined]
        detector = AnomalyDetector(
            contamination=contamination, n_estimators=n_estimators
        )
        detector.fit(readings)

        mlflow.log_params({**detector.params, "n_readings": len(readings), "dataset": "uci-household-power"})  # type: ignore[attr-defined]

        print("Scoring readings ...")
        predictions = detector.predict(readings)
        metrics = _compute_metrics(predictions)
        mlflow.log_metrics(metrics)  # type: ignore[attr-defined]

        detector.save(output_dir)
        mlflow.log_artifact(str(output_dir / "detector.pkl"))  # type: ignore[attr-defined]

        print(f"Training complete. Metrics: {metrics}")
        print(f"Model saved to: {output_dir}")
        print("View results: mlflow ui --backend-store-uri ./mlruns")

    return detector


if __name__ == "__main__":
    train()
