"""
Energy Batch Pipeline (DAG)

This Airflow DAG:
1. Runs daily.
2. Runs Spark feature engineering first.
3. Runs Spark batch analytics after features are available.
4. Logs task run status through Airflow callbacks.

Dependencies:
- Spark feature engineering job #18
- Spark batch analytics job #19
"""

import logging
import os
import shlex
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

logger = logging.getLogger(__name__)

REPO_ROOT = Path(
    os.getenv("ENERGY_REPO_ROOT", str(Path(__file__).resolve().parents[1]))
)
SPARK_SUBMIT_BIN = os.getenv("SPARK_SUBMIT_BIN", "spark-submit")
POSTGRES_JDBC_PACKAGE = os.getenv(
    "POSTGRES_JDBC_PACKAGE",
    "org.postgresql:postgresql:42.6.0",
)


def spark_submit_command(script_path: str) -> str:
    """Build a spark-submit command that runs from the repository root."""
    return " ".join(
        [
            f"cd {shlex.quote(str(REPO_ROOT))}",
            "&&",
            shlex.quote(SPARK_SUBMIT_BIN),
            "--packages",
            shlex.quote(POSTGRES_JDBC_PACKAGE),
            shlex.quote(script_path),
        ]
    )


def log_task_start(context):
    """Log when an Airflow task starts."""
    task_instance = context["task_instance"]
    logger.info(
        "Starting %s.%s for run_id=%s try=%s",
        task_instance.dag_id,
        task_instance.task_id,
        context.get("run_id"),
        task_instance.try_number,
    )


def log_task_success(context):
    """Log successful Airflow task completion."""
    task_instance = context["task_instance"]
    logger.info(
        "Completed %s.%s with status=success run_id=%s try=%s",
        task_instance.dag_id,
        task_instance.task_id,
        context.get("run_id"),
        task_instance.try_number,
    )


def log_task_failure(context):
    """Log failed Airflow task completion."""
    task_instance = context["task_instance"]
    logger.error(
        "Completed %s.%s with status=failed run_id=%s try=%s exception=%r",
        task_instance.dag_id,
        task_instance.task_id,
        context.get("run_id"),
        task_instance.try_number,
        context.get("exception"),
    )


default_args = {
    "owner": "E2_Data_Intelligence",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "start_date": pendulum.datetime(2025, 1, 1, tz="UTC"),
    "email_on_failure": False,
    "email_on_retry": False,
    "on_execute_callback": log_task_start,
    "on_success_callback": log_task_success,
    "on_failure_callback": log_task_failure,
}

dag = DAG(
    "energy_batch_pipeline",
    default_args=default_args,
    description="Run daily Spark feature engineering and batch analytics jobs",
    schedule="0 1 * * *",
    catchup=False,
    tags=["E2", "Spark", "batch"],
)

feature_engineering_task = BashOperator(
    task_id="run_feature_engineering",
    bash_command=spark_submit_command("src/spark/feature_engineering.py"),
    dag=dag,
)

batch_analytics_task = BashOperator(
    task_id="run_batch_analytics",
    bash_command=spark_submit_command("src/spark/batch-energy-analytics.py"),
    dag=dag,
)

feature_engineering_task >> batch_analytics_task
