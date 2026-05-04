# E2 Integration Guide — E3 (Frontend & User Interaction)

This document tells E3 exactly how to consume the E2 REST API.

---

## Connection

| Setting | Value |
|---|---|
| Protocol | HTTP/1.1 |
| Base URL (local dev) | `http://localhost:8000` |
| Base URL (Docker internal) | `http://energy-api:8000` |
| Authentication | None required |
| Interactive docs | `http://localhost:8000/docs` |

---

## Endpoints

### GET /health

Liveness check. Use this to gate UI startup or show a connectivity status indicator.

**Response `200`:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "service": "Load Forecasting API"
}
```

---

### GET /anomalies

Returns detected energy anomalies. Use this to populate alert lists, dashboards, or node-level detail views.

**Query parameters:**

| Parameter | Type | Description |
|---|---|---|
| `node_id` | string | Filter to a specific meter/device |
| `severity` | string | Filter by `"high"`, `"medium"`, or `"normal"` |
| `limit` | integer | Max records (default 100) |

**Example request:**
```
GET /anomalies?node_id=node_001&severity=high&limit=20
```

**Response `200`:**
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

| Field | Type | Notes |
|---|---|---|
| `node_id` | string | Device/meter identifier |
| `timestamp` | integer | Unix epoch milliseconds — convert to display time |
| `anomaly_type` | string | e.g. `"voltage_spike"`, `"energy_theft"`, `"unusual_consumption"` |
| `score` | float | Isolation Forest score — more negative = more anomalous |
| `severity` | string | `"high"`, `"medium"`, or `"normal"` |

Returns an empty array `[]` if no anomalies exist — not a 404.

---

### GET /recommendations

Returns energy optimization recommendations derived from anomaly data. Use this for the recommendations panel or notification feed.

**Response `200`:**
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

| Field | Type | Notes |
|---|---|---|
| `node_id` | string | Device/meter identifier |
| `type` | string | `"high_anomaly"`, `"load_shift"`, or `"high_consumption"` |
| `severity` | string | `"high"`, `"medium"`, or `"low"` |
| `message` | string | Ready-to-display text — no formatting needed |
| `generated_at` | string | ISO 8601 datetime string |
| `metadata` | object | Additional context, may be empty `{}` |

---

### GET /forecast/forecasts

Returns stored 24-hour load forecasts from the database. Use this to display historical/pre-computed forecast charts per node.

**Query parameters:**

| Parameter | Type | Description |
|---|---|---|
| `node_id` | string | Filter to a specific meter/device |
| `limit` | integer | Max records (default 100) |

**Response `200`:**
```json
[
  {
    "node_id": "node_001",
    "timestamp": 1714800000000,
    "predicted_consumption": 432.5
  }
]
```

| Field | Type | Notes |
|---|---|---|
| `node_id` | string | Device/meter identifier |
| `timestamp` | integer | Unix epoch milliseconds of the forecast point |
| `predicted_consumption` | float | Predicted power in watts |

---

### POST /forecast/predict

On-demand 24-hour forecast given the last 10 hourly readings. Use this for interactive "what-if" tools or when a node has no stored forecast.

**Request body:**
```json
{
  "power_readings": [400, 420, 450, 480, 500, 470, 420, 380, 350, 340]
}
```

- `power_readings` — exactly **10** power values in watts, ordered oldest → newest

**Response `200`:**
```json
{
  "forecast": [412.3, 425.1, 438.7, 451.2, 462.0, 455.3, 441.8, 428.6, 415.2, 402.7, 398.1, 395.4, 401.2, 418.3, 435.6, 452.1, 461.8, 458.3, 443.2, 429.7, 416.1, 403.8, 397.2, 394.5],
  "hours_ahead": 24,
  "unit": "watts"
}
```

- `forecast` — array of 24 floats, one per hour starting from now
- `hours_ahead` — always 24
- `unit` — always `"watts"`

**Response `400`** (wrong input length):
```json
{ "detail": "Expected 10 power readings, got 5" }
```

> **Note:** This endpoint runs ML inference on each call (~80 ms). Use it on-demand, not for polling. For display purposes, prefer `/forecast/forecasts` which returns pre-computed results.

---

### POST /forecast/predict-batch

Forecast multiple nodes in a single request. Useful when loading a dashboard with several nodes at once.

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
    [412.3, 425.1, 438.7, "...24 values"],
    [308.2, 312.4, 316.8, "...24 values"]
  ],
  "count": 2,
  "hours_ahead": 24,
  "unit": "watts"
}
```

---

## Errors

| Status | Meaning |
|---|---|
| `400` | Bad request — check your input (e.g. wrong number of readings) |
| `503` | E2 database temporarily unavailable — retry after a short wait |

Error body always has the shape:
```json
{ "detail": "Description of the error" }
```

---

## CORS

CORS is enabled on the E2 API. If you hit issues from a browser, let us know the origin and we will whitelist it via the `CORS_ALLOWED_ORIGINS` environment variable.

---

## Timestamps

All `timestamp` fields are **Unix epoch milliseconds** (13-digit integers). Convert to local time in the UI:

```js
new Date(1714800000000).toLocaleString()
```

---

## Polling recommendations

| Endpoint | Suggested approach |
|---|---|
| `/anomalies` | Poll every 30–60 seconds for live alert feeds |
| `/recommendations` | Poll every 60 seconds or on user page load |
| `/forecast/forecasts` | Load once on page load, refresh every few minutes |
| `/forecast/predict` | Call on-demand only (user action, not polling) |
| `/health` | Check once on app startup |

---

## Quick start

```js
const BASE = "http://localhost:8000";

// Get high-severity anomalies for a node
const anomalies = await fetch(`${BASE}/anomalies?node_id=node_001&severity=high`)
  .then(r => r.json());

// Get recommendations
const recs = await fetch(`${BASE}/recommendations`)
  .then(r => r.json());

// On-demand forecast
const forecast = await fetch(`${BASE}/forecast/predict`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ power_readings: [400, 420, 450, 480, 500, 470, 420, 380, 350, 340] })
}).then(r => r.json());

console.log(forecast.forecast); // [412.3, 425.1, ...]
```

---

## Contact

E2 team: Tharupahan Jayawardana (architecture/anomaly), babijana jegarashan (API)
