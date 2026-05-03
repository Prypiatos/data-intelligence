# Telemetry Validation

This module validates telemetry records using Great Expectations.

Rules checked:
- required fields: `node_id`, `timestamp`, `voltage`, `current`, `power`, `energy_wh`
- `node_id` must be a string
- `timestamp` must be a positive 13-digit epoch millisecond integer
- `voltage` must be between `200` and `250`
- `current` must be greater than `0`
- `power` must be greater than `0`
- `energy_wh` must be `0` or greater

## Run Locally

install dependencies:

```bash
pip install -r requirements.txt
```

run From the `data-intelligence` folder:

```bash
python3 -m src.validation.telemetry_expectations
```

## Airflow Validation DAG

The Airflow DAG in `dags/data-validation-dag.py` runs the telemetry validation
rules against PostgreSQL rows for each daily Airflow data interval.

Run Airflow locally from the `data-intelligence` folder:

```bash
docker compose build airflow
docker compose up postgres airflow
```

Open the Airflow UI:

```text
http://localhost:8081
```

Local development login:

```text
admin / admin
```

Trigger this DAG manually:

```text
data_validation_dag
```

Expected behavior:

- logs a validation summary with checked, passed, and failed row counts
- succeeds when no invalid telemetry rows are found
- fails the task when invalid telemetry rows are found
