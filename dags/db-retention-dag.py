import logging
import pendulum

from airflow.decorators import dag, task
from sqlalchemy import text

from src.api.dependencies import get_db_engine

RETENTION_DAYS = 30

# Tables with a millisecond epoch timestamp column
EPOCH_MS_TABLES = [
    "telemetry_readings",
    "node_events",
    "node_health",
    "anomaly_records",
    "forecasts",
]

# Tables with a created_at TIMESTAMP column
CREATED_AT_TABLES = [
    "energy_features",
    "energy_analytics_hourly",
    "energy_analytics_daily",
]


@dag(
    dag_id="db_retention_dag",
    schedule="@daily",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    tags=["maintenance", "retention"],
)
def db_retention_dag():
    @task
    def purge_old_records():
        engine = get_db_engine()
        cutoff_ms = int(
            (pendulum.now("UTC").subtract(days=RETENTION_DAYS)).timestamp() * 1000
        )
        cutoff_ts = pendulum.now("UTC").subtract(days=RETENTION_DAYS)

        total_deleted = 0
        with engine.begin() as conn:
            for table in EPOCH_MS_TABLES:
                result = conn.execute(
                    text(f"DELETE FROM {table} WHERE timestamp < :cutoff"),
                    {"cutoff": cutoff_ms},
                )
                logging.info("Deleted %d rows from %s", result.rowcount, table)
                total_deleted += result.rowcount

            for table in CREATED_AT_TABLES:
                result = conn.execute(
                    text(f"DELETE FROM {table} WHERE created_at < :cutoff"),
                    {"cutoff": cutoff_ts},
                )
                logging.info("Deleted %d rows from %s", result.rowcount, table)
                total_deleted += result.rowcount

        logging.info("Retention run complete. Total rows deleted: %d", total_deleted)
        return total_deleted

    purge_old_records()


db_retention_dag()
