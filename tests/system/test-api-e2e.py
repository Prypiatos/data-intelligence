"""
System tests: API end-to-end with live data in the database.

Requires the full stack to be running:
    docker compose up

Run with:
    pytest tests/system/test-api-e2e.py -v
"""

import httpx
import pytest

BASE = "http://localhost:8000"


@pytest.fixture(scope="module")
def api():
    return httpx.Client(base_url=BASE, timeout=10)


class TestRoot:
    def test_returns_200(self, api):
        assert api.get("/").status_code == 200

    def test_lists_all_endpoints(self, api):
        data = api.get("/").json()
        endpoints = data.get("endpoints", {})
        assert "anomalies" in endpoints
        assert "recommendations" in endpoints


class TestHealth:
    def test_returns_200(self, api):
        assert api.get("/health").status_code == 200

    def test_status_healthy(self, api):
        assert api.get("/health").json()["status"] == "healthy"


class TestForecastPredict:
    def test_predict_returns_24h_forecast(self, api):
        response = api.post(
            "/forecast/predict",
            json={"power_readings": [400, 420, 450, 480, 500, 470, 420, 380, 350, 340]},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["forecast"]) == 24
        assert data["hours_ahead"] == 24
        assert data["unit"] == "watts"

    def test_predict_rejects_wrong_input_count(self, api):
        response = api.post("/forecast/predict", json={"power_readings": [400] * 5})
        assert response.status_code == 400

    def test_predict_batch_returns_correct_count(self, api):
        response = api.post(
            "/forecast/predict-batch",
            json={"batch_readings": [[400] * 10, [500] * 10]},
        )
        assert response.status_code == 200
        assert response.json()["count"] == 2


class TestForecasts:
    def test_returns_list(self, api):
        response = api.get("/forecast/forecasts")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_schema(self, api):
        data = api.get("/forecast/forecasts?limit=1").json()
        if data:
            record = data[0]
            assert "node_id" in record
            assert "timestamp" in record
            assert "predicted_consumption" in record

    def test_node_id_filter(self, api):
        # Should return 200 regardless of whether data exists
        assert api.get("/forecast/forecasts?node_id=node_001").status_code == 200

    def test_concurrent_requests(self, api):
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(api.get, "/forecast/forecasts") for _ in range(10)]
            results = [f.result().status_code for f in futures]
        assert all(s == 200 for s in results)


class TestAnomalies:
    def test_returns_list(self, api):
        response = api.get("/anomalies")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_schema(self, api):
        data = api.get("/anomalies?limit=1").json()
        if data:
            record = data[0]
            assert "node_id" in record
            assert "timestamp" in record
            assert "anomaly_type" in record
            assert "score" in record
            assert "severity" in record

    def test_severity_filter(self, api):
        assert api.get("/anomalies?severity=high").status_code == 200

    def test_data_integrity_severity_values(self, api):
        data = api.get("/anomalies?limit=100").json()
        valid = {"high", "medium", "low"}
        for record in data:
            assert record["severity"] in valid

    def test_concurrent_requests(self, api):
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(api.get, "/anomalies") for _ in range(10)]
            results = [f.result().status_code for f in futures]
        assert all(s == 200 for s in results)


class TestRecommendations:
    def test_returns_list(self, api):
        response = api.get("/recommendations")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_schema(self, api):
        data = api.get("/recommendations").json()
        if data:
            record = data[0]
            assert "node_id" in record
            assert "type" in record
            assert "severity" in record
            assert "message" in record
            assert "generated_at" in record
            assert "metadata" in record

    def test_severity_values(self, api):
        data = api.get("/recommendations").json()
        valid = {"high", "medium", "low"}
        for rec in data:
            assert rec["severity"] in valid

    def test_type_values(self, api):
        data = api.get("/recommendations").json()
        valid = {"high_anomaly", "load_shift", "high_consumption"}
        for rec in data:
            assert rec["type"] in valid
