# E2 Integration Guide — E4 (Infrastructure & Operations)

This document covers everything E4 needs to deploy and operate the E2 data intelligence stack in production.

---

## What E2 provides

E2 owns the application code, Dockerfiles, and a `docker-compose.yml` for local development reference. E4 owns production orchestration — Kubernetes, networking, secrets management, scaling, and monitoring.

---

## Services

### Custom-built images (built from this repo)

| Service | Dockerfile | Role |
|---|---|---|
| `api` | `docker/Dockerfile.api` | FastAPI REST API — the integration point for E3 |
| `ingestion` | `docker/Dockerfile.ingestion` | MQTT → Kafka bridge — the integration point for E1 |
| `storage` | `docker/Dockerfile.storage` | Kafka → PostgreSQL + InfluxDB writer |
| `anomaly` | `docker/Dockerfile.anomaly` | Kafka consumer — runs anomaly detection, writes to PostgreSQL |
| `streaming` | `docker/Dockerfile.streaming` | PyFlink stream processing job |
| `airflow` | `docker/Dockerfile.airflow` | Airflow scheduler + webserver (model retraining DAGs) |

> `docker/Dockerfile.batch-pipeline` also exists — this is a Spark batch image used by Airflow task runners, not a long-running service. It has no compose entry and is not deployed standalone.

### Third-party images (no build required)

| Service | Image | Role |
|---|---|---|
| `postgres` | `postgres:16` | Primary database |
| `influxdb` | `influxdb:2.7` | Time-series metrics store |
| `kafka` | `confluentinc/cp-kafka:7.5.0` | Message broker |
| `mosquitto` | `eclipse-mosquitto:2` | MQTT broker (E1 devices connect here) |
| `mlflow` | `ghcr.io/mlflow/mlflow` | ML experiment tracking |

---

## Startup order

Services have hard `depends_on` conditions — bring them up in this order:

```
kafka
                    ├── ingestion  (also needs mosquitto healthy)
                    ├── storage    (also needs postgres + influxdb healthy)
                    ├── anomaly    (also needs postgres healthy)
                    └── streaming

postgres ──────────┬── mlflow
                   ├── airflow
                   ├── storage
                   ├── anomaly
                   └── api ←── also needs kafka + influxdb healthy

mosquitto ─────────── ingestion

influxdb ──────────── storage, api

```

Kafka topics are created automatically on first use (`KAFKA_AUTO_CREATE_TOPICS_ENABLE=true`).

---

## Ports

| Service | Internal port | Exposed port | Who connects |
|---|---|---|---|
| `api` | 8000 | **8000** | E3 frontend |
| `mosquitto` | 1883 | **1883** | E1 devices (MQTT) |
| `mosquitto` | 9001 | 9001 | MQTT over WebSocket (optional) |
| `postgres` | 5432 | 5432 | Internal only |
| `influxdb` | 8086 | **8086** | E4 Grafana |
| `kafka` | 9092 | 9092 | Internal only |
| `mlflow` | 5000 | **5001** | Admin UI |
| `airflow` | 8080 | **8081** | Admin UI |

**Externally reachable in production:** port 8000 (API for E3), port 1883 (MQTT for E1 devices), and port 8086 (InfluxDB for E4 Grafana). Everything else should be internal-only behind the network boundary.

> **macOS note:** Port 5000 conflicts with AirPlay — MLflow is mapped to 5001. In production use any free port.

---

## Environment variables

Create a `.env` file (or inject via secrets manager). All custom services load from it via `env_file: .env`.

### Required — change all of these in production

| Variable | Dev default | Description |
|---|---|---|
| `POSTGRES_PASSWORD` | `energy_pass` | PostgreSQL password |
| `POSTGRES_USER` | `energy_user` | PostgreSQL user |
| `POSTGRES_DB` | `energy_db` | PostgreSQL database name |
| `DOCKER_INFLUXDB_INIT_PASSWORD` | `admin12345` | InfluxDB admin password |
| `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN` | `energy-token-123` | InfluxDB init token |
| `INFLUXDB_TOKEN` | `your-influxdb-token` | Token used by app services to write to InfluxDB — **must exactly match `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN`** or writes silently fail |
| `AIRFLOW_ADMIN_PASSWORD` | `changeme` | Airflow admin UI password |

### Set for production environment

| Variable | Description |
|---|---|
| `KAFKA_ADVERTISED_LISTENERS` | Update the `EXTERNAL://` listener to the server's real IP/hostname. Dev value is `EXTERNAL://localhost:9092` which only works locally. |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allowed origins for the API (E3's frontend URL). Default allows all origins. |

### Optional tuning

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Set to `WARNING` in production to reduce log volume |
| `FORECAST_HORIZON_HOURS` | `24` | Hours ahead to forecast |
| `HIGH_CONSUMPTION_THRESHOLD` | `800` | Watts threshold for high-consumption recommendations |
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | Already correct for internal Docker networking |

---

## Persistent volumes

| Volume | Used by | What's stored |
|---|---|---|
| `postgres_data` | postgres | All relational data (telemetry, anomalies, forecasts, MLflow metadata) |
| `influxdb_data` | influxdb | Time-series metrics |
| `kafka_data` | kafka | Message log |
| `mlflow_artifacts` | mlflow | Model artifacts, experiment files |
| `mosquitto_data` / `mosquitto_logs` | mosquitto | MQTT persistence and logs |
| `airflow_data` | airflow | DAG run data |
| `./models` (bind mount) | api, anomaly, airflow | Trained model files |

**The `./models` bind mount is critical.** The API loads the LSTM model from `models/lstm_model.pth` at startup. Airflow writes updated model files to `models/` after each retraining run. In production, replace this bind mount with a named shared persistent volume accessible to both `api` and `airflow`.

**Dev-only bind mount to remove:** `streaming` also mounts the entire repo (`.:/app`) in `docker-compose.yml` for hot-reloading. Remove this in production — the image already contains the source code.

---

## Schema initialisation

PostgreSQL schema is auto-applied on first start via:
```
./db/postgres/schema.sql → /docker-entrypoint-initdb.d/01-schema.sql
```

This only runs on a **fresh data volume**. If `postgres_data` already exists, the init script does not re-run. To re-initialise:
```bash
docker volume rm <project>_postgres_data
```

---

## Health checks

Container-level Docker healthchecks are configured for:

| Service | Method |
|---|---|
| `postgres` | `pg_isready` |
| `influxdb` | `GET /ping` |
| `kafka` | `kafka-broker-api-versions` |
| `mosquitto` | `mosquitto_pub` test publish |

These services do **not** have container-level Docker healthchecks and should be monitored externally: `api`, `ingestion`, `storage`, `anomaly`, `streaming`, `mlflow`, `airflow`.

The API exposes two monitoring endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness probe → `{"status": "healthy"}` — use as load balancer health probe |
| `GET /metrics` | Prometheus metrics — point your Prometheus scraper here |

Prometheus scrape config:
```yaml
scrape_configs:
  - job_name: e2-api
    static_configs:
      - targets: ['api:8000']
    metrics_path: /metrics
```

---

## Build

```bash
# Build all custom images
docker compose build

# Build a specific image
docker compose build api
docker compose build ingestion
docker compose build storage
docker compose build anomaly
docker compose build streaming
docker compose build airflow
```

Image names produced:
- `data-intelligence-api`
- `data-intelligence-ingestion`
- `data-intelligence-storage`
- `data-intelligence-anomaly`
- `data-intelligence-streaming`
- `data-intelligence-airflow`

---

## Kafka topics

Topics are created automatically on first use:

| Topic | Producers | Consumers |
|---|---|---|
| `energy.telemetry` | ingestion | storage, anomaly, streaming |
| `energy.telemetry.results` | streaming | storage (persists to `stream_summaries`; exposed via `GET /stream/summary`) |

Partitions: 1. Replication factor: 1 (increase both for HA).

---

## Airflow DAGs

| DAG ID | Schedule | What it does |
|---|---|---|
| `model_retraining_pipeline` | Weekly (Mon 02:00) | Retrains LSTM forecasting model, logs to MLflow, saves to `models/` |
| `energy_batch_pipeline` | Daily (01:00) | Runs Spark feature engineering and batch analytics |
| `data_validation_dag` | Daily | Validates data quality in PostgreSQL |

Airflow admin UI: `http://<host>:8081` — credentials set via `AIRFLOW_ADMIN_PASSWORD`.

Trigger the `model_retraining_pipeline` DAG manually after first boot to generate the initial `lstm_model.pth` before the API serves predictions.

---

## Model files

| File | Used by | What happens without it |
|---|---|---|
| `models/lstm_model.pth` | api | API starts but serves low-quality predictions until the model is trained |
| `models/anomaly/detector.pkl` | anomaly | Anomaly pipeline trains a fresh model on first run from available data |

---

## Grafana integration

E4 connects Grafana to two E2 data sources: InfluxDB (raw sensor telemetry) and Prometheus (API metrics).

### InfluxDB data source

| Setting | Value |
|---|---|
| URL | `http://influxdb:8086` (if Grafana is on the same Docker network) or `http://<ec2-host>:8086` (if external) |
| Token | value of `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN` in `.env` |
| Organisation | `energy-org` |
| Default bucket | `energy_telemetry` |

**InfluxDB data schema** — what E2 writes:

| Field | Type | Description |
|---|---|---|
| Measurement | — | `telemetry` |
| Tag: `node_id` | string | Device/meter identifier (e.g. `node_001`) |
| Field: `voltage` | float | Volts |
| Field: `current` | float | Amps |
| Field: `power` | float | Watts |
| Field: `energy_wh` | float | Watt-hours |
| Timestamp | milliseconds | Unix epoch ms — set `precision` to `ms` in Grafana flux queries |

Example Flux query for power over time per node:
```flux
from(bucket: "energy_telemetry")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "telemetry")
  |> filter(fn: (r) => r._field == "power")
  |> filter(fn: (r) => r.node_id == "node_001")
```

**Important:** `INFLUXDB_TOKEN` in `.env` must exactly match `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN`. The `.env.example` ships with a placeholder (`your-influxdb-token`) — if this is not updated before first boot, all E2 writes to InfluxDB will silently fail and Grafana will show an empty bucket.

### Prometheus data source

| Setting | Value |
|---|---|
| URL | `http://api:8000` (internal) or `http://<ec2-host>:8000` (external) |
| Metrics path | `/metrics` |

Use for dashboards showing API request rate, latency, and error rate by endpoint.

Prometheus scrape config (add to E4's `prometheus.yml`):
```yaml
scrape_configs:
  - job_name: e2-api
    static_configs:
      - targets: ['api:8000']
    metrics_path: /metrics
```

### PostgreSQL data source (optional)

Grafana's PostgreSQL plugin can query E2 tables directly for business dashboards:

| Table | Useful for |
|---|---|
| `anomaly_records` | Anomaly count per node, severity distribution over time |
| `stream_summaries` | Near-real-time avg/peak power per node |
| `forecasts` | Forecast vs actual consumption charts |
| `telemetry_readings` | Historical raw readings (use with caution — large table) |

Connection details: use the same `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` values from `.env`. PostgreSQL port 5432 does **not** need to be publicly exposed — Grafana should be on the same Docker network.

---

## Known constraints

- **Kafka external listener**: Dev config advertises `localhost:9092` as the external address. Update `KAFKA_ADVERTISED_LISTENERS` with the server's real IP before deploying.
- **Single-node Kafka**: `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1`. Increase broker count and replication factor for HA.
- **No TLS**: MQTT (1883) and API (8000) are unencrypted. Terminate TLS at a load balancer or ingress in production.
- **Streaming bind mount**: `streaming` mounts `.:/app` in compose — dev only. Remove in production.
- **Model volume**: `./models` is a bind mount in compose. Replace with a named shared volume in production so `api` and `airflow` can both access it.

