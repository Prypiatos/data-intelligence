import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


FEATURE_COLUMNS = ["voltage", "current", "power", "energy_wh", "power_factor", "apparent_power"]


def extract_features(readings: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(readings)
    df["apparent_power"] = df["voltage"] * df["current"]
    # Avoid division by zero for dead circuits
    df["power_factor"] = np.where(
        df["apparent_power"] > 0,
        df["power"] / df["apparent_power"],
        0.0,
    )
    return df[FEATURE_COLUMNS]


def fit_scaler(X: pd.DataFrame) -> tuple[np.ndarray, StandardScaler]:
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    return X_scaled, scaler


def apply_scaler(X: pd.DataFrame, scaler: StandardScaler) -> np.ndarray:
    return scaler.transform(X)
