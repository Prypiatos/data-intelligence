"""LSTM forecasting model for 24-hour energy consumption prediction.

Training uses the RECON-SL Sri Lankan smart meter dataset.
Set RECON_SL_DIR env var if the data is not in the default location.

Usage:
    python -m src.models.forecasting.lstm_model

Outputs:
    models/lstm_model.pth   — trained model object
    models/lstm_scaler.pkl  — fitted MinMaxScaler (used by batch_pipeline)
"""

import os
import pickle
from pathlib import Path

import mlflow
import numpy as np
import torch
import torch.nn as nn
from sklearn.preprocessing import MinMaxScaler

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


if __name__ == "__main__":
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

    print("Building sequences ...")
    all_X, all_y = [], []
    for _, grp in hourly.groupby("node_id"):
        vals = grp["power_w"].values
        if len(vals) < SEQ_LEN + PRED_LEN:
            continue
        X, y = _build_sequences(vals)
        all_X.append(X)
        all_y.append(y)

    X_all = np.concatenate(all_X)
    y_all = np.concatenate(all_y)
    print(f"Total sequences: {len(X_all):,}")

    # Fit scaler on all power values seen during training
    scaler = MinMaxScaler()
    scaler.fit(np.concatenate([X_all.flatten(), y_all.flatten()]).reshape(-1, 1))

    X_norm = scaler.transform(X_all.reshape(-1, 1)).reshape(X_all.shape)
    y_norm = scaler.transform(y_all.reshape(-1, 1)).reshape(y_all.shape)

    # Shuffle
    rng = np.random.default_rng(42)
    idx = rng.permutation(len(X_norm))
    X_norm, y_norm = X_norm[idx], y_norm[idx]

    X_t = torch.FloatTensor(X_norm).unsqueeze(-1)  # (N, seq_len, 1)
    y_t = torch.FloatTensor(y_norm)                # (N, 24)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Training on {device} ...")

    model = LSTMForecaster().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    loss_fn = nn.MSELoss()
    n = len(X_t)

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "mlruns"))
    mlflow.set_experiment("lstm-forecasting-recon-sl")

    with mlflow.start_run():
        mlflow.log_params({
            "dataset": "RECON-SL",
            "epochs": EPOCHS,
            "batch_size": BATCH_SIZE,
            "seq_len": SEQ_LEN,
            "pred_len": PRED_LEN,
            "max_households": MAX_HOUSEHOLDS,
            "n_sequences": n,
        })

        for epoch in range(EPOCHS):
            model.train()
            epoch_loss = 0.0
            for i in range(0, n, BATCH_SIZE):
                xb = X_t[i : i + BATCH_SIZE].to(device)
                yb = y_t[i : i + BATCH_SIZE].to(device)
                pred = model(xb)
                loss = loss_fn(pred, yb)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item() * len(xb)
            avg_loss = epoch_loss / n
            print(f"  Epoch {epoch + 1:02d}/{EPOCHS}  loss={avg_loss:.6f}")
            mlflow.log_metric("train_loss", avg_loss, step=epoch)

    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model, str(MODEL_OUT))
    print(f"Model saved → {MODEL_OUT}")

    SCALER_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(SCALER_OUT, "wb") as f:
        pickle.dump(scaler, f)
    print(f"Scaler saved → {SCALER_OUT}")
    print("Done.")
