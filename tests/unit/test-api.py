"""Unit tests for all FastAPI endpoints."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_db_engine
from src.api.main import app

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
    with TestClient(app) as c:
        yield c


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
