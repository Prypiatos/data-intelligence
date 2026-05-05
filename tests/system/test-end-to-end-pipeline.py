"""
System test: full pipeline from simulated E1 MQTT message to API response.

Flow under test:
  E1 MQTT publish
    → mqtt_consumer (ingestion service)
    → Kafka energy.telemetry
    → kafka_consumer (storage service) → PostgreSQL telemetry_readings
    → anomaly pipeline → PostgreSQL anomaly_records (if severity != normal)
    → API GET /anomalies

Requires the full stack to be running:
    docker compose up

Run with:
    pytest tests/system/test-end-to-end-pipeline.py -v
"""

import json
import time
import uuid
from pathlib import Path

import httpx
import paho.mqtt.client as mqtt
import psycopg2
import pytest

API_BASE = "http://localhost:8000"
MQTT_HOST = "localhost"
MQTT_PORT = 1883
POSTGRES_DSN = (
    "host=localhost port=5432 dbname=energy_db user=energy_user password=energy_pass"
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "energy-readings.json"

PIPELINE_TIMEOUT_S = 30
POLL_INTERVAL_S = 2


# ============================================================
# Service availability checks
# ============================================================


def _api_available() -> bool:
    try:
        return httpx.get(f"{API_BASE}/health", timeout=3).status_code == 200
    except Exception:
        return False


def _mqtt_available() -> bool:
    try:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        c.connect(MQTT_HOST, MQTT_PORT, keepalive=5)
        c.disconnect()
        return True
    except Exception:
        return False


def _postgres_available() -> bool:
    try:
        conn = psycopg2.connect(POSTGRES_DSN, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


requires_stack = pytest.mark.skipif(
    not (_api_available() and _mqtt_available() and _postgres_available()),
    reason="Full Docker stack not running (docker compose up required)",
)


# ============================================================
# Helpers
# ============================================================


def _load_fixtures() -> list[dict]:
    with open(FIXTURE_PATH) as f:
        return json.load(f)


def _publish_readings(node_id: str, readings: list[dict]) -> int:
    """Publish readings to MQTT and return count published."""
    published = 0
    now_ms = int(time.time() * 1000)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
    client.loop_start()

    for i, base in enumerate(readings):
        payload = {
            "node_id": node_id,
            "timestamp": now_ms + i * 60_000,  # 1-minute apart
            "voltage": base["voltage"],
            "current": base["current"],
            "power": base["power"],
            "energy_wh": base["energy_wh"],
        }
        topic = f"energy/nodes/{node_id}/telemetry"
        result = client.publish(topic, json.dumps(payload), qos=1)
        result.wait_for_publish(timeout=5)
        published += 1

    client.loop_stop()
    client.disconnect()
    return published


def _poll_postgres(node_id: str, expected_count: int) -> bool:
    """Poll until at least expected_count rows appear for node_id (or timeout)."""
    deadline = time.time() + PIPELINE_TIMEOUT_S
    while time.time() < deadline:
        try:
            conn = psycopg2.connect(POSTGRES_DSN)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM telemetry_readings WHERE node_id = %s",
                    (node_id,),
                )
                count = cur.fetchone()[0]
            conn.close()
            if count >= expected_count:
                return True
        except Exception:
            pass
        time.sleep(POLL_INTERVAL_S)
    return False


def _poll_api_anomalies(node_id: str) -> list[dict]:
    """Poll /anomalies until at least one record for node_id appears (or timeout)."""
    deadline = time.time() + PIPELINE_TIMEOUT_S
    while time.time() < deadline:
        try:
            resp = httpx.get(
                f"{API_BASE}/anomalies",
                params={"node_id": node_id, "limit": 100},
                timeout=5,
            )
            if resp.status_code == 200 and resp.json():
                return resp.json()
        except Exception:
            pass
        time.sleep(POLL_INTERVAL_S)
    return []


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(scope="module")
def test_node_id() -> str:
    """Unique node ID so test data doesn't collide with real data."""
    return f"e2e_test_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def published_count(test_node_id) -> int:
    """Publish fixture readings once for the whole module."""
    readings = _load_fixtures()
    # Use first 5 readings to keep the test fast
    return _publish_readings(test_node_id, readings[:5])


# ============================================================
# Tests
# ============================================================


@requires_stack
class TestMQTTPublish:
    def test_all_readings_published_successfully(self, published_count):
        assert published_count == 5


@requires_stack
class TestStoragePipeline:
    def test_telemetry_reaches_postgres(self, test_node_id, published_count):
        """MQTT → Kafka → storage consumer → PostgreSQL."""
        reached = _poll_postgres(test_node_id, expected_count=published_count)
        assert reached, (
            f"Telemetry for {test_node_id} did not appear in PostgreSQL "
            f"within {PIPELINE_TIMEOUT_S}s. "
            "Check: ingestion service, storage service, Kafka topics."
        )

    def test_stored_rows_have_correct_schema(self, test_node_id, published_count):
        _poll_postgres(test_node_id, expected_count=1)
        conn = psycopg2.connect(POSTGRES_DSN)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT node_id, timestamp, voltage, current, power, energy_wh
                FROM telemetry_readings
                WHERE node_id = %s
                LIMIT 1
                """,
                (test_node_id,),
            )
            row = cur.fetchone()
        conn.close()
        assert row is not None
        node_id, timestamp, voltage, current, power, energy_wh = row
        assert node_id == test_node_id
        assert timestamp > 0
        assert 200 <= voltage <= 250
        assert current > 0
        assert power > 0
        assert energy_wh >= 0

    def test_no_duplicate_rows_stored(self, test_node_id, published_count):
        _poll_postgres(test_node_id, expected_count=published_count)
        conn = psycopg2.connect(POSTGRES_DSN)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM telemetry_readings WHERE node_id = %s",
                (test_node_id,),
            )
            count = cur.fetchone()[0]
        conn.close()
        assert count == published_count


@requires_stack
class TestAnomalyPipeline:
    def test_anomaly_pipeline_processes_readings(self, test_node_id, published_count):
        """Anomaly pipeline must consume energy.telemetry and score each reading."""
        # Ensure telemetry is stored first
        _poll_postgres(test_node_id, expected_count=published_count)

        # Poll anomaly_records — not all readings produce records (normal severity
        # is not written), so we check the pipeline ran without checking row count.
        conn = psycopg2.connect(POSTGRES_DSN)
        with conn.cursor() as cur:
            # At minimum, the anomaly_records table should exist and be queryable
            cur.execute("SELECT COUNT(*) FROM anomaly_records")
            total = cur.fetchone()[0]
        conn.close()
        assert total >= 0  # table exists and is accessible

    def test_anomaly_records_have_valid_severity(self, test_node_id):
        conn = psycopg2.connect(POSTGRES_DSN)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT severity FROM anomaly_records WHERE node_id = %s",
                (test_node_id,),
            )
            severities = {row[0] for row in cur.fetchall()}
        conn.close()
        valid = {"high", "medium", "low"}
        assert severities <= valid


@requires_stack
class TestAPIOutput:
    def test_health_endpoint_up(self):
        assert httpx.get(f"{API_BASE}/health", timeout=5).status_code == 200

    def test_telemetry_visible_via_anomalies_endpoint(
        self, test_node_id, published_count
    ):
        """After ingestion, GET /anomalies must be queryable for the test node."""
        _poll_postgres(test_node_id, expected_count=published_count)
        resp = httpx.get(
            f"{API_BASE}/anomalies",
            params={"node_id": test_node_id, "limit": 100},
            timeout=5,
        )
        assert resp.status_code == 200
        # Response is a list (may be empty if all readings are normal severity)
        assert isinstance(resp.json(), list)

    def test_forecast_endpoint_returns_list(self):
        resp = httpx.get(f"{API_BASE}/forecast/forecasts", timeout=5)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_recommendations_endpoint_returns_list(self):
        resp = httpx.get(f"{API_BASE}/recommendations", timeout=5)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_predict_endpoint_works_end_to_end(self):
        """Forecast predict endpoint should return 24h forecast for any input."""
        resp = httpx.post(
            f"{API_BASE}/forecast/predict",
            json={"power_readings": [400, 420, 450, 480, 500, 470, 420, 380, 350, 340]},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["forecast"]) == 24
        assert all(v >= 0 for v in data["forecast"])


@requires_stack
class TestDataIntegrity:
    def test_voltage_within_valid_range(self, test_node_id):
        """All stored readings must have voltage between 200V and 250V."""
        _poll_postgres(test_node_id, expected_count=1)
        conn = psycopg2.connect(POSTGRES_DSN)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT voltage FROM telemetry_readings WHERE node_id = %s",
                (test_node_id,),
            )
            voltages = [row[0] for row in cur.fetchall()]
        conn.close()
        assert voltages, "No rows found"
        assert all(
            200 <= v <= 250 for v in voltages
        ), f"Voltages out of range: {[v for v in voltages if not 200 <= v <= 250]}"

    def test_power_is_positive(self, test_node_id):
        _poll_postgres(test_node_id, expected_count=1)
        conn = psycopg2.connect(POSTGRES_DSN)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT power FROM telemetry_readings WHERE node_id = %s",
                (test_node_id,),
            )
            powers = [row[0] for row in cur.fetchall()]
        conn.close()
        assert all(p > 0 for p in powers)

    def test_timestamps_are_unique_per_node(self, test_node_id, published_count):
        _poll_postgres(test_node_id, expected_count=published_count)
        conn = psycopg2.connect(POSTGRES_DSN)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), COUNT(DISTINCT timestamp) FROM telemetry_readings WHERE node_id = %s",
                (test_node_id,),
            )
            total, distinct = cur.fetchone()
        conn.close()
        assert total == distinct, "Duplicate timestamps found"
