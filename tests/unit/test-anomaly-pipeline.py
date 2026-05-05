"""Unit tests for the anomaly detection pipeline."""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# Mock kafka before importing pipeline
_kafka = types.ModuleType("kafka")
_kafka.KafkaConsumer = MagicMock
_kafka.KafkaProducer = MagicMock
sys.modules["kafka"] = _kafka

from src.models.anomaly.pipeline import _write_to_postgres, ANOMALY_TYPE  # noqa: E402

# ---------------------------------------------------------------------------
# _write_to_postgres
# ---------------------------------------------------------------------------


def _make_conn():
    cur = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = lambda s: cur
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


class TestWriteToPostgres:
    def _result(self, severity="high", score=-0.2):
        return {
            "node_id": "node_001",
            "timestamp": 1714800000000,
            "anomaly_score": score,
            "severity": severity,
        }

    def test_executes_insert(self):
        conn, cur = _make_conn()
        _write_to_postgres(conn, self._result())
        assert cur.execute.called

    def test_inserts_correct_values(self):
        conn, cur = _make_conn()
        result = self._result(severity="medium", score=-0.1)
        _write_to_postgres(conn, result)
        args = cur.execute.call_args.args[1]
        assert args[0] == "node_001"
        assert args[1] == 1714800000000
        assert args[2] == ANOMALY_TYPE
        assert args[3] == -0.1
        assert args[4] == "medium"

    def test_commits_after_insert(self):
        conn, cur = _make_conn()
        _write_to_postgres(conn, self._result())
        conn.commit.assert_called_once()

    def test_anomaly_type_is_theft_or_leakage(self):
        conn, cur = _make_conn()
        _write_to_postgres(conn, self._result())
        args = cur.execute.call_args.args[1]
        assert args[2] == "theft_or_leakage"

    def test_high_severity_written(self):
        conn, cur = _make_conn()
        _write_to_postgres(conn, self._result(severity="high", score=-0.2))
        args = cur.execute.call_args.args[1]
        assert args[4] == "high"

    def test_low_severity_written(self):
        conn, cur = _make_conn()
        _write_to_postgres(conn, self._result(severity="low", score=-0.03))
        args = cur.execute.call_args.args[1]
        assert args[4] == "low"


# ---------------------------------------------------------------------------
# run() — model not found path
# ---------------------------------------------------------------------------


class TestRunModelNotFound:
    def test_exits_when_model_missing(self):
        with patch("src.models.anomaly.pipeline.MODEL_PATH") as mock_path:
            mock_path.__truediv__ = lambda s, o: MagicMock(
                **{"exists.return_value": False}
            )
            with pytest.raises(SystemExit):
                from src.models.anomaly import pipeline

                with patch.object(pipeline, "MODEL_PATH") as mp:
                    (mp / "detector.pkl").exists.return_value = False
                    with patch("sys.exit", side_effect=SystemExit):
                        pipeline.run()


# ---------------------------------------------------------------------------
# _build_consumer / _build_producer
# ---------------------------------------------------------------------------


class TestBuildConsumerProducer:
    def test_build_consumer_uses_correct_topic(self):
        with patch("src.models.anomaly.pipeline.KafkaConsumer") as mock:
            from src.models.anomaly.pipeline import _build_consumer, INPUT_TOPIC

            _build_consumer()
            mock.assert_called_once()
            assert mock.call_args.args[0] == INPUT_TOPIC

    def test_build_producer_called_with_bootstrap_servers(self):
        with patch("src.models.anomaly.pipeline.KafkaProducer") as mock:
            from src.models.anomaly.pipeline import _build_producer

            _build_producer()
            mock.assert_called_once()
            assert "bootstrap_servers" in mock.call_args.kwargs
