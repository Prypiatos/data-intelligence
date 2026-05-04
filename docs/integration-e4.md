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

### Third-party images (no build required)

| Service | Image | Role |
|---|---|---|
| `postgres` | `postgres:16` | Primary database |
| `influxdb` | `influxdb:2.7` | Time-series metrics store |
| `redis` | `redis:7` | Cache |
| `kafka` | `confluentinc/cp-kafka:7.5.0` | Message broker |
| `zookeeper` | `confluentinc/cp-zookeeper:7.5.0` | Kafka coordination |
| `mosquitto` | `eclipse-mosquitto:2` | MQTT broker (E1 devices connect here) |
| `mlflow` | `ghcr.io/mlflow/mlflow` | ML experiment tracking |
| `flink-jobmanager` | `flink:1.17.1-scala_2.12-java11` | Flink cluster job manager |
| `flink-taskmanager` | `flink:1.17.1-scala_2.12-java11` | Flink cluster task manager |

---

## Startup order

Services have hard dependencies — bring them up in this order:

```
zookeeper
    └── kafka (waits for zookeeper)
            └── kafka-init (one-shot: creates topics, exits)
                    ├── ingestion
                    ├── storage
                    ├── anomaly
                    └── streaming

postgres ──────────────────────────────────────┐
mosquitto                                       ├── api
influxdb                                        ├── storage
redis                                           ├── anomaly
                                                ├── mlflow
                                                └── airflow

flink-jobmanager
    └── flink-taskmanager
```

`kafka-init` is a one-shot init container — it creates Kafka topics and exits. All stream consumers depend on it completing successfully before starting.

---

## Ports

| Service | Internal port | Exposed port | Who connects |
|---|---|---|---|
| `api` | 8000 | **8000** | E3 frontend |
| `mosquitto` | 1883 | **1883** | E1 devices (MQTT) |
| `mosquitto` | 9001 | 9001 | MQTT over WebSocket (optional) |
| `postgres` | 5432 | 5432 | Internal only |
| `influxdb` | 8086 | 8086 | Internal only |
| `redis` | 6379 | 6379 | Internal only |
| `kafka` | 9092 | 9092 | Internal only |
| `mlflow` | 5000 | **5001** | Admin UI |
| `airflow` | 8080 | **8081** | Admin UI |
| `flink-jobmanager` | 8081 | **8082** | Admin UI |

**Externally reachable in production:** port 8000 (API for E3) and port 1883 (MQTT for E1 devices). Everything else should be internal-only.

> **macOS note:** Port 5000 conflicts with AirPlay. MLflow is mapped to 5001 — keep this in production or pick any free port.

---

## Environment variables

Create a `.env` file (or equivalent secrets store). All services load from it via `env_file: .env`.

### Required — change these in production

| Variable | Default (dev) | Description |
|---|---|---|
| `POSTGRES_PASSWORD` | `energy_pass` | PostgreSQL password — **change this** |
| `POSTGRES_USER` | `energy_user` | PostgreSQL user |
| `POSTGRES_DB` | `energy_db` | PostgreSQL database name |
| `DOCKER_INFLUXDB_INIT_PASSWORD` | `admin12345` | InfluxDB admin password — **change this** |
| `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN` | `energy-token-123` | InfluxDB API token — **change this** |
| `AIRFLOW_ADMIN_PASSWORD` | `changeme` | Airflow admin UI password — **change this** |

### Required — set for production environment

| Variable | Description |
|---|---|
| `KAFKA_ADVERTISED_LISTENERS` | Set the `EXTERNAL://` listener to the server's public IP/hostname so external clients can reach Kafka if needed. Example: `INTERNAL://kafka:29092,EXTERNAL://<server-ip>:9092` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated list of allowed origins for the API (E3's frontend URL). Default allows all. |
| `MLFLOW_TRACKING_URI` | Set to `http://mlflow:5000` (internal) — already correct |

### Optional tuning

| Variable | Default | Description |
|---|---|---|
| `INFLUXDB_TOKEN` | `energy-token-123` | Token for InfluxDB writes from ingestion/storage services |
| `LOG_LEVEL` | `INFO` | Set to `WARNING` in production to reduce log volume |
| `FORECAST_HORIZON_HOURS` | `24` | Hours ahead to forecast |
| `HIGH_CONSUMPTION_THRESHOLD` | `800` | Watts threshold for high-consumption recommendations |

---

## Persistent volumes

| Volume | Used by | What's stored |
|---|---|---|
| `postgres_data` | postgres | All relational data (telemetry, anomalies, forecasts, MLflow metadata) |
| `influxdb_data` | influxdb | Time-series metrics |
| `redis_data` | redis | Cache (ephemeral — safe to lose) |
| `kafka_data` | kafka | Message log |
| `zookeeper_data` / `zookeeper_logs` | zookeeper | Kafka coordination state |
| `flink_data` | flink-jobmanager, flink-taskmanager | Flink checkpoints |
| `mlflow_artifacts` | mlflow | Model artifacts, experiment files |
| `mosquitto_data` / `mosquitto_logs` | mosquitto | MQTT persistence and logs |
| `airflow_data` | airflow | DAG run data |
| `./models` (bind mount) | api, anomaly, airflow | LSTM model file (`lstm_model.pth`), anomaly detector (`detector.pkl`) |

**The `./models` bind mount is critical.** The API loads the LSTM model from `models/lstm_model.pth` at startup. Airflow writes updated model files here after each retraining run. In production, replace this bind mount with a shared persistent volume accessible to both the `api` and `airflow` containers.

---

## Schema initialisation

PostgreSQL schema is auto-applied on first start via:
```
./db/postgres/schema.sql → /docker-entrypoint-initdb.d/01-schema.sql
```

This only runs on a **fresh data volume**. If `postgres_data` already exists, the schema is not re-applied. If you need to re-initialise, drop the volume first:
```bash
docker volume rm <project>_postgres_data
```

---

## Health checks

| Service | Health check endpoint |
|---|---|
| `api` | `GET /health` → `{"status": "healthy"}` |
| `postgres` | `pg_isready` |
| `influxdb` | `GET /ping` |
| `redis` | `redis-cli ping` |
| `kafka` | `kafka-broker-api-versions` |
| `mosquitto` | `mosquitto_pub` test publish |
| `flink-jobmanager` | `GET /overview` |
| `flink-taskmanager` | `GET /taskmanagers` via jobmanager |

---

## Build

```bash
# Build all custom images
docker compose build

# Build a specific image
docker compose build api
docker compose build ingestion
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

`kafka-init` creates these topics automatically on first boot:

| Topic | Producers | Consumers |
|---|---|---|
| `energy.telemetry` | ingestion | storage, anomaly, streaming |
| `energy.telemetry.results` | streaming | storage |

Partitions: 1. Replication factor: 1 (increase for HA).

---

## Model files

The API and anomaly service require pre-trained model files at startup:

| File | Used by | What happens without it |
|---|---|---|
| `models/lstm_model.pth` | api | API starts with an untrained model — `/forecast/predict` returns low-quality predictions |
| `models/anomaly/detector.pkl` | anomaly | Anomaly pipeline trains a fresh model on first run using available data |

Trigger the Airflow `model_retraining` DAG after first boot to generate `lstm_model.pth`. The anomaly detector self-bootstraps.

---

## Airflow DAGs

| DAG | Schedule | What it does |
|---|---|---|
| `model_retraining` | Weekly (configurable) | Retrains LSTM forecasting model, logs to MLflow, saves to `models/` |
| `energy_batch_pipeline` | Daily | Aggregates telemetry into analytics tables |
| `data_validation` | Daily | Validates data quality in PostgreSQL |

Airflow admin UI: `http://<host>:8081` — default credentials set via `AIRFLOW_ADMIN_PASSWORD`.

---

## Known constraints

- **Kafka `EXTERNAL` listener**: In `docker-compose.yml` the external listener advertises `localhost:9092`. In production, update `KAFKA_ADVERTISED_LISTENERS` to use the server's real IP/hostname so services outside Docker can connect.
- **Single-node Kafka**: `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1`. For HA, increase broker count and replication factor.
- **Flink local mode**: The `streaming` container runs PyFlink in local mini-cluster mode — it does not submit jobs to the `flink-jobmanager`. The Flink cluster containers are available for future job submission.
- **No TLS**: MQTT and API are unencrypted. Terminate TLS at a load balancer/ingress in production.
- **Model bind mount**: The `./models` directory is bind-mounted. Replace with a named shared volume in production.

---

## Contact

E2 team: Tharupahan Jayawardana (architecture), babijana jegarashan (API/infra config)
