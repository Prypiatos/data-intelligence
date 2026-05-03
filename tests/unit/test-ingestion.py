import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch

INGESTION_PATH = Path(__file__).resolve().parents[2] / "src" / "ingestion"
sys.path.insert(0, str(INGESTION_PATH))

mock_db_writer = types.ModuleType("db_writer")
mock_db_writer.insert_telemetry = Mock()
sys.modules["db_writer"] = mock_db_writer

mock_influx_writer = types.ModuleType("influx_writer")
mock_influx_writer.write_telemetry = Mock()
sys.modules["influx_writer"] = mock_influx_writer

from kafka_consumer import process_telemetry
from validator import validate_telemetry


def valid_telemetry():
    return {
        "node_id": "plug_01",
        "timestamp": 1777392332445,
        "voltage": 230.0,
        "current": 1.5,
        "power": 345.0,
        "energy_wh": 1200.0,
    }


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


@patch("kafka_consumer.write_telemetry")
@patch("kafka_consumer.insert_telemetry")
def test_process_telemetry_writes_to_postgres_and_influx(
    mock_insert_telemetry,
    mock_write_telemetry,
):
    data = valid_telemetry()
    mock_insert_telemetry.return_value = True

    result = process_telemetry(data)

    assert result is True
    mock_insert_telemetry.assert_called_once_with(data)
    mock_write_telemetry.assert_called_once_with(data)


@patch("kafka_consumer.write_telemetry")
@patch("kafka_consumer.insert_telemetry")
def test_duplicate_telemetry_skips_influx_write(
    mock_insert_telemetry,
    mock_write_telemetry,
):
    data = valid_telemetry()
    mock_insert_telemetry.return_value = False

    result = process_telemetry(data)

    assert result is True
    mock_insert_telemetry.assert_called_once_with(data)
    mock_write_telemetry.assert_not_called()


@patch("kafka_consumer.write_telemetry")
@patch("kafka_consumer.insert_telemetry")
def test_postgres_failure_returns_false_for_retry(
    mock_insert_telemetry,
    mock_write_telemetry,
):
    data = valid_telemetry()
    mock_insert_telemetry.return_value = None

    result = process_telemetry(data)

    assert result is False
    mock_insert_telemetry.assert_called_once_with(data)
    mock_write_telemetry.assert_not_called()


@patch("kafka_consumer.write_telemetry")
@patch("kafka_consumer.insert_telemetry")
def test_influx_failure_logs_warning_but_returns_true(
    mock_insert_telemetry,
    mock_write_telemetry,
    capsys,
):
    data = valid_telemetry()
    mock_insert_telemetry.return_value = True
    mock_write_telemetry.side_effect = Exception("influx down")

    result = process_telemetry(data)

    captured = capsys.readouterr()

    assert result is True
    assert "WARNING: InfluxDB write failed" in captured.out
    mock_insert_telemetry.assert_called_once_with(data)
    mock_write_telemetry.assert_called_once_with(data)


@patch("kafka_consumer.write_telemetry")
@patch("kafka_consumer.insert_telemetry")
def test_embedded_timestamp_is_preserved(
    mock_insert_telemetry,
    mock_write_telemetry,
):
    data = valid_telemetry()
    data["timestamp"] = 1777000000000
    mock_insert_telemetry.return_value = True

    process_telemetry(data)

    written_to_postgres = mock_insert_telemetry.call_args.args[0]
    written_to_influx = mock_write_telemetry.call_args.args[0]

    assert written_to_postgres["timestamp"] == 1777000000000
    assert written_to_influx["timestamp"] == 1777000000000
