from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "API running"


def test_forecasts():
    response = client.get("/forecasts")
    assert response.status_code == 200
    data = response.json()
    assert "forecast" in data
    assert isinstance(data["forecast"], list)


def test_anomalies():
    response = client.get("/anomalies")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


def test_recommendations():
    response = client.get("/recommendations")
    assert response.status_code == 200
    data = response.json()
    assert "actions" in data