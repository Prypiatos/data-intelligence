"""
Performance tests for E2 Data Intelligence.

These don't require any running infrastructure — everything runs in-process.
Thresholds are conservative so they don't flake on slow CI machines.

Run with:
    pytest tests/performance/ -v
"""

import random
import sys
import time
import types
from unittest.mock import MagicMock, patch

import pytest
import torch
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# kafka mock (needed before importing API / anomaly pipeline)
# ---------------------------------------------------------------------------
if "kafka" not in sys.modules:
    _kafka = types.ModuleType("kafka")
    _kafka.KafkaConsumer = MagicMock
    _kafka.KafkaProducer = MagicMock
    _kafka_errors = types.ModuleType("kafka.errors")
    _kafka_errors.KafkaError = Exception
    _kafka.errors = _kafka_errors
    sys.modules["kafka"] = _kafka
    sys.modules["kafka.errors"] = _kafka_errors

from src.api.dependencies import get_db_engine
from src.api.main import app
from src.api.routes import forecasting as forecasting_module
from src.models.anomaly.model import AnomalyDetector
from src.models.forecasting.lstm_model import LSTMForecaster

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_readings(n: int, seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    return [
        {
            "node_id": f"node_{i % 10:02d}",
            "timestamp": 1_000_000 + i * 60_000,
            "voltage": rng.uniform(220, 240),
            "current": rng.uniform(0.5, 8.0),
            "power": rng.uniform(100, 1800),
            "energy_wh": rng.uniform(1, 30),
        }
        for i in range(n)
    ]


def _fitted_detector(n: int = 300) -> AnomalyDetector:
    d = AnomalyDetector(contamination=0.05, n_estimators=100, random_state=42)
    d.fit(_make_readings(n))
    return d


def _db_override(rows=None):
    def override():
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = rows or []
        mock_conn = MagicMock()
        mock_conn.__enter__ = lambda s: mock_conn
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value = mock_result
        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn
        return mock_engine

    return override


@pytest.fixture(scope="module")
def api_client():
    app.dependency_overrides[get_db_engine] = _db_override()
    with patch.object(forecasting_module, "initialize_forecasting"):
        forecasting_module.model = LSTMForecaster()
        forecasting_module.model.eval()
        from sklearn.preprocessing import MinMaxScaler

        forecasting_module.scaler = MinMaxScaler()
        forecasting_module.scaler.fit([[0], [800]])
        forecasting_module.device = torch.device("cpu")
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------


class TestAnomalyDetectionPerf:

    def test_single_reading_under_5ms(self):
        """One reading scored in under 5ms — we process readings in real time."""
        detector = _fitted_detector()
        reading = _make_readings(1)[0]

        start = time.perf_counter()
        detector.predict([reading])
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert (
            elapsed_ms < 5
        ), f"Single prediction took {elapsed_ms:.1f}ms, expected < 5ms"

    def test_batch_100_under_50ms(self):
        """100 readings scored in under 50ms — batch scoring must stay snappy."""
        detector = _fitted_detector()
        readings = _make_readings(100)

        start = time.perf_counter()
        results = detector.predict(readings)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(results) == 100
        assert elapsed_ms < 50, f"100 readings took {elapsed_ms:.1f}ms, expected < 50ms"

    def test_batch_1000_under_200ms(self):
        """1 000 readings scored in under 200ms."""
        detector = _fitted_detector()
        readings = _make_readings(1000)

        start = time.perf_counter()
        results = detector.predict(readings)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(results) == 1000
        assert (
            elapsed_ms < 200
        ), f"1000 readings took {elapsed_ms:.1f}ms, expected < 200ms"

    def test_fit_on_10k_readings_under_10s(self):
        """Fitting the model on 10 000 readings completes in under 10s.
        Retraining runs weekly — but it still shouldn't block for ages."""
        readings = _make_readings(10_000)
        detector = AnomalyDetector(
            contamination=0.05, n_estimators=100, random_state=42
        )

        start = time.perf_counter()
        detector.fit(readings)
        elapsed_s = time.perf_counter() - start

        assert (
            elapsed_s < 10
        ), f"Fit on 10k readings took {elapsed_s:.1f}s, expected < 10s"


# ---------------------------------------------------------------------------
# LSTM forecasting
# ---------------------------------------------------------------------------


class TestLSTMInferencePerf:

    def test_single_inference_under_50ms(self):
        """Single 24h forecast in under 50ms (CPU, no warm-up needed)."""
        model = LSTMForecaster()
        model.eval()
        X = torch.randn(1, 10, 1)

        with torch.no_grad():
            start = time.perf_counter()
            model(X)
            elapsed_ms = (time.perf_counter() - start) * 1000

        assert (
            elapsed_ms < 50
        ), f"LSTM inference took {elapsed_ms:.1f}ms, expected < 50ms"

    def test_batch_32_under_200ms(self):
        """Batch of 32 forecasts under 200ms — matches training batch size."""
        model = LSTMForecaster()
        model.eval()
        X = torch.randn(32, 10, 1)

        with torch.no_grad():
            start = time.perf_counter()
            output = model(X)
            elapsed_ms = (time.perf_counter() - start) * 1000

        assert output.shape == (32, 24)
        assert (
            elapsed_ms < 200
        ), f"Batch-32 LSTM took {elapsed_ms:.1f}ms, expected < 200ms"


# ---------------------------------------------------------------------------
# API response time
# ---------------------------------------------------------------------------


class TestAPIResponsePerf:

    def test_health_under_20ms(self, api_client):
        """Health check should be instant — load balancers poll this."""
        start = time.perf_counter()
        r = api_client.get("/health")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert r.status_code == 200
        assert elapsed_ms < 20, f"/health took {elapsed_ms:.1f}ms, expected < 20ms"

    def test_anomalies_endpoint_under_100ms(self, api_client):
        """/anomalies with mocked DB returns in under 100ms."""
        start = time.perf_counter()
        r = api_client.get("/anomalies")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert r.status_code == 200
        assert elapsed_ms < 100, f"/anomalies took {elapsed_ms:.1f}ms, expected < 100ms"

    def test_forecast_predict_under_200ms(self, api_client):
        """/forecast/predict (LSTM inference + serialisation) under 200ms."""
        payload = {"power_readings": [400, 420, 450, 480, 500, 470, 420, 380, 350, 340]}

        start = time.perf_counter()
        r = api_client.post("/forecast/predict", json=payload)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert r.status_code == 200
        assert (
            elapsed_ms < 200
        ), f"/forecast/predict took {elapsed_ms:.1f}ms, expected < 200ms"

    def test_recommendations_under_200ms(self, api_client):
        """/recommendations generates on the fly — should still be fast with empty DB."""
        with patch(
            "src.api.routes.recommendations.run_recommendations", return_value=[]
        ):
            start = time.perf_counter()
            r = api_client.get("/recommendations")
            elapsed_ms = (time.perf_counter() - start) * 1000

        assert r.status_code == 200
        assert (
            elapsed_ms < 200
        ), f"/recommendations took {elapsed_ms:.1f}ms, expected < 200ms"

    def test_concurrent_forecast_requests(self, api_client):
        """10 concurrent /forecast/predict calls all return 200 — no race conditions."""
        import concurrent.futures

        payload = {"power_readings": [400] * 10}

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [
                pool.submit(api_client.post, "/forecast/predict", json=payload)
                for _ in range(10)
            ]
            statuses = [f.result().status_code for f in futures]

        assert all(s == 200 for s in statuses), f"Some requests failed: {statuses}"
