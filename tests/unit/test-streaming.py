"""Unit tests for Flink stream processor transformations and windowing logic."""

import json
from unittest.mock import Mock, patch

from src.streaming import telemetry_transforms as transforms


def valid_telemetry() -> dict:
    return {
        "node_id": "node_001",
        "timestamp": 1714496400000,
        "voltage": 230.0,
        "current": 2.5,
        "power": 575.0,
        "energy_wh": 10.5,
    }


def test_validate_message_accepts_valid_telemetry_json():
    payload = valid_telemetry()

    with patch.object(
        transforms,
        "validate_telemetry",
        return_value=(True, "Telemetry data is valid"),
    ):
        result = json.loads(transforms.validate_message(json.dumps(payload)))

    assert result["status"] == "valid"
    assert result["reason"] == "Telemetry data is valid"
    assert result["data"] == payload


def test_validate_message_rejects_empty_message():
    result = json.loads(transforms.validate_message(""))

    assert result == {
        "status": "invalid",
        "reason": "Empty message",
        "data": None,
    }


def test_validate_message_rejects_invalid_json():
    result = json.loads(transforms.validate_message("{bad json"))

    assert result == {
        "status": "invalid",
        "reason": "Invalid JSON",
        "data": None,
    }


def test_validate_message_rejects_invalid_telemetry_values():
    payload = valid_telemetry()
    payload["voltage"] = 999.0

    with patch.object(
        transforms,
        "validate_telemetry",
        return_value=(False, "Validation failed for 'voltage'"),
    ):
        result = json.loads(transforms.validate_message(json.dumps(payload)))

    assert result["status"] == "invalid"
    assert result["reason"] == "Validation failed for 'voltage'"
    assert result["data"] == payload


def test_timestamp_assigner_returns_record_timestamp():
    assigner = transforms.TelemetryTimestampAssigner()
    payload = valid_telemetry()

    timestamp = assigner.extract_timestamp(payload, record_timestamp=0)

    assert timestamp == payload["timestamp"]


def test_summarize_window_returns_window_bounds_and_record_count():
    window = Mock()
    window.start = 1000
    window.end = 3000

    context = Mock()
    context.window.return_value = window

    records = [valid_telemetry(), valid_telemetry()]
    result = transforms.SummarizeWindow().process("all", context, records)
    summary = json.loads(result[0])

    assert summary == {
        "window_start": 1000,
        "window_end": 3000,
        "record_count": 2,
    }


def test_window_records_uses_constant_key_and_two_second_tumbling_window():
    stream = Mock()
    keyed_stream = Mock()
    windowed_stream = Mock()
    stream.key_by.return_value = keyed_stream
    keyed_stream.window.return_value = windowed_stream

    with (
        patch.object(
            transforms.Time, "milliseconds", return_value="two_seconds"
        ) as mock_milliseconds,
        patch.object(
            transforms.TumblingEventTimeWindows,
            "of",
            return_value="window_spec",
        ) as mock_window_of,
    ):
        result = transforms.window_records(stream)

    key_function = stream.key_by.call_args.args[0]
    assert key_function(valid_telemetry()) == "all"
    mock_milliseconds.assert_called_once_with(transforms.WINDOW_SIZE_MS)
    mock_window_of.assert_called_once_with("two_seconds")
    keyed_stream.window.assert_called_once_with("window_spec")
    assert result is windowed_stream
