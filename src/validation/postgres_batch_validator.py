import os

import psycopg2
from psycopg2.extras import RealDictCursor

from src.validation.telemetry_expectations import validate_telemetry


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
    failures = []

    for record in records:
        is_valid, reason = validate_telemetry(record)

        if not is_valid:
            failures.append(
                {
                    "node_id": record.get("node_id"),
                    "timestamp": record.get("timestamp"),
                    "reason": reason,
                }
            )

    checked = len(records)
    failed = len(failures)

    return {
        "start_time": str(start_time),
        "end_time": str(end_time),
        "checked": checked,
        "passed": checked - failed,
        "failed": failed,
        "failures": failures,
    }
