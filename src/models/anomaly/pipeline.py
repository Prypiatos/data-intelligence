import json
import logging
import os
import signal
import sys
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
ANOMALY_TYPE = "theft_or_leakage"

POSTGRES_DSN = (
    f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
    f"port={os.getenv('POSTGRES_PORT', '5432')} "
    f"dbname={os.getenv('POSTGRES_DB', 'energy_db')} "
    f"user={os.getenv('POSTGRES_USER', 'energy_user')} "
    f"password={os.getenv('POSTGRES_PASSWORD', 'energy_pass')}"
)


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
