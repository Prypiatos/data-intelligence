"""Integration tests for the full Kafka ingestion pipeline (issue #34).

Requires all services running:
    docker compose up -d kafka mosquitto postgres influxdb

And the ingestion consumers running:
    python3 src/ingestion/mqtt_consumer.py
    python3 src/ingestion/kafka_consumer.py
"""

import json
import time

import paho.mqtt.client as mqtt
import psycopg2
from influxdb_client import InfluxDBClient

MQTT_HOST = "localhost"
POSTGRES_CONFIG = {
    "host": "localhost",
    "database": "energy_db",
    "user": "energy_user",
    "password": "energy_pass",
}

INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "energy-token-123"
INFLUX_ORG = "energy-org"
INFLUX_BUCKET = "energy_telemetry"

PIPELINE_WAIT = 5  # seconds for messages to traverse MQTT → Kafka → storage


def _publish(node_id: str, timestamp: int | None = None) -> dict:
    """Publish a single telemetry message via MQTT and return the payload."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(MQTT_HOST, 1883, 60)

    payload = {
        "node_id": node_id,
        "timestamp": timestamp if timestamp is not None else int(time.time() * 1000),
        "voltage": 230.0,
        "current": 1.5,
        "power": 345.0,
        "energy_wh": 1200.0,
    }

    client.publish(f"energy/nodes/{node_id}/telemetry", json.dumps(payload))
    client.disconnect()
    return payload


def _pg_fetch(node_id: str, timestamp: int) -> tuple | None:
    """Return the stored row for (node_id, timestamp) or None."""
    with psycopg2.connect(**POSTGRES_CONFIG) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT node_id, timestamp, voltage, current, power, energy_wh "
            "FROM telemetry_readings WHERE node_id = %s AND timestamp = %s",
            (node_id, timestamp),
        )
        return cur.fetchone()


def _influx_query(node_id: str, range_minutes: int = 10) -> list:
    """Return all InfluxDB records for node_id within the last range_minutes."""
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    query = (
        f'from(bucket: "{INFLUX_BUCKET}")'
        f"  |> range(start: -{range_minutes}m)"
        f'  |> filter(fn: (r) => r["node_id"] == "{node_id}")'
    )
    tables = client.query_api().query(query, org=INFLUX_ORG)
    return [r for t in tables for r in t.records]


# ---------------------------------------------------------------------------
# Test 1: full pipeline — MQTT → Kafka → PostgreSQL + InfluxDB
# ---------------------------------------------------------------------------


def test_full_pipeline_stores_correct_fields():
    """Published message should land in both databases with all fields intact."""
    node_id = f"pipeline_{int(time.time())}"
    payload = _publish(node_id)

    time.sleep(PIPELINE_WAIT)

    # PostgreSQL — verify all field values match what was published
    row = _pg_fetch(node_id, payload["timestamp"])
    assert row is not None, f"Row not found in PostgreSQL for {node_id}"
    assert row[0] == node_id
    assert row[1] == payload["timestamp"]
    assert abs(row[2] - 230.0) < 0.01  # voltage
    assert abs(row[3] - 1.5) < 0.01  # current
    assert abs(row[4] - 345.0) < 0.01  # power
    assert abs(row[5] - 1200.0) < 0.01  # energy_wh

    # InfluxDB — verify record exists with correct node tag
    records = _influx_query(node_id)
    assert len(records) > 0, f"No records found in InfluxDB for {node_id}"
    assert all(r.values["node_id"] == node_id for r in records)


# ---------------------------------------------------------------------------
# Test 2: buffered message — embedded timestamp must be preserved
# ---------------------------------------------------------------------------


def test_buffered_message_timestamp_preserved():
    """A message with an old embedded timestamp (buffered reading) must be stored
    with the original timestamp, not the time it arrived at the consumer."""
    node_id = f"buffered_{int(time.time())}"

    # Simulate a reading that was buffered 60 seconds ago
    buffered_ts = int((time.time() - 60) * 1000)
    _publish(node_id, timestamp=buffered_ts)

    time.sleep(PIPELINE_WAIT)

    row = _pg_fetch(node_id, buffered_ts)
    assert row is not None, "Buffered message not found in PostgreSQL"
    assert (
        row[1] == buffered_ts
    ), f"Timestamp was overwritten: expected {buffered_ts}, got {row[1]}"


# ---------------------------------------------------------------------------
# Test 3: duplicate messages — UNIQUE constraint prevents double storage
# ---------------------------------------------------------------------------


def test_duplicate_messages_stored_once():
    """Publishing the same message twice should result in exactly one DB row."""
    node_id = f"dup_{int(time.time())}"
    ts = int(time.time() * 1000)

    _publish(node_id, timestamp=ts)
    _publish(node_id, timestamp=ts)

    time.sleep(PIPELINE_WAIT)

    with psycopg2.connect(**POSTGRES_CONFIG) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM telemetry_readings WHERE node_id = %s AND timestamp = %s",
            (node_id, ts),
        )
        count = cur.fetchone()[0]

    assert count == 1, f"Expected 1 row for duplicate messages, got {count}"
