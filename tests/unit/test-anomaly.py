"""Unit tests for the anomaly detection model (issue #40)."""

import random

import pytest

from src.models.anomaly.model import AnomalyDetector, SEVERITY_THRESHOLDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_readings(n: int, seed: int = 42, anomaly_fraction: float = 0.0) -> list[dict]:
    """Generate varied normal readings with optional anomaly injections."""
    rng = random.Random(seed)
    readings = []
    for i in range(n):
        is_anomaly = anomaly_fraction > 0 and rng.random() < anomaly_fraction
        voltage = rng.uniform(220, 240)
        if is_anomaly:
            current = rng.uniform(18, 30)
            power = voltage * current * rng.uniform(0.3, 0.5)
        else:
            current = rng.uniform(0.5, 8.0)
            power = voltage * current * rng.uniform(0.85, 0.99)
        readings.append(
            {
                "node_id": f"plug-{i % 5:02d}",
                "timestamp": 1_000_000 + i * 60_000,
                "voltage": round(voltage, 2),
                "current": round(current, 3),
                "power": round(power, 2),
                "energy_wh": round(power / 60, 4),
            }
        )
    return readings


def _normal_reading(node_id: str = "plug-01", ts: int = 1_000_000) -> dict:
    return {
        "node_id": node_id,
        "timestamp": ts,
        "voltage": 230.0,
        "current": 2.0,
        "power": 450.0,
        "energy_wh": 7.5,
    }


def _anomalous_reading(node_id: str = "plug-01", ts: int = 2_000_000) -> dict:
    """Theft-style anomaly: very high current, low power factor."""
    return {
        "node_id": node_id,
        "timestamp": ts,
        "voltage": 230.0,
        "current": 28.0,
        "power": 900.0,
        "energy_wh": 55.0,
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
        reading = _normal_reading(node_id="main-03", ts=99999)
        result = detector.predict([reading])[0]
        assert result["node_id"] == "main-03"
        assert result["timestamp"] == 99999


# ---------------------------------------------------------------------------
# Severity scoring
# ---------------------------------------------------------------------------


class TestSeverityScoring:
    def test_normal_readings_have_low_severity(self):
        """Normal readings should not be flagged as high severity."""
        detector = _fitted_detector(n=400)
        # Score a batch of typical readings
        readings = _make_readings(20, seed=99)
        results = detector.predict(readings)
        high_count = sum(1 for r in results if r["severity"] == "high")
        # With contamination=0.05 we allow a small fraction; none should be high
        assert (
            high_count == 0
        ), f"{high_count} normal readings incorrectly flagged as high"

    def test_anomalous_readings_flagged(self):
        """Clear outliers should not be scored as normal."""
        normal = _make_readings(300)
        detector = AnomalyDetector(
            contamination=0.05, n_estimators=100, random_state=42
        )
        detector.fit(normal)

        result = detector.predict([_anomalous_reading()])[0]
        assert (
            result["severity"] != "normal"
        ), f"Expected anomaly to be flagged, got 'normal' (score={result['anomaly_score']})"

    def test_score_is_lower_for_anomaly_than_normal(self):
        """Anomaly score (decision function) should be lower for outliers."""
        normal = _make_readings(300)
        detector = AnomalyDetector(
            contamination=0.05, n_estimators=100, random_state=42
        )
        detector.fit(normal)

        normal_score = detector.predict([_normal_reading(ts=1)])[0]["anomaly_score"]
        anomaly_score = detector.predict([_anomalous_reading(ts=2)])[0]["anomaly_score"]
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
    def test_dead_circuit_zero_current(self):
        """Zero current/power should not cause division-by-zero in power_factor calc."""
        detector = _fitted_detector()
        reading = {
            "node_id": "plug-01",
            "timestamp": 1,
            "voltage": 230.0,
            "current": 0.0,
            "power": 0.0,
            "energy_wh": 0.0,
        }
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
            _normal_reading(node_id="plug-01", ts=1),
            _normal_reading(node_id="plug-02", ts=2),
            _normal_reading(node_id="main-01", ts=3),
        ]
        results = detector.predict(readings)
        node_ids = [r["node_id"] for r in results]
        assert node_ids == ["plug-01", "plug-02", "main-01"]

    def test_out_of_range_high_voltage(self):
        """Extremely high voltage should be scoreable without crashing."""
        detector = _fitted_detector()
        reading = {
            "node_id": "plug-01",
            "timestamp": 1,
            "voltage": 10_000.0,
            "current": 100.0,
            "power": 500_000.0,
            "energy_wh": 9999.0,
        }
        results = detector.predict([reading])
        assert len(results) == 1

    def test_out_of_range_negative_values(self):
        """Negative readings (sensor glitch) should not crash the model."""
        detector = _fitted_detector()
        reading = {
            "node_id": "plug-01",
            "timestamp": 1,
            "voltage": -5.0,
            "current": -1.0,
            "power": -10.0,
            "energy_wh": -0.1,
        }
        results = detector.predict([reading])
        assert len(results) == 1


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
        # Manually save a blank state
        import pickle

        (tmp_path / "detector.pkl").write_bytes(
            pickle.dumps({"model": None, "scaler": None})
        )
        loaded = AnomalyDetector.load(tmp_path)
        with pytest.raises(RuntimeError, match="not fitted"):
            loaded.predict([_normal_reading()])
