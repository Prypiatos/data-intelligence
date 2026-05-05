"""Unit tests for the ingestion and storage layer (issue #29)."""

import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch

# Must come before ingestion imports — kafka_consumer uses bare imports
INGESTION_PATH = Path(__file__).resolve().parents[2] / "src" / "ingestion"
sys.path.insert(0, str(INGESTION_PATH))

mock_kafka = types.ModuleType("kafka")
mock_kafka.KafkaConsumer = Mock()  # type: ignore[attr-defined]
sys.modules["kafka"] = mock_kafka

mock_db_writer = types.ModuleType("db_writer")
mock_db_writer.insert_telemetry = Mock()  # type: ignore[attr-defined]
mock_db_writer.insert_stream_summary = Mock()  # type: ignore[attr-defined]
sys.modules["db_writer"] = mock_db_writer

mock_influx_writer = types.ModuleType("influx_writer")
mock_influx_writer.write_telemetry = Mock()  # type: ignore[attr-defined]
sys.modules["influx_writer"] = mock_influx_writer

from kafka_consumer import consume_stream_results, process_telemetry  # noqa: E402
from validator import validate_telemetry  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def valid_telemetry() -> dict:
    return {
        "node_id": "plug_01",
        "timestamp": 1777392332445,
        "voltage": 230.0,
        "current": 1.5,
        "power": 345.0,
        "energy_wh": 1200.0,
    }


# ---------------------------------------------------------------------------
# Validator — message parsing
# ---------------------------------------------------------------------------


def test_valid_telemetry_passes_validation():
    is_valid, message = validate_telemetry(valid_telemetry())
    assert is_valid is True
    assert message == "Valid telemetry message"


def test_invalid_timestamp_rejected():
    data = valid_telemetry()
    data["timestamp"] = 123
    is_valid, message = validate_telemetry(data)
    assert is_valid is False
    assert "timestamp" in message


def test_invalid_voltage_rejected():
    data = valid_telemetry()
    data["voltage"] = 180.0
    is_valid, message = validate_telemetry(data)
    assert is_valid is False
    assert "voltage" in message


def test_current_zero_rejected():
    data = valid_telemetry()
    data["current"] = 0
    is_valid, message = validate_telemetry(data)
    assert is_valid is False
    assert "current" in message


def test_power_zero_rejected():
    data = valid_telemetry()
    data["power"] = 0
    is_valid, message = validate_telemetry(data)
    assert is_valid is False
    assert "power" in message


def test_missing_required_field_rejected():
    data = valid_telemetry()
    del data["voltage"]
    is_valid, message = validate_telemetry(data)
    assert is_valid is False
    assert "required" in message.lower() or "field" in message.lower()


def test_extra_field_rejected():
    data = valid_telemetry()
    data["extra_key"] = "unexpected"
    is_valid, message = validate_telemetry(data)
    assert is_valid is False


# ---------------------------------------------------------------------------
# process_telemetry — DB write logic
# ---------------------------------------------------------------------------


@patch("kafka_consumer.write_telemetry")
@patch("kafka_consumer.insert_telemetry")
def test_invalid_telemetry_skips_db_writes(mock_insert, mock_write):
    """Invalid messages are dropped (returns True) without touching the DB."""
    bad_data = valid_telemetry()
    bad_data["voltage"] = 999.0  # out of range

    result = process_telemetry(bad_data)

    assert result is True
    mock_insert.assert_not_called()
    mock_write.assert_not_called()


@patch("kafka_consumer.write_telemetry")
@patch("kafka_consumer.insert_telemetry")
def test_process_telemetry_writes_to_postgres_and_influx(mock_insert, mock_write):
    data = valid_telemetry()
    mock_insert.return_value = True

    result = process_telemetry(data)

    assert result is True
    mock_insert.assert_called_once_with(data)
    mock_write.assert_called_once_with(data)


@patch("kafka_consumer.write_telemetry")
@patch("kafka_consumer.insert_telemetry")
def test_duplicate_telemetry_skips_influx_write(mock_insert, mock_write):
    data = valid_telemetry()
    mock_insert.return_value = False

    result = process_telemetry(data)

    assert result is True
    mock_insert.assert_called_once_with(data)
    mock_write.assert_not_called()


@patch("kafka_consumer.write_telemetry")
@patch("kafka_consumer.insert_telemetry")
def test_postgres_failure_returns_false_for_retry(mock_insert, mock_write):
    data = valid_telemetry()
    mock_insert.return_value = None

    result = process_telemetry(data)

    assert result is False
    mock_insert.assert_called_once_with(data)
    mock_write.assert_not_called()


@patch("kafka_consumer.write_telemetry")
@patch("kafka_consumer.insert_telemetry")
def test_influx_failure_does_not_fail_processing(mock_insert, mock_write):
    """InfluxDB failure should be swallowed — message is committed, not retried."""
    data = valid_telemetry()
    mock_insert.return_value = True
    mock_write.side_effect = Exception("influx down")

    result = process_telemetry(data)

    assert result is True
    mock_insert.assert_called_once_with(data)
    mock_write.assert_called_once_with(data)


# ---------------------------------------------------------------------------
# Buffered message handling — embedded timestamp preserved
# ---------------------------------------------------------------------------


@patch("kafka_consumer.write_telemetry")
@patch("kafka_consumer.insert_telemetry")
def test_embedded_timestamp_is_preserved(mock_insert, mock_write):
    """Buffered messages carry their original timestamp — it must not be overwritten."""
    data = valid_telemetry()
    data["timestamp"] = 1777000000000
    mock_insert.return_value = True

    process_telemetry(data)

    assert mock_insert.call_args.args[0]["timestamp"] == 1777000000000
    assert mock_write.call_args.args[0]["timestamp"] == 1777000000000


# ---------------------------------------------------------------------------
# consume_stream_results — stream summary persistence
# ---------------------------------------------------------------------------


def _stream_summary():
    return {
        "node_id": "plug_01",
        "window_start": 1777392330000,
        "window_end": 1777392332000,
        "avg_power": 345.0,
        "max_power": 380.0,
        "record_count": 4,
    }


def _make_message(value):
    msg = Mock()
    msg.value = value
    return msg


@patch("kafka_consumer.insert_stream_summary")
@patch("kafka_consumer.create_results_consumer")
def test_consume_stream_results_inserts_and_commits(mock_create, mock_insert):
    summary = _stream_summary()
    mock_insert.return_value = True
    mock_consumer = Mock()
    mock_consumer.__iter__ = Mock(return_value=iter([_make_message(summary)]))
    mock_create.return_value = mock_consumer

    consume_stream_results()

    mock_insert.assert_called_once_with(summary)
    mock_consumer.commit.assert_called_once()


@patch("kafka_consumer.insert_stream_summary")
@patch("kafka_consumer.create_results_consumer")
def test_consume_stream_results_skips_commit_on_insert_failure(mock_create, mock_insert):
    mock_insert.return_value = None
    mock_consumer = Mock()
    mock_consumer.__iter__ = Mock(return_value=iter([_make_message(_stream_summary())]))
    mock_create.return_value = mock_consumer

    consume_stream_results()

    mock_insert.assert_called_once()
    mock_consumer.commit.assert_not_called()


@patch("kafka_consumer.insert_stream_summary")
@patch("kafka_consumer.create_results_consumer")
def test_consume_stream_results_handles_exception_without_crashing(mock_create, mock_insert):
    mock_insert.side_effect = Exception("unexpected error")
    mock_consumer = Mock()
    mock_consumer.__iter__ = Mock(return_value=iter([_make_message(_stream_summary())]))
    mock_create.return_value = mock_consumer

    consume_stream_results()  # must not raise

    mock_consumer.commit.assert_not_called()
