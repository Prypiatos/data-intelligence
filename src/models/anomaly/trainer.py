"""
Train the anomaly detection model.

Supports two data sources (controlled by the DATA_SOURCE env var):
  recon_sl  (default) — RECON-SL Sri Lankan smart meter dataset
  uci                 — UCI Individual Household Electric Power Consumption
  bulb                — Synthetic incandescent light bulb data (for demo/testing)

UCI dataset: place the raw file at data/uci-household-power.txt
Download: https://archive.ics.uci.edu/static/public/235/individual+household+electric+power+consumption.zip

Usage:
    python -m src.models.anomaly.trainer
    DATA_SOURCE=uci python -m src.models.anomaly.trainer
    DATA_SOURCE=bulb python -m src.models.anomaly.trainer

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
RECON_SL_MAX_ROWS = 500_000

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


def _load_bulb_readings(
    rated_watts: float = 60.0,
    n_readings: int = 50_000,
    interval_sec: int = 5,
    node_id: str = "bulb-demo-01",
) -> list[dict]:
    """Generate synthetic incandescent bulb readings for demo/testing.

    Incandescent characteristics:
    - Purely resistive load — power factor ≈ 1.0
    - Power proportional to V² (P = V²/R), so fluctuates with voltage
    - Binary state: fully on at rated wattage, or fully off (no dimming)
    - Typical on periods: 2–8 hours; off periods: 2–12 hours
    """
    rng = np.random.default_rng(42)

    # Start 90 days ago so timestamps align with retention window
    import pendulum

    start_ms = int(pendulum.now("UTC").subtract(days=90).timestamp() * 1000)

    readings = []
    ts_ms = start_ms
    bulb_on = False
    remaining_in_state = 0

    for _ in range(n_readings):
        if remaining_in_state <= 0:
            bulb_on = not bulb_on
            duration_sec = (
                rng.uniform(2 * 3600, 8 * 3600)
                if bulb_on
                else rng.uniform(2 * 3600, 12 * 3600)
            )
            remaining_in_state = int(duration_sec / interval_sec)

        # Voltage fluctuates ±3V around 230V (Sri Lanka grid)
        voltage = float(np.clip(rng.normal(230.0, 1.5), 220.0, 240.0))

        if bulb_on:
            # Incandescent power scales with V² (resistive load: P = V²/R)
            power = rated_watts * (voltage / 230.0) ** 2
            power = float(max(0.0, rng.normal(power, power * 0.005)))
            current = power / voltage
            energy_wh = power * interval_sec / 3600.0
        else:
            power = 0.0
            current = 0.0
            energy_wh = 0.0

        readings.append(
            {
                "node_id": node_id,
                "timestamp": int(ts_ms),
                "voltage": round(voltage, 2),
                "current": round(current, 4),
                "power": round(power, 2),
                "energy_wh": round(energy_wh, 6),
            }
        )

        ts_ms += interval_sec * 1000
        remaining_in_state -= 1

    print(
        f"Generated {len(readings):,} synthetic incandescent bulb readings ({rated_watts}W)"
    )
    return readings


def _load_recon_sl_readings(max_rows: int = RECON_SL_MAX_ROWS) -> list[dict]:
    """Load RECON-SL data and map columns to the telemetry reading schema."""
    from src.models.recon_sl_loader import load_recon_sl

    print("Loading RECON-SL dataset ...")
    df = load_recon_sl()

    if len(df) > max_rows:
        df = df.sample(n=max_rows, random_state=42)

    readings = [
        {
            "node_id": row.node_id,
            "timestamp": int(row.timestamp_ms),
            "voltage": float(row.voltage),
            "current": float(row.current),
            "power": float(row.power_w),
            "energy_wh": float(row.energy_wh),
        }
        for row in df.itertuples(index=False)
    ]
    print(f"Prepared {len(readings):,} readings from RECON-SL")
    return readings


def train(
    contamination: float = 0.05,
    n_estimators: int = 100,
    data_source: str | None = None,
    data_path: Path = UCI_DATA_PATH,
    output_dir: Path = MODEL_OUTPUT_DIR,
) -> AnomalyDetector:
    if data_source is None:
        data_source = os.getenv("DATA_SOURCE", "recon_sl")

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "mlruns"))  # type: ignore[attr-defined]
    mlflow.set_experiment(EXPERIMENT_NAME)  # type: ignore[attr-defined]

    if data_source == "uci":
        if not data_path.exists():
            raise FileNotFoundError(
                f"UCI dataset not found at {data_path}. "
                "Download from https://archive.ics.uci.edu/static/public/235/individual+household+electric+power+consumption.zip "
                "and place the extracted .txt file at data/uci-household-power.txt"
            )
        print(f"Loading UCI dataset from {data_path} ...")
        readings = _load_uci_readings(data_path)
    elif data_source == "bulb":
        readings = _load_bulb_readings()
        # Synthetic clean data — very few genuine anomalies expected
        contamination = 0.01
    else:
        readings = _load_recon_sl_readings()

    print(f"Loaded {len(readings):,} readings after dropping missing values")

    with mlflow.start_run():  # type: ignore[attr-defined]
        detector = AnomalyDetector(
            contamination=contamination, n_estimators=n_estimators
        )
        detector.fit(readings)

        mlflow.log_params({**detector.params, "n_readings": len(readings), "dataset": data_source})  # type: ignore[attr-defined]

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
