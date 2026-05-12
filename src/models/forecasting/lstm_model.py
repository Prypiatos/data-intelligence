"""LSTM forecasting model for 24-hour energy consumption prediction.

Usage:
    python -m src.models.forecasting.lstm_model            # RECON-SL dataset
    DATA_SOURCE=bulb python -m src.models.forecasting.lstm_model

Outputs:
    models/lstm_model.pth   — trained model weights
    models/lstm_scaler.pkl  — fitted MinMaxScaler (used by batch_pipeline)
"""

import logging
import os
import pickle
from pathlib import Path

import mlflow  # type: ignore[import-untyped]
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.preprocessing import MinMaxScaler

logger = logging.getLogger(__name__)

SEQ_LEN = 10
PRED_LEN = 24
HIDDEN = 64
LAYERS = 2
EPOCHS = 30
BATCH_SIZE = 64
LR = 0.001
MAX_HOUSEHOLDS = 200
STEP = 2  # stride when creating sequences

MODEL_OUT = Path("models/lstm_model.pth")
SCALER_OUT = Path("models/lstm_scaler.pkl")

DATA_SOURCE = os.getenv("DATA_SOURCE", "recon_sl")


class LSTMForecaster(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(1, HIDDEN, LAYERS, batch_first=True)
        self.fc = nn.Linear(HIDDEN, PRED_LEN)
        self.relu = nn.ReLU()

    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        return self.relu(self.fc(lstm_out[:, -1, :]))


def _build_sequences(power: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Slide a window over a 1-D hourly power array, returning (X, y) pairs."""
    window = SEQ_LEN + PRED_LEN
    X, y = [], []
    for i in range(0, len(power) - window + 1, STEP):
        X.append(power[i : i + SEQ_LEN])
        y.append(power[i + SEQ_LEN : i + window])
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


def train_from_df(
    hourly_df: pd.DataFrame,
    epochs: int = EPOCHS,
    batch_size: int = BATCH_SIZE,
    lr: float = LR,
) -> tuple[LSTMForecaster, MinMaxScaler]:
    """Train an LSTMForecaster from a DataFrame with columns node_id, power_w.

    Returns (model, scaler) without saving to disk — caller decides where to save.
    Raises ValueError if there is not enough data to build any training sequence.
    """
    all_X, all_y = [], []
    for _, grp in hourly_df.groupby("node_id"):
        vals = grp["power_w"].values.astype(np.float32)
        if len(vals) < SEQ_LEN + PRED_LEN:
            continue
        X, y = _build_sequences(vals)
        all_X.append(X)
        all_y.append(y)

    if not all_X:
        raise ValueError(
            f"No node has enough hourly rows to build sequences "
            f"(need at least {SEQ_LEN + PRED_LEN})"
        )

    X_all = np.concatenate(all_X)
    y_all = np.concatenate(all_y)
    logger.info(
        "Training on %d sequences from %d nodes",
        len(X_all),
        hourly_df["node_id"].nunique(),
    )

    scaler = MinMaxScaler()
    scaler.fit(np.concatenate([X_all.flatten(), y_all.flatten()]).reshape(-1, 1))
    X_norm = scaler.transform(X_all.reshape(-1, 1)).reshape(X_all.shape)
    y_norm = scaler.transform(y_all.reshape(-1, 1)).reshape(y_all.shape)

    rng = np.random.default_rng(42)
    idx = rng.permutation(len(X_norm))
    X_norm, y_norm = X_norm[idx], y_norm[idx]

    X_t = torch.FloatTensor(X_norm).unsqueeze(-1)  # (N, seq_len, 1)
    y_t = torch.FloatTensor(y_norm)  # (N, 24)
    n = len(X_t)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = LSTMForecaster().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    for epoch in range(epochs):
        model.train()
        epoch_loss = 0.0
        for i in range(0, n, batch_size):
            xb = X_t[i : i + batch_size].to(device)
            yb = y_t[i : i + batch_size].to(device)
            pred = model(xb)
            loss = loss_fn(pred, yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item() * len(xb)
        avg_loss = epoch_loss / n
        logger.info("Epoch %02d/%d  loss=%.6f", epoch + 1, epochs, avg_loss)

    return model, scaler


def _generate_bulb_hourly(
    rated_watts: float = 60.0,
    n_days: int = 365,
    n_bulbs: int = 10,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic hourly power data for incandescent bulbs.

    Usage pattern: ON evenings (18–22h, 85% chance) and mornings (7–8h, 60%),
    OFF otherwise (5%). Power when on: rated_watts * (V/230)^2 with small
    voltage noise.
    """
    rng = np.random.default_rng(seed)
    rows = []

    for bulb_idx in range(n_bulbs):
        node_id = f"bulb-synth-{bulb_idx:02d}"
        for day in range(n_days):
            for hour in range(24):
                if 18 <= hour <= 22:
                    on_prob = 0.85
                elif hour in (7, 8):
                    on_prob = 0.60
                else:
                    on_prob = 0.05

                if rng.random() < on_prob:
                    voltage = 230.0 + rng.normal(0, 2.0)
                    power = float(rated_watts * (voltage / 230.0) ** 2)
                else:
                    power = 0.0

                rows.append({"node_id": node_id, "power_w": power})

    return pd.DataFrame(rows)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    if DATA_SOURCE == "bulb":
        print("Generating synthetic bulb hourly data ...")
        hourly = _generate_bulb_hourly()
        mlflow_dataset = "bulb-synthetic"
        mlflow_experiment = "lstm-forecasting-bulb"
    else:
        from src.models.recon_sl_loader import load_recon_sl

        print("Loading RECON-SL dataset ...")
        df = load_recon_sl(max_households=MAX_HOUSEHOLDS)

        print("Resampling to hourly per household ...")
        hourly = (
            df.set_index("datetime")
            .groupby("node_id")["power_w"]
            .resample("1h")
            .mean()
            .reset_index()
            .dropna(subset=["power_w"])
        )
        mlflow_dataset = "RECON-SL"
        mlflow_experiment = "lstm-forecasting-recon-sl"

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "mlruns"))  # type: ignore[attr-defined]
    mlflow.set_experiment(mlflow_experiment)  # type: ignore[attr-defined]

    with mlflow.start_run():  # type: ignore[attr-defined]
        mlflow.log_params(  # type: ignore[attr-defined]
            {
                "dataset": mlflow_dataset,
                "epochs": EPOCHS,
                "batch_size": BATCH_SIZE,
                "seq_len": SEQ_LEN,
                "pred_len": PRED_LEN,
            }
        )

        model, scaler = train_from_df(hourly)

        mlflow.log_metric(  # type: ignore[attr-defined]
            "n_sequences",
            sum(
                max(0, len(grp) - SEQ_LEN - PRED_LEN + 1)
                for _, grp in hourly.groupby("node_id")
            ),
        )

    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model, str(MODEL_OUT))
    print(f"Model saved → {MODEL_OUT}")

    SCALER_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(SCALER_OUT, "wb") as f:
        pickle.dump(scaler, f)
    print(f"Scaler saved → {SCALER_OUT}")
    print("Done.")
