"""
Train the anomaly detection model against mock energy readings.

Usage:
    python -m src.models.anomaly.trainer

MLflow UI:
    mlflow ui --backend-store-uri ./mlruns
    open http://localhost:5000
"""

import os
import random
import time
from pathlib import Path

import mlflow  # type: ignore[attr-defined]
import numpy as np

from .model import AnomalyDetector

EXPERIMENT_NAME = "anomaly-detection"
MODEL_OUTPUT_DIR = Path("models/anomaly")

# Mirrors E1 telemetry schema (issue #6)
_NODE_TYPES = ["plug", "circuit", "main"]
_NODE_IDS = [f"{t}-{i:02d}" for t in _NODE_TYPES for i in range(1, 6)]


def _generate_mock_readings(n: int = 300, anomaly_fraction: float = 0.05) -> list[dict]:
    rng = random.Random(42)
    readings = []
    base_ts = int(time.time() * 1000) - n * 60_000

    for i in range(n):
        is_anomaly = rng.random() < anomaly_fraction
        voltage = rng.uniform(220, 240)
        if is_anomaly:
            # Simulate theft (unusually high current) or leakage (low voltage drop)
            current = rng.uniform(15, 30)
            power = voltage * current * rng.uniform(0.3, 0.5)
        else:
            current = rng.uniform(0.5, 10)
            power = voltage * current * rng.uniform(0.85, 0.99)

        readings.append(
            {
                "node_id": rng.choice(_NODE_IDS),
                "timestamp": base_ts + i * 60_000,
                "voltage": round(voltage, 2),
                "current": round(current, 3),
                "power": round(power, 2),
                "energy_wh": round(power / 60, 4),
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
    n_readings: int = 300,
    output_dir: Path = MODEL_OUTPUT_DIR,
) -> AnomalyDetector:
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))  # type: ignore[attr-defined]
    mlflow.set_experiment(EXPERIMENT_NAME)  # type: ignore[attr-defined]

    readings = _generate_mock_readings(n=n_readings, anomaly_fraction=contamination)

    with mlflow.start_run():  # type: ignore[attr-defined]
        detector = AnomalyDetector(
            contamination=contamination, n_estimators=n_estimators
        )
        detector.fit(readings)

        mlflow.log_params({**detector.params, "n_readings": n_readings})  # type: ignore[attr-defined]

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
