# Spark Batch Jobs

## Batch Energy Analytics

File:

```text
src/spark/batch-energy-analytics.py
```

The job:

- reads `telemetry_readings` from PostgreSQL
- reads `node_metadata` from PostgreSQL
- joins metadata using `node_id`
- uses `node_metadata.location` as `division`
- converts epoch-millisecond timestamps to Spark timestamps
- aggregates hourly and daily energy metrics
- writes results to `energy_analytics_hourly` and `energy_analytics_daily`

## Required PostgreSQL Tables

Make sure PostgreSQL has these output tables before running the job:

- `energy_analytics_hourly`
- `energy_analytics_daily`

They are defined in:

```text
db/postgres/schema.sql
db/postgres/migrations/002_energy_analytics_tables.sql
```

## Run Locally With Installed Spark

Start PostgreSQL:

```bash
docker compose up -d postgres
```

Run from the repository root:

```bash
POSTGRES_HOST=localhost spark-submit \
  --packages org.postgresql:postgresql:42.6.0 \
  src/spark/batch-energy-analytics.py
```

## Notes

- The job writes with `.mode("append")`.
- The output tables use `UNIQUE (node_id, hour_start)` and `UNIQUE (node_id, date)` to prevent duplicate analytics rows.
- If the same source data is processed again, PostgreSQL may reject duplicate rows because of those unique constraints.
