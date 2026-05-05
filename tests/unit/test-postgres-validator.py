"""Unit tests for the PostgreSQL batch validator."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.validation.postgres_batch_validator import (
    fetch_telemetry_batch,
    validate_telemetry_batch,
)

START = "2026-05-05 00:00:00"
END = "2026-05-05 01:00:00"

VALID_RECORD = {
    "node_id": "node_001",
    "timestamp": 1714800000000,
    "voltage": 230.0,
    "current": 2.5,
    "power": 575.0,
    "energy_wh": 10.5,
}


def _mock_conn(rows: list[dict]):
    cur = MagicMock()
    cur.fetchall.return_value = rows
    cur.__enter__ = lambda s: cur
    cur.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = lambda s: conn
    conn.__exit__ = MagicMock(return_value=False)
    return conn


# ---------------------------------------------------------------------------
# fetch_telemetry_batch
# ---------------------------------------------------------------------------

class TestFetchTelemetryBatch:
    def test_returns_list_of_dicts(self):
        with patch("src.validation.postgres_batch_validator.get_postgres_connection",
                   return_value=_mock_conn([VALID_RECORD])):
            result = fetch_telemetry_batch(START, END)
        assert isinstance(result, list)
        assert result[0]["node_id"] == "node_001"

    def test_returns_empty_list_when_no_rows(self):
        with patch("src.validation.postgres_batch_validator.get_postgres_connection",
                   return_value=_mock_conn([])):
            result = fetch_telemetry_batch(START, END)
        assert result == []

    def test_passes_time_params_to_query(self):
        conn = _mock_conn([])
        with patch("src.validation.postgres_batch_validator.get_postgres_connection",
                   return_value=conn):
            fetch_telemetry_batch(START, END)
        cur = conn.cursor.return_value
        call_args = cur.execute.call_args.args
        assert START in call_args[1]
        assert END in call_args[1]


# ---------------------------------------------------------------------------
# validate_telemetry_batch — empty
# ---------------------------------------------------------------------------

class TestValidateTelemetryBatchEmpty:
    def test_empty_records_returns_zero_counts(self):
        with patch("src.validation.postgres_batch_validator.fetch_telemetry_batch",
                   return_value=[]):
            result = validate_telemetry_batch(START, END)
        assert result["checked"] == 0
        assert result["passed"] == 0
        assert result["failed"] == 0
        assert result["failures"] == []

    def test_empty_result_has_time_fields(self):
        with patch("src.validation.postgres_batch_validator.fetch_telemetry_batch",
                   return_value=[]):
            result = validate_telemetry_batch(START, END)
        assert result["start_time"] == str(START)
        assert result["end_time"] == str(END)


# ---------------------------------------------------------------------------
# validate_telemetry_batch — all pass
# ---------------------------------------------------------------------------

class TestValidateTelemetryBatchAllPass:
    def test_all_valid_records_pass(self):
        mock_result = MagicMock()
        mock_result.success = True

        with patch("src.validation.postgres_batch_validator.fetch_telemetry_batch",
                   return_value=[VALID_RECORD, VALID_RECORD]):
            with patch("src.validation.postgres_batch_validator.validate_telemetry_dataframe",
                       return_value=mock_result):
                result = validate_telemetry_batch(START, END)

        assert result["checked"] == 2
        assert result["passed"] == 2
        assert result["failed"] == 0
        assert result["failures"] == []

    def test_result_schema_has_required_keys(self):
        mock_result = MagicMock()
        mock_result.success = True

        with patch("src.validation.postgres_batch_validator.fetch_telemetry_batch",
                   return_value=[VALID_RECORD]):
            with patch("src.validation.postgres_batch_validator.validate_telemetry_dataframe",
                       return_value=mock_result):
                result = validate_telemetry_batch(START, END)

        assert set(result.keys()) == {"start_time", "end_time", "checked", "passed", "failed", "failures"}


# ---------------------------------------------------------------------------
# validate_telemetry_batch — some fail
# ---------------------------------------------------------------------------

class TestValidateTelemetryBatchSomeFail:
    def _make_failed_result(self, col: str, bad_indices: list[int]):
        expectation_config = MagicMock()
        expectation_config.kwargs = {"column": col}
        expectation_config.type = "expect_column_values_to_be_between"

        row_result = MagicMock()
        row_result.success = False
        row_result.expectation_config = expectation_config
        row_result.result = {"unexpected_index_list": bad_indices}

        mock_validation = MagicMock()
        mock_validation.success = False
        mock_validation.results = [row_result]
        return mock_validation

    def test_failed_records_counted(self):
        bad_result = self._make_failed_result("voltage", [0])
        with patch("src.validation.postgres_batch_validator.fetch_telemetry_batch",
                   return_value=[VALID_RECORD, VALID_RECORD]):
            with patch("src.validation.postgres_batch_validator.validate_telemetry_dataframe",
                       return_value=bad_result):
                result = validate_telemetry_batch(START, END)

        assert result["failed"] == 1
        assert result["passed"] == 1
        assert len(result["failures"]) == 1

    def test_failure_contains_node_id_and_reason(self):
        bad_result = self._make_failed_result("voltage", [0])
        with patch("src.validation.postgres_batch_validator.fetch_telemetry_batch",
                   return_value=[VALID_RECORD]):
            with patch("src.validation.postgres_batch_validator.validate_telemetry_dataframe",
                       return_value=bad_result):
                result = validate_telemetry_batch(START, END)

        failure = result["failures"][0]
        assert "node_id" in failure
        assert "timestamp" in failure
        assert "reason" in failure
        assert "voltage" in failure["reason"]

    def test_table_level_failure_marks_all_rows(self):
        row_result = MagicMock()
        row_result.success = False
        row_result.expectation_config = None
        row_result.result = {}

        mock_validation = MagicMock()
        mock_validation.success = False
        mock_validation.results = [row_result]

        with patch("src.validation.postgres_batch_validator.fetch_telemetry_batch",
                   return_value=[VALID_RECORD, VALID_RECORD]):
            with patch("src.validation.postgres_batch_validator.validate_telemetry_dataframe",
                       return_value=mock_validation):
                result = validate_telemetry_batch(START, END)

        assert result["failed"] == 2
