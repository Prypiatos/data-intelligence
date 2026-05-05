"""Unit tests for the recommendations engine."""

import pandas as pd
import pytest

from src.optimization.recommendations import (
    Recommendation,
    _anomaly_recommendations,
    _high_consumption_recommendations,
    _load_shift_recommendations,
    generate_recommendations,
)


def _anomaly_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        rows, columns=["node_id", "timestamp", "anomaly_score", "severity"]
    )


def _forecast_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["node_id", "timestamp", "predicted_consumption"])


# ---------------------------------------------------------------------------
# Recommendation.to_dict
# ---------------------------------------------------------------------------


class TestRecommendationToDict:
    def test_has_all_required_keys(self):
        rec = Recommendation(
            node_id="node_001", type="high_anomaly", severity="high", message="test"
        )
        d = rec.to_dict()
        assert set(d.keys()) == {
            "node_id",
            "type",
            "severity",
            "message",
            "generated_at",
            "metadata",
        }

    def test_generated_at_is_iso_string(self):
        rec = Recommendation(
            node_id="n1", type="high_anomaly", severity="high", message="x"
        )
        assert isinstance(rec.to_dict()["generated_at"], str)
        assert "T" in rec.to_dict()["generated_at"]

    def test_metadata_defaults_to_empty_dict(self):
        rec = Recommendation(
            node_id="n1", type="high_anomaly", severity="high", message="x"
        )
        assert rec.to_dict()["metadata"] == {}


# ---------------------------------------------------------------------------
# _anomaly_recommendations
# ---------------------------------------------------------------------------


class TestAnomalyRecommendations:
    def test_empty_df_returns_empty(self):
        assert _anomaly_recommendations(_anomaly_df([])) == []

    def test_high_severity_produces_recommendation(self):
        df = _anomaly_df(
            [
                {
                    "node_id": "node_001",
                    "timestamp": 1000,
                    "anomaly_score": -0.2,
                    "severity": "high",
                }
            ]
        )
        recs = _anomaly_recommendations(df)
        assert len(recs) == 1
        assert recs[0].type == "high_anomaly"
        assert recs[0].node_id == "node_001"
        assert recs[0].severity == "high"

    def test_medium_severity_produces_recommendation(self):
        df = _anomaly_df(
            [
                {
                    "node_id": "n2",
                    "timestamp": 2000,
                    "anomaly_score": -0.1,
                    "severity": "medium",
                }
            ]
        )
        recs = _anomaly_recommendations(df)
        assert len(recs) == 1
        assert recs[0].severity == "medium"

    def test_low_severity_not_included(self):
        df = _anomaly_df(
            [
                {
                    "node_id": "n3",
                    "timestamp": 3000,
                    "anomaly_score": -0.02,
                    "severity": "low",
                }
            ]
        )
        recs = _anomaly_recommendations(df)
        assert recs == []

    def test_one_rec_per_node(self):
        df = _anomaly_df(
            [
                {
                    "node_id": "node_001",
                    "timestamp": 1000,
                    "anomaly_score": -0.3,
                    "severity": "high",
                },
                {
                    "node_id": "node_001",
                    "timestamp": 2000,
                    "anomaly_score": -0.2,
                    "severity": "high",
                },
            ]
        )
        recs = _anomaly_recommendations(df)
        assert len(recs) == 1

    def test_worst_score_selected(self):
        df = _anomaly_df(
            [
                {
                    "node_id": "node_001",
                    "timestamp": 1000,
                    "anomaly_score": -0.3,
                    "severity": "high",
                },
                {
                    "node_id": "node_001",
                    "timestamp": 2000,
                    "anomaly_score": -0.5,
                    "severity": "high",
                },
            ]
        )
        recs = _anomaly_recommendations(df)
        assert recs[0].metadata["anomaly_score"] == pytest.approx(-0.5)

    def test_message_contains_node_id(self):
        df = _anomaly_df(
            [
                {
                    "node_id": "node_42",
                    "timestamp": 1000,
                    "anomaly_score": -0.2,
                    "severity": "high",
                }
            ]
        )
        recs = _anomaly_recommendations(df)
        assert "node_42" in recs[0].message


# ---------------------------------------------------------------------------
# _high_consumption_recommendations
# ---------------------------------------------------------------------------


class TestHighConsumptionRecommendations:
    def test_empty_df_returns_empty(self):
        assert _high_consumption_recommendations(_forecast_df([])) == []

    def test_above_threshold_produces_recommendation(self):
        df = _forecast_df(
            [{"node_id": "n1", "timestamp": 1000, "predicted_consumption": 900.0}]
        )
        recs = _high_consumption_recommendations(df)
        assert len(recs) == 1
        assert recs[0].type == "high_consumption"
        assert recs[0].severity == "high"

    def test_below_threshold_no_recommendation(self):
        df = _forecast_df(
            [{"node_id": "n1", "timestamp": 1000, "predicted_consumption": 500.0}]
        )
        recs = _high_consumption_recommendations(df)
        assert recs == []

    def test_message_contains_node_id(self):
        df = _forecast_df(
            [{"node_id": "node_77", "timestamp": 1000, "predicted_consumption": 950.0}]
        )
        recs = _high_consumption_recommendations(df)
        assert "node_77" in recs[0].message

    def test_one_rec_per_node(self):
        df = _forecast_df(
            [
                {"node_id": "n1", "timestamp": 1000, "predicted_consumption": 850.0},
                {"node_id": "n1", "timestamp": 2000, "predicted_consumption": 900.0},
            ]
        )
        recs = _high_consumption_recommendations(df)
        assert len(recs) == 1


# ---------------------------------------------------------------------------
# _load_shift_recommendations
# ---------------------------------------------------------------------------


class TestLoadShiftRecommendations:
    def test_empty_df_returns_empty(self):
        assert _load_shift_recommendations(_forecast_df([])) == []

    def test_peak_hours_trigger_recommendation(self):
        rows = [
            {
                "node_id": "n1",
                "timestamp": 1714896000000 + i * 3600000,
                "predicted_consumption": 100.0 + i * 50,
            }
            for i in range(10)
        ]
        df = _forecast_df(rows)
        recs = _load_shift_recommendations(df)
        assert len(recs) >= 1
        assert all(r.type == "load_shift" for r in recs)

    def test_recommendation_has_peak_hours_metadata(self):
        rows = [
            {
                "node_id": "n1",
                "timestamp": 1714896000000 + i * 3600000,
                "predicted_consumption": 100.0 + i * 50,
            }
            for i in range(10)
        ]
        recs = _load_shift_recommendations(_forecast_df(rows))
        assert "peak_hours" in recs[0].metadata
        assert "max_consumption_watts" in recs[0].metadata


# ---------------------------------------------------------------------------
# generate_recommendations
# ---------------------------------------------------------------------------


class TestGenerateRecommendations:
    def test_empty_inputs_return_empty(self):
        result = generate_recommendations(_anomaly_df([]), _forecast_df([]))
        assert result == []

    def test_high_consumption_suppresses_load_shift_for_same_node(self):
        forecast_rows = [
            {
                "node_id": "n1",
                "timestamp": 1714896000000 + i * 3600000,
                "predicted_consumption": 900.0 + i * 10,
            }
            for i in range(10)
        ]
        recs = generate_recommendations(_anomaly_df([]), _forecast_df(forecast_rows))
        types = {r.type for r in recs}
        assert "high_consumption" in types
        assert not any(r.type == "load_shift" and r.node_id == "n1" for r in recs)

    def test_combines_anomaly_and_forecast_recs(self):
        anomaly_rows = [
            {
                "node_id": "n1",
                "timestamp": 1000,
                "anomaly_score": -0.2,
                "severity": "high",
            }
        ]
        forecast_rows = [
            {"node_id": "n2", "timestamp": 1000, "predicted_consumption": 900.0}
        ]
        recs = generate_recommendations(
            _anomaly_df(anomaly_rows), _forecast_df(forecast_rows)
        )
        node_ids = {r.node_id for r in recs}
        assert "n1" in node_ids
        assert "n2" in node_ids
