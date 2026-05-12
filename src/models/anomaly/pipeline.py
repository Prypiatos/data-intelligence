import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

import psycopg2
from kafka import KafkaConsumer, KafkaProducer

from .model import AnomalyDetector

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
INPUT_TOPIC = "energy.telemetry"
OUTPUT_TOPIC = "energy.anomalies"
GROUP_ID = "anomaly-detection-group"
MODEL_PATH = Path(os.getenv("ANOMALY_MODEL_PATH", "models/anomaly"))
ANOMALY_TYPE = "consumption_anomaly"
LEARNING_PERIOD_DAYS = int(os.getenv("LEARNING_PERIOD_DAYS", "30"))
_LEARNING_PERIOD_MS = LEARNING_PERIOD_DAYS * 24 * 3600 * 1000
_CACHE_TTL_SEC = 3600  # recheck learning mode once per hour per node

POSTGRES_DSN = (
    f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
    f"port={os.getenv('POSTGRES_PORT', '5432')} "
    f"dbname={os.getenv('POSTGRES_DB', 'energy_db')} "
    f"user={os.getenv('POSTGRES_USER', 'energy_user')} "
    f"password={os.getenv('POSTGRES_PASSWORD', 'energy_pass')}"
)

# Nodes that have passed the learning period — never revert, so cache permanently
_graduated_nodes: set = set()
# Cache: node_id -> (check_time, is_learning_mode) — stores the actual result, not just the timestamp
_learning_mode_cache: dict = {}


def _is_learning_mode(conn, node_id: str) -> bool:
    """Return True if the node has less than LEARNING_PERIOD_DAYS of data."""
    if node_id in _graduated_nodes:
        return False

    now = time.time()
    cached = _learning_mode_cache.get(node_id)
    if cached and now - cached[0] < _CACHE_TTL_SEC:
        return cached[1]

    with conn.cursor() as cur:
        cur.execute(
            "SELECT MIN(timestamp) FROM telemetry_readings WHERE node_id = %s",
            (node_id,),
        )
        row = cur.fetchone()

    if not row or row[0] is None:
        _learning_mode_cache[node_id] = (now, True)
        return True

    if int(now * 1000) - row[0] >= _LEARNING_PERIOD_MS:
        _graduated_nodes.add(node_id)
        _learning_mode_cache.pop(node_id, None)
        logger.info("Node %s graduated from learning mode", node_id)
        return False

    _learning_mode_cache[node_id] = (now, True)
    return True


def _build_consumer() -> KafkaConsumer:
    return KafkaConsumer(
        INPUT_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=GROUP_ID,
        auto_offset_reset="earliest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )


def _build_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )


def _write_to_postgres(conn, result: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO anomaly_records (node_id, timestamp, anomaly_type, score, severity)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                result["node_id"],
                result["timestamp"],
                ANOMALY_TYPE,
                result["anomaly_score"],
                result["severity"],
            ),
        )
    conn.commit()


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not (MODEL_PATH / "detector.pkl").exists():
        logger.error(
            "Model not found at %s. Run `python -m src.models.anomaly.trainer` first.",
            MODEL_PATH,
        )
        sys.exit(1)

    detector = AnomalyDetector.load(MODEL_PATH)
    logger.info("Loaded anomaly detector from %s", MODEL_PATH)

    consumer = _build_consumer()
    producer = _build_producer()
    conn = psycopg2.connect(POSTGRES_DSN)
    logger.info("Pipeline started — consuming from %s", INPUT_TOPIC)

    def _shutdown(sig, frame):
        logger.info("Shutting down...")
        consumer.close()
        producer.close()
        conn.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    for message in consumer:
        try:
            reading = message.value
            node_id = reading.get("node_id")

            if _is_learning_mode(conn, node_id):
                logger.debug("Node %s in learning mode — skipping anomaly detection", node_id)
                continue

            results = detector.predict([reading])
            result = results[0]

            if result["severity"] != "normal":
                _write_to_postgres(conn, result)

                event = {
                    "node_id": result["node_id"],
                    "timestamp": result["timestamp"],
                    "anomaly_type": ANOMALY_TYPE,
                    "anomaly_score": result["anomaly_score"],
                    "severity": result["severity"],
                }
                producer.send(OUTPUT_TOPIC, value=event)
                logger.info("Anomaly detected: %s", event)

        except Exception as e:
            logger.error("Error processing message: %s", e)


if __name__ == "__main__":
    run()
