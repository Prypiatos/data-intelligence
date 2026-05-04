import os

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor

from src.validation.telemetry_expectations import validate_telemetry_dataframe


def get_postgres_connection():
    """Create a PostgreSQL connection using environment variables."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "energy_db"),
        user=os.getenv("POSTGRES_USER", "energy_user"),
        password=os.getenv("POSTGRES_PASSWORD", "energy_pass"),
    )


def fetch_telemetry_batch(start_time, end_time):
    """Fetch telemetry rows created inside one validation interval."""
    query = """
        SELECT node_id, timestamp, voltage, current, power, energy_wh
        FROM telemetry_readings
        WHERE created_at >= %s
        AND created_at < %s
        ORDER BY created_at ASC;
    """

    with get_postgres_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, (start_time, end_time))
            return [dict(row) for row in cursor.fetchall()]


def validate_telemetry_batch(start_time, end_time):
    """Validate telemetry rows for one interval and return a summary."""
    records = fetch_telemetry_batch(start_time, end_time)
    checked = len(records)

    if not records:
        return {
            "start_time": str(start_time),
            "end_time": str(end_time),
            "checked": 0,
            "passed": 0,
            "failed": 0,
            "failures": [],
        }

    df = pd.DataFrame(records)
    validation_result = validate_telemetry_dataframe(df)

    if validation_result.success:
        return {
            "start_time": str(start_time),
            "end_time": str(end_time),
            "checked": checked,
            "passed": checked,
            "failed": 0,
            "failures": [],
        }

    # Map row index → first failure reason using GX's unexpected_index_list
    # (available because validate_telemetry_dataframe uses result_format="COMPLETE")
    failure_reasons: dict[int, str] = {}
    for result in validation_result.results:
        if result.success:
            continue
        config = result.expectation_config
        if config is None:
            continue
        col = config.kwargs.get("column", "table")
        reason = f"Validation failed for '{col}': {config.type}"
        unexpected_indices = (result.result or {}).get("unexpected_index_list") or []
        for idx in unexpected_indices:
            failure_reasons.setdefault(idx, reason)

    # Table-level failures (wrong column set) affect every row
    if not failure_reasons:
        failure_reasons = {i: "Telemetry validation failed" for i in range(checked)}

    failures = [
        {
            "node_id": records[i].get("node_id"),
            "timestamp": records[i].get("timestamp"),
            "reason": reason,
        }
        for i, reason in sorted(failure_reasons.items())
    ]

    failed = len(failures)
    return {
        "start_time": str(start_time),
        "end_time": str(end_time),
        "checked": checked,
        "passed": checked - failed,
        "failed": failed,
        "failures": failures,
    }
