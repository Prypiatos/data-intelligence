"""Unit tests for the anomaly detection pipeline."""

import sys
import time
import types
from unittest.mock import MagicMock, patch

import pytest

# Mock kafka before importing pipeline
_kafka = types.ModuleType("kafka")
_kafka.KafkaConsumer = MagicMock
_kafka.KafkaProducer = MagicMock
_kafka_errors = types.ModuleType("kafka.errors")
_kafka_errors.KafkaError = Exception
_kafka.errors = _kafka_errors
sys.modules["kafka"] = _kafka
sys.modules["kafka.errors"] = _kafka_errors

from src.models.anomaly.pipeline import (  # noqa: E402
    ANOMALY_TYPE,
    _graduated_nodes,
    _is_learning_mode,
    _learning_mode_cache,
    _write_to_postgres,
)


@pytest.fixture(autouse=True)
def clear_learning_mode_cache():
    """Reset module-level learning mode state between tests."""
    _graduated_nodes.clear()
    _learning_mode_cache.clear()
    yield
    _graduated_nodes.clear()
    _learning_mode_cache.clear()


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

    def test_anomaly_type_is_consumption_anomaly(self):
        conn, cur = _make_conn()
        _write_to_postgres(conn, self._result())
        args = cur.execute.call_args.args[1]
        assert args[2] == "consumption_anomaly"

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
# run() — startup behaviour
# ---------------------------------------------------------------------------


class TestRunStartup:
    def test_starts_in_collection_mode_when_model_missing(self):
        """Pipeline should not crash when no model exists — enters collection mode."""
        mock_conn = MagicMock()
        mock_consumer = MagicMock()
        # Stop the consumer loop immediately after one iteration
        mock_consumer.__iter__ = MagicMock(return_value=iter([]))

        with patch(
            "src.models.anomaly.pipeline.psycopg2.connect", return_value=mock_conn
        ), patch(
            "src.models.anomaly.pipeline._build_consumer", return_value=mock_consumer
        ), patch(
            "src.models.anomaly.pipeline._build_producer", return_value=MagicMock()
        ), patch(
            "src.models.anomaly.pipeline.MODEL_PATH"
        ) as mock_path:

            mock_path.__truediv__ = lambda s, o: MagicMock(
                **{"exists.return_value": False}
            )
            # Should complete without SystemExit
            from src.models.anomaly import pipeline

            with patch.object(pipeline, "MODEL_PATH") as mp:
                mp.__truediv__ = lambda s, o: MagicMock(
                    **{"exists.return_value": False}
                )
                pipeline.run()  # must not raise


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


# ---------------------------------------------------------------------------
# _is_learning_mode
# ---------------------------------------------------------------------------


def _make_db_conn(first_seen_ms):
    cur = MagicMock()
    cur.fetchone.return_value = (
        (first_seen_ms,) if first_seen_ms is not None else (None,)
    )
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = lambda s: cur
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn


class TestIsLearningMode:
    def test_node_with_no_data_is_in_learning_mode(self):
        conn = _make_db_conn(None)
        assert _is_learning_mode(conn, "node_new") is True

    def test_node_with_recent_first_seen_is_in_learning_mode(self):
        first_seen_ms = int(time.time() * 1000) - 5 * 24 * 3600 * 1000  # 5 days ago
        conn = _make_db_conn(first_seen_ms)
        assert _is_learning_mode(conn, "node_recent") is True

    def test_node_older_than_30_days_is_graduated(self):
        first_seen_ms = int(time.time() * 1000) - 35 * 24 * 3600 * 1000  # 35 days ago
        conn = _make_db_conn(first_seen_ms)
        assert _is_learning_mode(conn, "node_old") is False

    def test_graduated_node_added_to_permanent_cache(self):
        first_seen_ms = int(time.time() * 1000) - 35 * 24 * 3600 * 1000
        conn = _make_db_conn(first_seen_ms)
        _is_learning_mode(conn, "node_grad")
        assert "node_grad" in _graduated_nodes

    def test_graduated_node_skips_db_on_second_call(self):
        _graduated_nodes.add("node_already_grad")
        conn = _make_db_conn(0)
        result = _is_learning_mode(conn, "node_already_grad")
        assert result is False
        conn.cursor.assert_not_called()

    def test_cache_returns_stored_result_within_ttl(self):
        _learning_mode_cache["node_cached"] = (time.time(), True)
        conn = _make_db_conn(0)
        result = _is_learning_mode(conn, "node_cached")
        assert result is True
        conn.cursor.assert_not_called()

    def test_expired_cache_hits_db(self):
        _learning_mode_cache["node_stale"] = (time.time() - 7200, True)  # 2 hours ago
        first_seen_ms = int(time.time() * 1000) - 5 * 24 * 3600 * 1000
        conn = _make_db_conn(first_seen_ms)
        result = _is_learning_mode(conn, "node_stale")
        assert result is True
        conn.cursor.assert_called_once()

    def test_learning_mode_result_stored_in_cache(self):
        first_seen_ms = int(time.time() * 1000) - 5 * 24 * 3600 * 1000
        conn = _make_db_conn(first_seen_ms)
        _is_learning_mode(conn, "node_store")
        assert "node_store" in _learning_mode_cache
        assert _learning_mode_cache["node_store"][1] is True
