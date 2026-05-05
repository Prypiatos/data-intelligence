"""Unit tests for all FastAPI endpoints."""

from unittest.mock import MagicMock, patch

import pytest
import torch
from fastapi.testclient import TestClient

from src.api.dependencies import get_db_engine
from src.api.main import app
from src.api.routes import forecasting as forecasting_module

# ============================================================
# Helpers
# ============================================================


def _db_override(rows):
    """Return a get_db_engine dependency override yielding fixed rows."""

    def override():
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = rows
        mock_conn = MagicMock()
        mock_conn.__enter__ = lambda s: mock_conn
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value = mock_result
        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn
        return mock_engine

    return override


def _db_override_error():
    """Return a get_db_engine override that raises on execute."""

    def override():
        mock_conn = MagicMock()
        mock_conn.__enter__ = lambda s: mock_conn
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.side_effect = Exception("connection refused")
        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn
        return mock_engine

    return override


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    """Ensure dependency overrides are cleaned up after each test."""
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def client():
    with patch.object(forecasting_module, "initialize_forecasting"):
        with TestClient(app) as c:
            yield c


@pytest.fixture()
def client_with_model(client):
    """TestClient with a real (untrained) LSTM model wired up."""
    device = torch.device("cpu")
    from src.models.forecasting.lstm_model import LSTMForecaster
    from sklearn.preprocessing import MinMaxScaler

    model = LSTMForecaster().to(device)
    model.eval()
    scaler = MinMaxScaler()
    scaler.fit([[0], [800]])

    forecasting_module.model = model
    forecasting_module.device = device
    forecasting_module.scaler = scaler

    yield client

    forecasting_module.model = None
    forecasting_module.device = None
    forecasting_module.scaler = None


# ============================================================
# GET /
# ============================================================


class TestRoot:
    def test_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_response_contains_name_and_version(self, client):
        data = client.get("/").json()
        assert data["name"] == "Energy Management System API"
        assert data["version"] == "1.0.0"

    def test_response_lists_endpoints(self, client):
        data = client.get("/").json()
        assert "endpoints" in data
        assert "anomalies" in data["endpoints"]
        assert "recommendations" in data["endpoints"]


# ============================================================
# GET /health
# ============================================================


class TestHealth:
    def test_returns_200(self, client):
        assert client.get("/health").status_code == 200

    def test_status_is_healthy(self, client):
        data = client.get("/health").json()
        assert data["status"] == "healthy"

    def test_response_schema(self, client):
        data = client.get("/health").json()
        assert "status" in data
        assert "version" in data
        assert "service" in data


# ============================================================
# POST /forecast/predict
# ============================================================


class TestForecastPredict:
    def test_returns_503_when_model_not_loaded(self, client):
        assert (
            client.post(
                "/forecast/predict", json={"power_readings": [400] * 10}
            ).status_code
            == 503
        )

    def test_returns_200_with_valid_input(self, client_with_model):
        response = client_with_model.post(
            "/forecast/predict", json={"power_readings": [400] * 10}
        )
        assert response.status_code == 200

    def test_response_schema(self, client_with_model):
        data = client_with_model.post(
            "/forecast/predict", json={"power_readings": [400] * 10}
        ).json()
        assert "forecast" in data
        assert "hours_ahead" in data
        assert "unit" in data
        assert data["hours_ahead"] == 24
        assert data["unit"] == "watts"

    def test_forecast_has_24_values(self, client_with_model):
        data = client_with_model.post(
            "/forecast/predict", json={"power_readings": [400] * 10}
        ).json()
        assert len(data["forecast"]) == 24

    def test_forecast_values_are_non_negative(self, client_with_model):
        data = client_with_model.post(
            "/forecast/predict", json={"power_readings": [400] * 10}
        ).json()
        assert all(v >= 0 for v in data["forecast"])

    def test_returns_400_for_wrong_reading_count(self, client_with_model):
        response = client_with_model.post(
            "/forecast/predict", json={"power_readings": [400] * 5}
        )
        assert response.status_code == 400

    def test_returns_400_for_too_many_readings(self, client_with_model):
        response = client_with_model.post(
            "/forecast/predict", json={"power_readings": [400] * 20}
        )
        assert response.status_code == 400


# ============================================================
# POST /forecast/predict-batch
# ============================================================


class TestForecastPredictBatch:
    def test_returns_503_when_model_not_loaded(self, client):
        response = client.post(
            "/forecast/predict-batch",
            json={"batch_readings": [[400] * 10]},
        )
        assert response.status_code == 503

    def test_returns_200_with_valid_batch(self, client_with_model):
        response = client_with_model.post(
            "/forecast/predict-batch",
            json={"batch_readings": [[400] * 10, [500] * 10]},
        )
        assert response.status_code == 200

    def test_response_count_matches_input(self, client_with_model):
        data = client_with_model.post(
            "/forecast/predict-batch",
            json={"batch_readings": [[400] * 10, [500] * 10, [300] * 10]},
        ).json()
        assert data["count"] == 3
        assert len(data["forecasts"]) == 3

    def test_each_forecast_has_24_values(self, client_with_model):
        data = client_with_model.post(
            "/forecast/predict-batch",
            json={"batch_readings": [[400] * 10]},
        ).json()
        assert len(data["forecasts"][0]) == 24

    def test_returns_400_for_empty_batch(self, client_with_model):
        response = client_with_model.post(
            "/forecast/predict-batch", json={"batch_readings": []}
        )
        assert response.status_code == 400

    def test_returns_400_for_wrong_sequence_length_in_batch(self, client_with_model):
        response = client_with_model.post(
            "/forecast/predict-batch",
            json={"batch_readings": [[400] * 5]},
        )
        assert response.status_code == 400


# ============================================================
# GET /forecast/forecasts
# ============================================================


FORECAST_ROWS = [
    {"node_id": "node_001", "timestamp": 1714500000000, "predicted_consumption": 450.5},
    {"node_id": "node_002", "timestamp": 1714496400000, "predicted_consumption": 310.0},
]


class TestGetForecasts:
    def test_returns_200(self, client):
        app.dependency_overrides[get_db_engine] = _db_override(FORECAST_ROWS)
        assert client.get("/forecast/forecasts").status_code == 200

    def test_returns_list(self, client):
        app.dependency_overrides[get_db_engine] = _db_override(FORECAST_ROWS)
        data = client.get("/forecast/forecasts").json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_response_schema(self, client):
        app.dependency_overrides[get_db_engine] = _db_override(FORECAST_ROWS)
        record = client.get("/forecast/forecasts").json()[0]
        assert "node_id" in record
        assert "timestamp" in record
        assert "predicted_consumption" in record

    def test_node_id_filter_passes_param(self, client):
        app.dependency_overrides[get_db_engine] = _db_override([FORECAST_ROWS[0]])
        data = client.get("/forecast/forecasts?node_id=node_001").json()
        assert len(data) == 1
        assert data[0]["node_id"] == "node_001"

    def test_returns_503_on_db_error(self, client):
        app.dependency_overrides[get_db_engine] = _db_override_error()
        assert client.get("/forecast/forecasts").status_code == 503

    def test_empty_list_when_no_data(self, client):
        app.dependency_overrides[get_db_engine] = _db_override([])
        data = client.get("/forecast/forecasts").json()
        assert data == []


# ============================================================
# GET /anomalies
# ============================================================


ANOMALY_ROWS = [
    {
        "node_id": "node_001",
        "timestamp": 1714500000000,
        "anomaly_type": "theft_or_leakage",
        "score": 0.12,
        "severity": "high",
    },
    {
        "node_id": "node_002",
        "timestamp": 1714496400000,
        "anomaly_type": "theft_or_leakage",
        "score": 0.35,
        "severity": "medium",
    },
]


class TestGetAnomalies:
    def test_returns_200(self, client):
        app.dependency_overrides[get_db_engine] = _db_override(ANOMALY_ROWS)
        assert client.get("/anomalies").status_code == 200

    def test_returns_list(self, client):
        app.dependency_overrides[get_db_engine] = _db_override(ANOMALY_ROWS)
        data = client.get("/anomalies").json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_response_schema(self, client):
        app.dependency_overrides[get_db_engine] = _db_override(ANOMALY_ROWS)
        record = client.get("/anomalies").json()[0]
        assert "node_id" in record
        assert "timestamp" in record
        assert "anomaly_type" in record
        assert "score" in record
        assert "severity" in record

    def test_severity_filter_passes_param(self, client):
        app.dependency_overrides[get_db_engine] = _db_override([ANOMALY_ROWS[0]])
        data = client.get("/anomalies?severity=high").json()
        assert len(data) == 1
        assert data[0]["severity"] == "high"

    def test_node_id_filter_passes_param(self, client):
        app.dependency_overrides[get_db_engine] = _db_override([ANOMALY_ROWS[0]])
        data = client.get("/anomalies?node_id=node_001").json()
        assert len(data) == 1
        assert data[0]["node_id"] == "node_001"

    def test_returns_503_on_db_error(self, client):
        app.dependency_overrides[get_db_engine] = _db_override_error()
        assert client.get("/anomalies").status_code == 503

    def test_empty_list_when_no_data(self, client):
        app.dependency_overrides[get_db_engine] = _db_override([])
        assert client.get("/anomalies").json() == []


# ============================================================
# GET /recommendations
# ============================================================


RECOMMENDATION_ROWS = [
    {
        "node_id": "node_001",
        "type": "high_anomaly",
        "severity": "high",
        "message": "Inspect node_001 for irregular consumption.",
        "generated_at": "2026-05-04T00:00:00+00:00",
        "metadata": {"anomaly_score": 0.12},
    }
]


class TestGetRecommendations:
    def test_returns_200(self, client):
        with patch(
            "src.api.routes.recommendations.run_recommendations",
            return_value=RECOMMENDATION_ROWS,
        ):
            assert client.get("/recommendations").status_code == 200

    def test_returns_list(self, client):
        with patch(
            "src.api.routes.recommendations.run_recommendations",
            return_value=RECOMMENDATION_ROWS,
        ):
            data = client.get("/recommendations").json()
            assert isinstance(data, list)
            assert len(data) == 1

    def test_response_schema(self, client):
        with patch(
            "src.api.routes.recommendations.run_recommendations",
            return_value=RECOMMENDATION_ROWS,
        ):
            record = client.get("/recommendations").json()[0]
            assert "node_id" in record
            assert "type" in record
            assert "severity" in record
            assert "message" in record
            assert "generated_at" in record
            assert "metadata" in record

    def test_empty_list_when_no_recommendations(self, client):
        with patch(
            "src.api.routes.recommendations.run_recommendations",
            return_value=[],
        ):
            assert client.get("/recommendations").json() == []

    def test_returns_503_on_engine_error(self, client):
        with patch(
            "src.api.routes.recommendations.run_recommendations",
            side_effect=Exception("db error"),
        ):
            assert client.get("/recommendations").status_code == 503


# ============================================================
# GET /stream/summary
# ============================================================


STREAM_ROWS = [
    {
        "node_id": "node_001",
        "window_start": 1714800000000,
        "window_end": 1714800002000,
        "avg_power": 487.3,
        "max_power": 512.1,
        "record_count": 4,
    },
    {
        "node_id": "node_002",
        "window_start": 1714800000000,
        "window_end": 1714800002000,
        "avg_power": 310.0,
        "max_power": 340.0,
        "record_count": 2,
    },
]


class TestGetStreamSummary:
    def test_returns_200(self, client):
        app.dependency_overrides[get_db_engine] = _db_override(STREAM_ROWS)
        assert client.get("/stream/summary").status_code == 200

    def test_returns_list(self, client):
        app.dependency_overrides[get_db_engine] = _db_override(STREAM_ROWS)
        data = client.get("/stream/summary").json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_response_schema(self, client):
        app.dependency_overrides[get_db_engine] = _db_override(STREAM_ROWS)
        record = client.get("/stream/summary").json()[0]
        assert "node_id" in record
        assert "window_start" in record
        assert "window_end" in record
        assert "avg_power" in record
        assert "max_power" in record
        assert "record_count" in record

    def test_node_id_filter_passes_param(self, client):
        app.dependency_overrides[get_db_engine] = _db_override([STREAM_ROWS[0]])
        data = client.get("/stream/summary?node_id=node_001").json()
        assert len(data) == 1
        assert data[0]["node_id"] == "node_001"

    def test_empty_list_when_no_data(self, client):
        app.dependency_overrides[get_db_engine] = _db_override([])
        assert client.get("/stream/summary").json() == []

    def test_returns_503_on_db_error(self, client):
        app.dependency_overrides[get_db_engine] = _db_override_error()
        assert client.get("/stream/summary").status_code == 503
