import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

FEATURE_COLUMNS = [
    "hour_of_day",
    "day_of_week",
    "is_active",
]


def extract_features(readings: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(readings)
    # timestamp is epoch milliseconds
    dt = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["hour_of_day"] = dt.dt.hour
    df["day_of_week"] = dt.dt.dayofweek
    df["is_active"] = (df["power"] > 0).astype(int)
    return df[FEATURE_COLUMNS]


def fit_scaler(X: pd.DataFrame) -> tuple[np.ndarray, StandardScaler]:
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    return X_scaled, scaler


def apply_scaler(X: pd.DataFrame, scaler: StandardScaler) -> np.ndarray:
    return scaler.transform(X)
