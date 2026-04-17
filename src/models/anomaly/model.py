import pickle
from pathlib import Path

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from .preprocessor import apply_scaler, extract_features, fit_scaler


SEVERITY_THRESHOLDS = {
    "high":   -0.15,
    "medium": -0.05,
    "low":     0.0,
}


def _score_to_severity(score: float) -> str:
    if score <= SEVERITY_THRESHOLDS["high"]:
        return "high"
    if score <= SEVERITY_THRESHOLDS["medium"]:
        return "medium"
    if score <= SEVERITY_THRESHOLDS["low"]:
        return "low"
    return "normal"


class AnomalyDetector:
    def __init__(self, contamination: float = 0.05, n_estimators: int = 100, random_state: int = 42):
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.random_state = random_state
        self._model: IsolationForest | None = None
        self._scaler: StandardScaler | None = None

    def fit(self, readings: list[dict]) -> "AnomalyDetector":
        X = extract_features(readings)
        X_scaled, self._scaler = fit_scaler(X)
        self._model = IsolationForest(
            contamination=self.contamination,
            n_estimators=self.n_estimators,
            random_state=self.random_state,
        )
        self._model.fit(X_scaled)
        return self

    def predict(self, readings: list[dict]) -> list[dict]:
        if self._model is None or self._scaler is None:
            raise RuntimeError("Model is not fitted. Call fit() first.")
        X = extract_features(readings)
        X_scaled = apply_scaler(X, self._scaler)
        scores = self._model.decision_function(X_scaled)
        results = []
        for reading, score in zip(readings, scores):
            results.append({
                "node_id": reading.get("node_id"),
                "timestamp": reading.get("timestamp"),
                "anomaly_score": round(float(score), 6),
                "severity": _score_to_severity(float(score)),
            })
        return results

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        with open(path / "detector.pkl", "wb") as f:
            pickle.dump({"model": self._model, "scaler": self._scaler}, f)

    @classmethod
    def load(cls, path: str | Path) -> "AnomalyDetector":
        path = Path(path)
        with open(path / "detector.pkl", "rb") as f:
            state = pickle.load(f)
        detector = cls()
        detector._model = state["model"]
        detector._scaler = state["scaler"]
        return detector

    @property
    def params(self) -> dict:
        return {
            "contamination": self.contamination,
            "n_estimators": self.n_estimators,
            "random_state": self.random_state,
        }
