import pandas as pd
import numpy as np
import torch
import torch.nn as nn
from sklearn.preprocessing import MinMaxScaler
import mlflow


# Mock data
def create_mock_data(days=30):
    timestamps = pd.date_range("2024-01-01", periods=days * 24, freq="h")
    power = [
        400 + 200 * np.sin(2 * np.pi * (h % 24) / 24) + np.random.normal(0, 30)
        for h in range(days * 24)
    ]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "power": power,
            "hour": timestamps.hour,
            "day": timestamps.dayofyear,
        }
    )


# LSTM Model
class LSTMForecaster(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(1, 64, 2, batch_first=True)
        self.fc = nn.Linear(64, 24)
        self.relu = nn.ReLU()

    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        output = self.fc(lstm_out[:, -1, :])
        return self.relu(output)


# Train
if __name__ == "__main__":
    mlflow.start_run()

    # Data
    df = create_mock_data(days=30)
    scaler = MinMaxScaler()
    data = scaler.fit_transform(df[["power"]])

    # Model
    model = LSTMForecaster()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    loss_fn = nn.MSELoss()

    # Train
    for epoch in range(10):
        X = torch.FloatTensor(data[:-24]).unsqueeze(1)
        y = torch.FloatTensor(data[24:, 0])

        pred = model(X)
        loss = loss_fn(pred[-1], y[-24:])

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        print(f"Epoch {epoch+1}, Loss: {loss.item():.4f}")

    # Log to MLflow
    mlflow.log_param("model_type", "LSTM")
    mlflow.log_param("epochs", 10)
    mlflow.log_metric("loss", loss.item())
    mlflow.end_run()

    print("✅ Model trained! Check http://localhost:5000")
