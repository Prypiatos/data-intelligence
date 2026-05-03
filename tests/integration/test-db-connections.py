import time

import pytest

from src.ingestion.db_writer import insert_telemetry
from src.ingestion.influx_writer import write_telemetry


def sample_data(node_id="test_node"):
    return {
        "node_id": node_id,
        "timestamp": int(time.time() * 1000),
        "voltage": 230.0,
        "current": 1.5,
        "power": 345.0,
        "energy_wh": 1200.0,
    }


def test_postgres_insert():
    data = sample_data("pg_test")

    result = insert_telemetry(data)

    assert result is True


def test_postgres_duplicate():
    data = sample_data("pg_dup")

    insert_telemetry(data)
    result = insert_telemetry(data)

    assert result is False


def test_influx_write():
    data = sample_data("influx_test")

    write_telemetry(data)

    assert True  # no exception = success


def test_high_volume_postgres():
    for i in range(20):
        data = sample_data(f"bulk_{i}")
        result = insert_telemetry(data)
        assert result is True


def test_high_volume_influx():
    for i in range(20):
        data = sample_data(f"bulk_influx_{i}")
        write_telemetry(data)

    assert True


def test_postgres_connection_failure():
    import psycopg2

    from src.ingestion import db_writer

    original_conn = db_writer.conn

    db_writer.conn.close()

    data = sample_data("fail_test")

    result = insert_telemetry(data)

    assert result is None

    db_writer.conn = original_conn