# System test: API endpoints return correct forecasts, anomalies and recommendations
import httpx


def test_root():
    response = httpx.get("http://localhost:8000/")
    assert response.status_code == 200


def test_forecasts():
    response = httpx.get("http://localhost:8000/forecasts")
    assert response.status_code == 200


def test_anomalies():
    response = httpx.get("http://localhost:8000/anomalies")
    assert response.status_code == 200


def test_recommendations():
    response = httpx.get("http://localhost:8000/recommendations")
    assert response.status_code == 200
