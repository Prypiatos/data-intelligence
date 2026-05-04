"""Integration tests for PostgreSQL and InfluxDB connections (issue #33).

Requires live database containers:
    docker compose up -d postgres influxdb
"""

import time

import psycopg2
import pytest

from src.ingestion import db_writer
from src.ingestion.db_writer import insert_telemetry
from src.ingestion.influx_writer import bucket, client, org, write_telemetry

# Unique prefix per test run so repeated runs don't interfere with count assertions
_RUN = int(time.time())


def sample_data(node_id: str = "test_node") -> dict:
    return {
        "node_id": node_id,
        "timestamp": int(time.time() * 1000),
        "voltage": 230.0,
        "current": 1.5,
        "power": 345.0,
        "energy_wh": 1200.0,
    }


def _pg_conn():
    """Fresh connection used for read-back verification."""
    return psycopg2.connect(
        host="localhost",
        database="energy_db",
        user="energy_user",
        password="energy_pass",
    )


def _restore_db_writer():
    """Reopen the db_writer module connection after a forced-close test."""
    new_conn = psycopg2.connect(
        host="localhost",
        database="energy_db",
        user="energy_user",
        password="energy_pass",
    )
    db_writer.conn = new_conn
    db_writer.cursor = new_conn.cursor()


# ---------------------------------------------------------------------------
# PostgreSQL — write + read
# ---------------------------------------------------------------------------


def test_postgres_write_and_read_back():
    data = sample_data(f"pg_readback_{_RUN}")
    result = insert_telemetry(data)
    assert result is True

    with _pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT node_id, voltage, current, power, energy_wh "
            "FROM telemetry_readings WHERE node_id = %s AND timestamp = %s",
            (data["node_id"], data["timestamp"]),
        )
        row = cur.fetchone()

    assert row is not None, "Inserted row not found in PostgreSQL"
    assert row[0] == data["node_id"]
    assert row[1] == pytest.approx(230.0)
    assert row[2] == pytest.approx(1.5)
    assert row[3] == pytest.approx(345.0)
    assert row[4] == pytest.approx(1200.0)


def test_postgres_duplicate_returns_false():
    data = sample_data(f"pg_dup_{_RUN}")
    insert_telemetry(data)
    result = insert_telemetry(data)
    assert result is False


def test_high_volume_postgres():
    prefix = f"pg_bulk_{_RUN}"
    for i in range(20):
        data = sample_data(f"{prefix}_{i}")
        result = insert_telemetry(data)
        assert result is True

    with _pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM telemetry_readings WHERE node_id LIKE %s",
            (f"{prefix}%",),
        )
        count = cur.fetchone()[0]

    assert count == 20


# ---------------------------------------------------------------------------
# PostgreSQL — connection failure and recovery (retry simulation)
# ---------------------------------------------------------------------------


def test_postgres_connection_failure_returns_none():
    db_writer.conn.close()
    result = insert_telemetry(sample_data(f"fail_{_RUN}"))
    assert result is None
    _restore_db_writer()


def test_postgres_recovers_after_reconnect():
    """Simulates a caller reconnecting and retrying after a failure."""
    db_writer.conn.close()
    insert_telemetry(sample_data(f"pre_retry_{_RUN}"))  # fails silently
    _restore_db_writer()

    result = insert_telemetry(sample_data(f"post_retry_{_RUN}"))
    assert result is True


# ---------------------------------------------------------------------------
# InfluxDB — write + read
# ---------------------------------------------------------------------------


def test_influx_write_and_read_back():
    node_id = f"influx_readback_{_RUN}"
    data = sample_data(node_id)
    write_telemetry(data)

    query_api = client.query_api()
    tables = query_api.query(
        f'from(bucket: "{bucket}")'
        f"  |> range(start: -1m)"
        f'  |> filter(fn: (r) => r["node_id"] == "{node_id}")'
        f"  |> limit(n: 1)",
        org=org,
    )
    records = [r for t in tables for r in t.records]
    assert len(records) > 0, "Written record not found in InfluxDB"


def test_high_volume_influx():
    node_id = f"influx_bulk_{_RUN}"
    base_ts = int(time.time() * 1000)
    for i in range(20):
        data = sample_data(node_id)
        data["timestamp"] = base_ts + i  # unique timestamps to avoid overwrite
        write_telemetry(data)

    query_api = client.query_api()
    tables = query_api.query(
        f'from(bucket: "{bucket}")'
        f"  |> range(start: -1m)"
        f'  |> filter(fn: (r) => r["node_id"] == "{node_id}")',
        org=org,
    )
    records = [r for t in tables for r in t.records]
    assert len(records) >= 20
