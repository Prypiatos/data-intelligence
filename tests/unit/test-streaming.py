"""Unit tests for Flink stream processor transformations and windowing logic."""

import json
import sys
import types
from unittest.mock import Mock, patch

# pyflink requires a full Flink/JVM installation not present in the unit test
# environment — mock it before importing telemetry_transforms, same pattern as
# test-ingestion.py uses for kafka.
_pyflink = types.ModuleType("pyflink")
_pyflink_common = types.ModuleType("pyflink.common")
_pyflink_common.Duration = Mock()
_pyflink_common.Time = Mock()
_pyflink_common.WatermarkStrategy = Mock()
_pyflink_datastream = types.ModuleType("pyflink.datastream")
_pyflink_datastream_functions = types.ModuleType("pyflink.datastream.functions")
_pyflink_datastream_functions.ProcessWindowFunction = object
_pyflink_datastream_window = types.ModuleType("pyflink.datastream.window")
_pyflink_datastream_window.TumblingEventTimeWindows = Mock()
_pyflink_common_watermark = types.ModuleType("pyflink.common.watermark_strategy")
_pyflink_common_watermark.TimestampAssigner = object
sys.modules["pyflink"] = _pyflink
sys.modules["pyflink.common"] = _pyflink_common
sys.modules["pyflink.datastream"] = _pyflink_datastream
sys.modules["pyflink.datastream.functions"] = _pyflink_datastream_functions
sys.modules["pyflink.datastream.window"] = _pyflink_datastream_window
sys.modules["pyflink.common.watermark_strategy"] = _pyflink_common_watermark

from src.streaming import telemetry_transforms as transforms  # noqa: E402


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
    result = transforms.SummarizeWindow().process("node_001", context, records)
    summary = json.loads(result[0])

    assert summary["window_start"] == 1000
    assert summary["window_end"] == 3000
    assert summary["record_count"] == 2
    assert summary["node_id"] == "node_001"


def test_summarize_window_computes_avg_and_max_power():
    window = Mock()
    window.start = 0
    window.end = 2000

    context = Mock()
    context.window.return_value = window

    r1 = valid_telemetry()
    r1["power"] = 400.0
    r2 = valid_telemetry()
    r2["power"] = 600.0

    result = transforms.SummarizeWindow().process("node_001", context, [r1, r2])
    summary = json.loads(result[0])

    assert summary["avg_power"] == 500.0
    assert summary["max_power"] == 600.0


def test_summarize_window_computes_avg_voltage_current_energy():
    window = Mock()
    window.start = 0
    window.end = 2000

    context = Mock()
    context.window.return_value = window

    r1 = valid_telemetry()
    r1["voltage"] = 220.0
    r1["current"] = 1.0
    r1["energy_wh"] = 10.0
    r2 = valid_telemetry()
    r2["voltage"] = 240.0
    r2["current"] = 3.0
    r2["energy_wh"] = 20.0

    result = transforms.SummarizeWindow().process("node_001", context, [r1, r2])
    summary = json.loads(result[0])

    assert summary["avg_voltage"] == 230.0
    assert summary["avg_current"] == 2.0
    assert summary["avg_energy_wh"] == 15.0


def test_validate_stream_maps_validate_message():
    stream = Mock()
    transforms.validate_stream(stream)
    stream.map.assert_called_once_with(transforms.validate_message)


def test_extract_valid_records_filters_invalid():
    valid = json.dumps({"status": "valid", "data": valid_telemetry()})
    invalid = json.dumps({"status": "invalid", "data": None, "reason": "bad"})

    stream = Mock()
    mapped1 = Mock()
    mapped2 = Mock()
    filtered = Mock()
    stream.map.return_value = mapped1
    mapped1.filter.return_value = mapped2
    mapped2.map.return_value = filtered

    result = transforms.extract_valid_records(stream)

    assert result is filtered
    filter_fn = mapped1.filter.call_args.args[0]
    assert filter_fn(json.loads(valid)) is True
    assert filter_fn(json.loads(invalid)) is False


def test_assign_event_time_calls_assign_timestamps():
    stream = Mock()
    transforms.assign_event_time(stream)
    stream.assign_timestamps_and_watermarks.assert_called_once()


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
    assert key_function(valid_telemetry()) == "node_001"
    mock_milliseconds.assert_called_once_with(transforms.WINDOW_SIZE_MS)
    mock_window_of.assert_called_once_with("two_seconds")
    keyed_stream.window.assert_called_once_with("window_spec")
    assert result is windowed_stream
