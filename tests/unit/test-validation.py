"""Unit tests for Great Expectations telemetry validation rules."""

import great_expectations as gx

from src.validation.telemetry_expectations import (
    build_telemetry_suite,
    validate_telemetry,
)


def valid_telemetry() -> dict:
    return {
        "node_id": "node_001",
        "timestamp": 1714496400000,
        "voltage": 230.0,
        "current": 2.5,
        "power": 575.0,
        "energy_wh": 10.5,
    }


def assert_invalid(data: dict, expected_text: str):
    is_valid, message = validate_telemetry(data)

    assert is_valid is False
    assert expected_text in message


def test_valid_telemetry_passes_great_expectations_validation():
    is_valid, message = validate_telemetry(valid_telemetry())

    assert is_valid is True
    assert message == "Telemetry data is valid"


def test_missing_required_field_fails_validation():
    data = valid_telemetry()
    del data["voltage"]

    assert_invalid(data, "voltage")


def test_extra_unexpected_field_fails_validation():
    data = valid_telemetry()
    data["unexpected"] = "value"

    assert_invalid(data, "table")


def test_wrong_node_id_type_fails_validation():
    data = valid_telemetry()
    data["node_id"] = 123

    assert_invalid(data, "node_id")


def test_wrong_timestamp_type_fails_validation():
    data = valid_telemetry()
    data["timestamp"] = "1714496400000"

    assert_invalid(data, "timestamp")


def test_timestamp_outside_epoch_millisecond_range_fails_validation():
    data = valid_telemetry()
    data["timestamp"] = 123

    assert_invalid(data, "timestamp")


def test_voltage_below_allowed_range_fails_validation():
    data = valid_telemetry()
    data["voltage"] = 199.9

    assert_invalid(data, "voltage")


def test_voltage_above_allowed_range_fails_validation():
    data = valid_telemetry()
    data["voltage"] = 250.1

    assert_invalid(data, "voltage")


def test_zero_current_passes_validation():
    data = valid_telemetry()
    data["current"] = 0

    is_valid, _ = validate_telemetry(data)
    assert is_valid is True


def test_zero_power_passes_validation():
    data = valid_telemetry()
    data["power"] = 0

    is_valid, _ = validate_telemetry(data)
    assert is_valid is True


def test_negative_current_fails_validation():
    data = valid_telemetry()
    data["current"] = -1

    assert_invalid(data, "current")


def test_negative_power_fails_validation():
    data = valid_telemetry()
    data["power"] = -1

    assert_invalid(data, "power")


def test_negative_energy_wh_fails_validation():
    data = valid_telemetry()
    data["energy_wh"] = -1

    assert_invalid(data, "energy_wh")


def test_build_telemetry_suite_contains_required_rules():
    gx.get_context()
    suite = build_telemetry_suite()
    expectations = suite.expectations
    expectation_types = {expectation.__class__.__name__ for expectation in expectations}
    expectation_columns = {
        expectation.column
        for expectation in expectations
        if hasattr(expectation, "column")
    }

    assert len(expectations) == 12
    assert "ExpectTableColumnsToMatchSet" in expectation_types
    assert "ExpectColumnValuesToBeOfType" in expectation_types
    assert "ExpectColumnValuesToBeInTypeList" in expectation_types
    assert "ExpectColumnValuesToBeBetween" in expectation_types
    assert {
        "node_id",
        "timestamp",
        "voltage",
        "current",
        "power",
        "energy_wh",
    } <= expectation_columns
