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


def publish_telemetry(node_id):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(MQTT_HOST, 1883, 60)

    ts = int(time.time() * 1000)

    payload = {
        "node_id": node_id,
        "timestamp": ts,
        "voltage": 230.0,
        "current": 1.5,
        "power": 345.0,
        "energy_wh": 1200.0,
    }

    client.publish(f"energy/nodes/{node_id}/telemetry", json.dumps(payload))
    client.disconnect()

    return payload


def test_full_pipeline():
    node_id = "pipeline_test"
    payload = publish_telemetry(node_id)

    # wait for pipeline to process
    time.sleep(5)

    # check PostgreSQL
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT node_id, timestamp FROM telemetry_readings WHERE node_id = %s",
        (node_id,),
    )

    rows = cursor.fetchall()

    assert len(rows) >= 1
    assert rows[0][0] == node_id

    conn.close()

    # check InfluxDB
    client = InfluxDBClient(
        url=INFLUX_URL,
        token=INFLUX_TOKEN,
        org=INFLUX_ORG,
    )

    query = f'''
    from(bucket: "{INFLUX_BUCKET}")
      |> range(start: -10m)
      |> filter(fn: (r) => r["node_id"] == "{node_id}")
    '''

    tables = client.query_api().query(query)

    assert len(tables) > 0


def test_buffered_messages():
    node_id = "buffer_test"

    for _ in range(5):
        publish_telemetry(node_id)

    time.sleep(5)

    conn = psycopg2.connect(**POSTGRES_CONFIG)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM telemetry_readings WHERE node_id = %s",
        (node_id,),
    )

    count = cursor.fetchone()[0]

    assert count >= 1

    conn.close()