"""Unit tests for the anomaly detection model."""

import random

import pytest

from src.models.anomaly.model import AnomalyDetector, SEVERITY_THRESHOLDS

# Base timestamp: 2024-01-01 00:00:00 UTC (a Monday)
_BASE_TS_MS = 1_704_067_200_000
_HOUR_MS = 3_600_000


def _ts(day: int, hour: int) -> int:
    """Return epoch ms for a given day offset and hour of day."""
    return _BASE_TS_MS + day * 24 * _HOUR_MS + hour * _HOUR_MS


def _make_readings(n: int, seed: int = 42) -> list[dict]:
    """Generate readings active only during daytime hours (8am–10pm)."""
    rng = random.Random(seed)
    readings = []
    for i in range(n):
        hour = rng.randint(8, 22)
        day = i % 14
        readings.append(
            {
                "node_id": f"plug-{i % 5:02d}",
                "timestamp": _ts(day, hour),
                "voltage": 230.0,
                "current": 0.26,
                "power": 60.0,
                "energy_wh": 0.083,
            }
        )
    return readings


def _normal_reading(node_id: str = "plug-01", ts: int = None) -> dict:
    """A reading during normal operating hours (Monday 2pm, device on)."""
    return {
        "node_id": node_id,
        "timestamp": ts if ts is not None else _ts(0, 14),
        "voltage": 230.0,
        "current": 0.26,
        "power": 60.0,
        "energy_wh": 0.083,
    }


def _anomalous_reading(node_id: str = "plug-01", ts: int = None) -> dict:
    """A reading at an unusual hour (Monday 3am, device on when it never is)."""
    return {
        "node_id": node_id,
        "timestamp": ts if ts is not None else _ts(0, 3),
        "voltage": 230.0,
        "current": 0.26,
        "power": 60.0,
        "energy_wh": 0.083,
    }


def _fitted_detector(n: int = 300) -> AnomalyDetector:
    readings = _make_readings(n)
    detector = AnomalyDetector(contamination=0.05, n_estimators=100, random_state=42)
    detector.fit(readings)
    return detector


# ---------------------------------------------------------------------------
# fit / predict basics
# ---------------------------------------------------------------------------


class TestAnomalyDetectorFit:
    def test_fit_returns_self(self):
        readings = _make_readings(50)
        detector = AnomalyDetector()
        result = detector.fit(readings)
        assert result is detector

    def test_predict_before_fit_raises(self):
        detector = AnomalyDetector()
        with pytest.raises(RuntimeError, match="not fitted"):
            detector.predict([_normal_reading()])

    def test_predict_returns_one_result_per_reading(self):
        detector = _fitted_detector()
        results = detector.predict(_make_readings(5))
        assert len(results) == 5

    def test_predict_result_has_required_keys(self):
        detector = _fitted_detector()
        result = detector.predict([_normal_reading()])[0]
        assert {"node_id", "timestamp", "anomaly_score", "severity"} <= result.keys()

    def test_predict_preserves_node_id_and_timestamp(self):
        detector = _fitted_detector()
        ts = _ts(0, 14)
        reading = _normal_reading(node_id="main-03", ts=ts)
        result = detector.predict([reading])[0]
        assert result["node_id"] == "main-03"
        assert result["timestamp"] == ts


# ---------------------------------------------------------------------------
# Severity scoring
# ---------------------------------------------------------------------------


class TestSeverityScoring:
    def test_normal_readings_have_low_severity(self):
        """Daytime readings should not be flagged as high severity."""
        detector = _fitted_detector(n=400)
        readings = _make_readings(20, seed=99)
        results = detector.predict(readings)
        high_count = sum(1 for r in results if r["severity"] == "high")
        assert (
            high_count == 0
        ), f"{high_count} daytime readings incorrectly flagged as high"

    def test_anomalous_readings_flagged(self):
        """Device active at 3am should not score as normal when never active at night."""
        normal = _make_readings(300)
        detector = AnomalyDetector(
            contamination=0.05, n_estimators=100, random_state=42
        )
        detector.fit(normal)
        result = detector.predict([_anomalous_reading()])[0]
        assert (
            result["severity"] != "normal"
        ), f"Expected 3am reading to be flagged, got 'normal' (score={result['anomaly_score']})"

    def test_score_is_lower_for_unusual_hour(self):
        """Anomaly score should be lower for a device active at an unusual hour."""
        normal = _make_readings(300)
        detector = AnomalyDetector(
            contamination=0.05, n_estimators=100, random_state=42
        )
        detector.fit(normal)
        normal_score = detector.predict([_normal_reading()])[0]["anomaly_score"]
        anomaly_score = detector.predict([_anomalous_reading()])[0]["anomaly_score"]
        assert (
            anomaly_score < normal_score
        ), f"Expected anomaly score ({anomaly_score}) < normal score ({normal_score})"

    def test_severity_thresholds_order(self):
        assert (
            SEVERITY_THRESHOLDS["high"]
            < SEVERITY_THRESHOLDS["medium"]
            < SEVERITY_THRESHOLDS["low"]
        )

    def test_anomaly_score_is_float(self):
        detector = _fitted_detector()
        result = detector.predict([_normal_reading()])[0]
        assert isinstance(result["anomaly_score"], float)

    def test_severity_values_are_valid(self):
        detector = _fitted_detector()
        results = detector.predict(_make_readings(10))
        valid = {"high", "medium", "low", "normal"}
        for r in results:
            assert r["severity"] in valid


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_device_off_at_usual_hour_scores_without_crash(self):
        """Device off during normal hours — is_active=0 is a valid feature state."""
        detector = _fitted_detector()
        reading = _normal_reading()
        reading["power"] = 0.0
        reading["current"] = 0.0
        results = detector.predict([reading])
        assert len(results) == 1
        assert isinstance(results[0]["anomaly_score"], float)

    def test_single_reading_batch(self):
        detector = _fitted_detector()
        results = detector.predict([_normal_reading()])
        assert len(results) == 1

    def test_large_batch(self):
        detector = _fitted_detector()
        readings = _make_readings(500)
        results = detector.predict(readings)
        assert len(results) == 500

    def test_multiple_nodes_in_batch(self):
        detector = _fitted_detector()
        readings = [
            _normal_reading(node_id="plug-01"),
            _normal_reading(node_id="plug-02"),
            _normal_reading(node_id="main-01"),
        ]
        results = detector.predict(readings)
        node_ids = [r["node_id"] for r in results]
        assert node_ids == ["plug-01", "plug-02", "main-01"]

    def test_missing_power_field_raises(self):
        """A reading missing power (needed for is_active) should raise KeyError."""
        detector = _fitted_detector()
        incomplete = {
            "node_id": "plug-01",
            "timestamp": _ts(0, 14),
            "voltage": 230.0,
            "current": 0.26,
        }
        with pytest.raises(KeyError):
            detector.predict([incomplete])

    def test_missing_timestamp_raises(self):
        """A reading missing timestamp (needed for hour/day features) should raise."""
        detector = _fitted_detector()
        incomplete = {
            "node_id": "plug-01",
            "voltage": 230.0,
            "current": 0.26,
            "power": 60.0,
            "energy_wh": 0.083,
        }
        with pytest.raises((KeyError, Exception)):
            detector.predict([incomplete])


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------


class TestSaveLoad:
    def test_save_and_load_produces_same_scores(self, tmp_path):
        detector = _fitted_detector()
        reading = _normal_reading()
        score_before = detector.predict([reading])[0]["anomaly_score"]
        detector.save(tmp_path)
        loaded = AnomalyDetector.load(tmp_path)
        score_after = loaded.predict([reading])[0]["anomaly_score"]
        assert score_before == pytest.approx(score_after)

    def test_loaded_detector_can_predict(self, tmp_path):
        detector = _fitted_detector()
        detector.save(tmp_path)
        loaded = AnomalyDetector.load(tmp_path)
        results = loaded.predict([_normal_reading(), _anomalous_reading()])
        assert len(results) == 2
        assert all(isinstance(r["anomaly_score"], float) for r in results)

    def test_predict_before_fit_raises_after_load_from_empty(self, tmp_path):
        """Loading a detector that was never fitted should still raise on predict."""
        import pickle

        (tmp_path / "detector.pkl").write_bytes(
            pickle.dumps({"model": None, "scaler": None})
        )
        loaded = AnomalyDetector.load(tmp_path)
        with pytest.raises(RuntimeError, match="not fitted"):
            loaded.predict([_normal_reading()])
