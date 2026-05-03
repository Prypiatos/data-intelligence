import logging
from datetime import datetime

from airflow.decorators import dag, task

from src.validation.postgres_batch_validator import validate_telemetry_batch

@dag(
    dag_id = "data_validation_dag",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["validation", "great-expectations"],
)
def data_validation_dag():
    @task
    def validate_latest_interval(**context):
        """validate telemetry data for the latest interval and log the results."""
        start_time = context["data_interval_start"]
        end_time = context["data_interval_end"]

        summary = validate_telemetry_batch(start_time, end_time)

        logging.info("Validation summary: %s", summary)

        if summary["failed"] >0:
            raise ValueError(f"Telemetry validation failed: {summary}")
        
        return summary
    

    validate_latest_interval()


data_validation_dag()
