# Contributing Guidelines

## Team

**Tharupahan Jayawardana** - Architecture, Scrum, Anomaly Detection
- `src/models/anomaly/`
- `src/optimization/`
- `src/utils/`
- `docker/Dockerfile.anomaly`
- `.github/workflows/ci.yml`
- `tests/unit/test-anomaly.py`
- `tests/system/test-end-to-end-pipeline.py`

**[Name]** - Ingestion & Storage
- `src/ingestion/`
- `db/postgres/`
- `db/influxdb/`
- `dags/energy-batch-pipeline.py`
- `docker/Dockerfile.ingestion`
- `tests/fixtures/energy-readings.json`
- `tests/unit/test-ingestion.py`
- `tests/integration/test-db-connections.py`
- `tests/integration/test-kafka-pipeline.py`

**Didula Jeewandara** - Forecasting & ML Ops
- `src/models/forecasting/`
- `mlflow/`
- `src/spark/feature-engineering.py`
- `dags/model-retraining-dag.py`
- `docker/Dockerfile.forecasting`
- `tests/unit/test-forecasting.py`

**[Name]** - Stream Processing & Validation
- `src/streaming/`
- `src/validation/`
- `src/spark/batch-energy-analytics.py`
- `dags/data-validation-dag.py`
- `docker/Dockerfile.streaming`
- `tests/unit/test-streaming.py`
- `tests/unit/test-validation.py`

**[Name]** - API & Infrastructure
- `src/api/`
- `docker-compose.yml`
- `docker/Dockerfile.api`
- `tests/unit/test-api.py`
- `tests/system/test-api-e2e.py`

---

## Development Approach
- **Sprint 1:** Each member develops against mock data to avoid blocking dependencies
- **Sprint 2+:** Integration with live Kafka/InfluxDB pipelines begins
- Docker only handles local development. Production orchestration is managed by E4
- `pyproject.toml`, `requirements.txt`, and `.env.example` are shared. Everyone updates them as needed.

---

## Branches
Each member has their own branch. Work there, don't push to other branches.

| Branch | Owner |
|---|---|
| `anomaly-detection` | Tharupahan |
| `data-ingestion` | [Name] |
| `load-forecasting` | [Name] |
| `stream-processing` | [Name] |
| `analytics-api` | [Name] |

---

## Before you start working
After cloning, run this once to activate commit hooks:

```bash
git config core.hooksPath .githooks
```

Always pull the latest from main into your branch before starting anything new. This keeps conflicts small and manageable.

```bash
git checkout your-branch
git pull origin main
```

If you haven't touched your branch in a while, do this before writing a single line.

---

## Commits
Keep them small and focused. One thing per commit.

```
add kafka consumer for smart meter topic
fix influxdb connection timeout
```

Not this:
```
changes
fixed stuff
wip
```

---

## Raising a PR
- Check branch is up to date with `main` first
- Fill in the PR template - [Find it here](.github/PULL_REQUEST_TEMPLATE.md)
- Tag the issue in PR description like this - `Closes #12`
- Don't merge your own PR

---

## Shared files
`requirements.txt`, `pyproject.toml`, `.env.example` - Be mindful not to overwrite others' work when editing these common files.
