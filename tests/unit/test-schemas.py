"""Unit tests for API Pydantic schemas."""

import pytest
from pydantic import ValidationError

from src.api.schemas import (
    AnomalyData,
    AnomalyResponse,
    BaseResponse,
    ForecastData,
    ForecastItem,
    ForecastResponse,
    MessageData,
    MessageResponse,
    RecommendationData,
    RecommendationResponse,
)


class TestBaseResponse:
    def test_valid_with_status_only(self):
        r = BaseResponse(status="ok")
        assert r.status == "ok"
        assert r.message is None

    def test_valid_with_message(self):
        r = BaseResponse(status="error", message="something failed")
        assert r.message == "something failed"

    def test_missing_status_raises(self):
        with pytest.raises(ValidationError):
            BaseResponse()


class TestMessageResponse:
    def test_valid(self):
        r = MessageResponse(status="ok", data=MessageData(message="hello"))
        assert r.data.message == "hello"

    def test_missing_data_raises(self):
        with pytest.raises(ValidationError):
            MessageResponse(status="ok")


class TestForecastResponse:
    def test_valid(self):
        item = ForecastItem(time="2026-05-05T00:00:00", value=432.5)
        data = ForecastData(node_id=1, forecast=[item])
        r = ForecastResponse(status="ok", data=data)
        assert len(r.data.forecast) == 1
        assert r.data.forecast[0].value == 432.5

    def test_forecast_item_value_is_float(self):
        item = ForecastItem(time="2026-05-05T00:00:00", value=100)
        assert isinstance(item.value, float)

    def test_empty_forecast_list(self):
        data = ForecastData(node_id=1, forecast=[])
        assert data.forecast == []

    def test_missing_forecast_raises(self):
        with pytest.raises(ValidationError):
            ForecastData(node_id=1)


class TestAnomalyResponse:
    def test_valid(self):
        data = AnomalyData(node_id=1, status="anomaly", score=0.85)
        r = AnomalyResponse(status="ok", data=data)
        assert r.data.score == 0.85

    def test_score_is_float(self):
        data = AnomalyData(node_id=1, status="normal", score=1)
        assert isinstance(data.score, float)

    def test_missing_field_raises(self):
        with pytest.raises(ValidationError):
            AnomalyData(node_id=1, status="anomaly")


class TestRecommendationResponse:
    def test_valid(self):
        data = RecommendationData(node_id=1, actions=["reduce load", "check meter"])
        r = RecommendationResponse(status="ok", data=data)
        assert len(r.data.actions) == 2

    def test_empty_actions_list(self):
        data = RecommendationData(node_id=1, actions=[])
        assert data.actions == []

    def test_missing_actions_raises(self):
        with pytest.raises(ValidationError):
            RecommendationData(node_id=1)
