# E2 Data Intelligence — API Contract

This document is the integration reference for E3 (frontend) and E4 (infrastructure).

## Base URL

| Environment | URL |
|---|---|
| Local dev | `http://localhost:8000` |
| Docker internal | `http://energy-api:8000` |

Interactive docs (Swagger UI): `http://localhost:8000/docs`

---

## Authentication

No authentication is required for the current API version.

---

## Endpoints

### GET /

Returns service metadata and a list of available endpoints.

**Response `200`:**
```json
{
  "name": "Energy Management System API",
  "version": "1.0.0",
  "team": "E2 Data & Intelligence",
  "endpoints": {
    "health": "/health (GET)",
    "forecasts": "/forecast/forecasts (GET)",
    "forecast_predict": "/forecast/predict (POST)",
    "forecast_batch": "/forecast/predict-batch (POST)",
    "anomalies": "/anomalies (GET)",
    "recommendations": "/recommendations (GET)",
    "documentation": "/docs (GET)"
  }
}
```

---

### GET /health

Liveness check.

**Response `200`:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "service": "Load Forecasting API"
}
```

---

### GET /forecast/forecasts

Retrieve stored 24-hour forecasts from the database.

**Query parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `node_id` | string | No | Filter by node ID |
| `limit` | integer | No | Max records to return (default 100) |

**Response `200`** — array of forecast records:
```json
[
  {
    "node_id": "node_001",
    "timestamp": 1714800000000,
    "predicted_consumption": 432.5
  }
]
```

**Fields:**
- `node_id` — device/meter identifier (string, e.g. `"node_001"`)
- `timestamp` — Unix epoch milliseconds (integer)
- `predicted_consumption` — predicted power in watts (float)

---

### POST /forecast/predict

On-demand 24-hour load forecast given the last 10 hourly readings.

**Request body:**
```json
{
  "power_readings": [400, 420, 450, 480, 500, 470, 420, 380, 350, 340]
}
```

- `power_readings` — exactly **10** power values in watts (floats), ordered oldest → newest

**Response `200`:**
```json
{
  "forecast": [412.3, 425.1, 438.7, 451.2, 462.0, 455.3, 441.8, 428.6, 415.2, 402.7, 398.1, 395.4, 401.2, 418.3, 435.6, 452.1, 461.8, 458.3, 443.2, 429.7, 416.1, 403.8, 397.2, 394.5],
  "hours_ahead": 24,
  "unit": "watts"
}
```

**Error `400`** — wrong number of readings:
```json
{ "detail": "Expected 10 power readings, got 5" }
```

---

### POST /forecast/predict-batch

Batch forecasting for multiple nodes in one request.

**Request body:**
```json
{
  "batch_readings": [
    [400, 420, 450, 480, 500, 470, 420, 380, 350, 340],
    [300, 310, 320, 315, 330, 325, 310, 305, 300, 295]
  ]
}
```

**Response `200`:**
```json
{
  "forecasts": [
    [412.3, 425.1, ...],
    [308.2, 312.4, ...]
  ],
  "count": 2,
  "hours_ahead": 24,
  "unit": "watts"
}
```

---

### GET /anomalies

Retrieve detected anomalies from the database.

**Query parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `node_id` | string | No | Filter by node ID |
| `severity` | string | No | Filter by severity: `high`, `medium`, `normal` |
| `limit` | integer | No | Max records to return (default 100) |

**Response `200`** — array of anomaly records:
```json
[
  {
    "node_id": "node_001",
    "timestamp": 1714800000000,
    "anomaly_type": "voltage_spike",
    "score": -0.18,
    "severity": "high"
  }
]
```

**Fields:**
- `node_id` — device/meter identifier (string)
- `timestamp` — Unix epoch milliseconds (integer)
- `anomaly_type` — type of anomaly detected (string, e.g. `"voltage_spike"`, `"energy_theft"`, `"unusual_consumption"`)
- `score` — Isolation Forest anomaly score (float, more negative = more anomalous)
- `severity` — one of `"high"`, `"medium"`, `"normal"`

---

### GET /recommendations

Retrieve energy optimization recommendations generated from anomaly data.

**Response `200`** — array of recommendation records:
```json
[
  {
    "node_id": "node_001",
    "type": "high_anomaly",
    "severity": "high",
    "message": "Node node_001 has 3 high-severity anomalies in the last 24h. Inspect meter and wiring.",
    "generated_at": "2026-05-04T07:00:00",
    "metadata": {}
  }
]
```

**Fields:**
- `node_id` — device/meter identifier (string)
- `type` — one of `"high_anomaly"`, `"load_shift"`, `"high_consumption"`
- `severity` — one of `"high"`, `"medium"`, `"low"`
- `message` — human-readable recommendation text
- `generated_at` — ISO 8601 timestamp string
- `metadata` — additional context (object, may be empty)

---

## Error responses

All endpoints return standard HTTP error codes:

| Status | Meaning |
|---|---|
| `400` | Bad request — invalid input (e.g. wrong number of power readings) |
| `503` | Database unavailable — retry after a short wait |

Error body:
```json
{ "detail": "Error description here" }
```

---

## Data flow context

```
E1 devices
    │ MQTT (port 1883)
    ▼
E2 ingestion → Kafka → anomaly detection → PostgreSQL
                                         ↑
                              E2 API reads from here
                                         │
                              REST API (port 8000)
                                         │
                     ┌───────────────────┘
                     ▼                   ▼
                   E3 app            E4 platform
```

E1 publishes telemetry to `energy/nodes/{node_id}/telemetry`. E3 and E4 consume E2's REST API — no direct access to Kafka or the database is needed.

---

## CORS

The API allows cross-origin requests. Configure `CORS_ALLOWED_ORIGINS` on the E2 API container if specific origins need to be whitelisted. Default allows all origins in local dev.
