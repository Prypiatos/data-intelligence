# E2 Integration Guide - E3 (Frontend & User Interaction)

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

Liveness check. Call this on app startup to confirm E2 is reachable before rendering data.

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

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `node_id` | string | — | — | Filter to a specific meter/device |
| `severity` | string | — | — | Filter by `"high"`, `"medium"`, or `"low"` |
| `limit` | integer | 100 | 1000 | Max records returned |

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
    "anomaly_type": "theft_or_leakage",
    "score": -0.18,
    "severity": "high"
  }
]
```

| Field | Type | Notes |
|---|---|---|
| `node_id` | string | Device/meter identifier |
| `timestamp` | integer | Unix epoch milliseconds — see timestamp section below |
| `anomaly_type` | string | Currently always `"theft_or_leakage"` |
| `score` | float | Isolation Forest anomaly score — see score section below |
| `severity` | string | `"high"`, `"medium"`, or `"low"` — see severity section below |

Returns an empty array `[]` if no anomalies exist. Not a 404.

**Only non normal readings are stored.** The `severity` field will never be `"normal"` in this response. Those readings are filtered at the pipeline level.

#### Anomaly score interpretation

| Score range | Severity | Meaning |
|---|---|---|
| ≤ −0.15 | `high` | Strong anomaly — likely meter fault or energy theft |
| −0.15 to −0.05 | `medium` | Moderate anomaly — worth investigating |
| −0.05 to 0.0 | `low` | Mild deviation — monitor |

More negative = more anomalous. Scores above 0 are normal and not stored.

---

### GET /recommendations

Returns energy optimization recommendations derived from anomaly data. Use this for the recommendations panel or notification feed.

**Important:** This endpoint generates results live on each call by querying the last 6 hours of anomaly data and 24 hour forecasts. Response time is typically under 200 ms but may be slower under heavy DB load. 

**Response `200`:**
```json
[
  {
    "node_id": "node_001",
    "type": "high_anomaly",
    "severity": "high",
    "message": "Node node_001 has 3 high-severity anomalies in the last 24h. Inspect meter and wiring.",
    "generated_at": "2026-05-04T07:00:00+00:00",
    "metadata": {}
  }
]
```

| Field | Type | Notes |
|---|---|---|
| `node_id` | string | Device/meter identifier |
| `type` | string | `"high_anomaly"`, `"load_shift"`, or `"high_consumption"` |
| `severity` | string | `"high"`, `"medium"`, or `"low"` |
| `message` | string | Ready-to-display text - no formatting needed |
| `generated_at` | string | ISO 8601 datetime with UTC offset |
| `metadata` | object | Additional context - may be empty `{}` |

**Recommendation types:**

| Type | Trigger | Meaning for user |
|---|---|---|
| `high_anomaly` | Node has multiple high-severity anomalies in last 6h | Possible meter fault or energy theft — inspect hardware |
| `load_shift` | Forecasted consumption peaks in top 10% | Suggest shifting load away from peak hours |
| `high_consumption` | Predicted consumption exceeds 800W threshold | Unusually high usage - review connected devices |

---

### GET /forecast/forecasts

Returns stored 24 hour load forecasts from the database. Use this to display forecast charts per node.

**Query parameters:**

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `node_id` | string | — | — | Filter to a specific meter/device |
| `limit` | integer | 100 | 1000 | Max records returned |

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

Returns an empty array `[]` if no forecasts have been generated yet. Forecasts are populated by the Airflow model retraining DAG. They may be empty on a fresh system.

---

### POST /forecast/predict

On demand 24 hour forecast given the last 10 hourly readings. Use this for interactive "what if" tools or when a node has no stored forecast.

**Request body:**
```json
{
  "power_readings": [400, 420, 450, 480, 500, 470, 420, 380, 350, 340]
}
```

- `power_readings` - exactly **10** power values in watts, ordered oldest → newest

**Response `200`:**
```json
{
  "forecast": [412.3, 425.1, 438.7, 451.2, 462.0, 455.3, 441.8, 428.6, 415.2, 402.7, 398.1, 395.4, 401.2, 418.3, 435.6, 452.1, 461.8, 458.3, 443.2, 429.7, 416.1, 403.8, 397.2, 394.5],
  "hours_ahead": 24,
  "unit": "watts"
}
```

- `forecast` - array of exactly 24 floats, one per hour starting from now
- `hours_ahead` - always `24`
- `unit` - always `"watts"`

**Response `400`** (wrong input length):
```json
{ "detail": "Expected 10 power readings, got 5" }
```

> **Performance note:** This endpoint runs LSTM inference on every call (~80 ms, CPU bound). Use it on demand (user action), not for polling. For chart display, prefer `/forecast/forecasts` which returns pre computed results.

---

### POST /forecast/predict-batch

Forecast multiple nodes in one request. Use this when loading a dashboard with several nodes at once to avoid N sequential calls.

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
    [412.3, 425.1, 438.7, "...24 values total"],
    [308.2, 312.4, 316.8, "...24 values total"]
  ],
  "count": 2,
  "hours_ahead": 24,
  "unit": "watts"
}
```

---

### GET /telemetry/history

Returns raw sensor readings from individual meters. Use this to display detailed historical charts or per-reading data for a specific node.

**Query parameters:**

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `node_id` | string | — | — | Filter to a specific meter/device |
| `start` | integer | — | — | Start time (Unix epoch ms, inclusive) |
| `end` | integer | — | — | End time (Unix epoch ms, inclusive) |
| `limit` | integer | 100 | 1000 | Max records returned |

**Example request:**
```
GET /telemetry/history?node_id=node_001&start=1714800000000&end=1714886400000
```

**Response `200`:**
```json
[
  {
    "node_id": "node_001",
    "timestamp": 1714800000000,
    "voltage": 230.5,
    "current": 10.5,
    "power": 2420.25,
    "energy_wh": 0.67
  }
]
```

| Field | Type | Notes |
|---|---|---|
| `node_id` | string | Device/meter identifier |
| `timestamp` | integer | Unix epoch milliseconds |
| `voltage` | float | Volts |
| `current` | float | Amps |
| `power` | float | Watts (instantaneous) |
| `energy_wh` | float | Energy in watt-hours for this reading interval |

Results are ordered newest first. Returns an empty array `[]` if no readings exist for the given filters.

> **Note:** Raw readings are high-frequency. Always provide `start`/`end` or a low `limit` to avoid large responses. For charting over longer periods, prefer `/analytics/hourly` or `/analytics/daily`.

---

### GET /analytics/hourly

Returns hourly energy consumption rollups produced by the Spark batch pipeline. Use this for trend charts, hourly breakdowns, or per-division comparisons.

**Query parameters:**

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `node_id` | string | — | — | Filter to a specific meter/device |
| `division` | string | — | — | Filter by building division |
| `start` | integer | — | — | Start time (Unix epoch ms, inclusive) |
| `end` | integer | — | — | End time (Unix epoch ms, inclusive) |
| `limit` | integer | 100 | 1000 | Max records returned |

**Example request:**
```
GET /analytics/hourly?node_id=node_001&start=1714800000000&end=1714886400000
```

**Response `200`:**
```json
[
  {
    "node_id": "node_001",
    "division": "Floor 1 - East Wing",
    "hour_start": "2024-05-04T10:00:00",
    "total_consumption_wh": 2450.5,
    "avg_power_w": 408.4,
    "peak_power_w": 512.1,
    "reading_count": 6
  }
]
```

| Field | Type | Notes |
|---|---|---|
| `node_id` | string | Device/meter identifier |
| `division` | string\|null | Building/division grouping — may be null |
| `hour_start` | string | ISO 8601 datetime — start of the hour bucket |
| `total_consumption_wh` | float | Total energy consumed in this hour |
| `avg_power_w` | float\|null | Average power in watts over the hour |
| `peak_power_w` | float\|null | Peak power in watts over the hour |
| `reading_count` | integer\|null | Number of raw readings that contributed |

Results are ordered newest first. Returns an empty array `[]` if the Spark pipeline has not yet run.

---

### GET /analytics/daily

Returns daily energy consumption rollups produced by the Spark batch pipeline. Use this for daily summaries, weekly comparison views, or long-range trend charts.

**Query parameters:**

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `node_id` | string | — | — | Filter to a specific meter/device |
| `division` | string | — | — | Filter by building division |
| `start` | string | — | — | Start date (YYYY-MM-DD, inclusive) |
| `end` | string | — | — | End date (YYYY-MM-DD, inclusive) |
| `limit` | integer | 100 | 1000 | Max records returned |

**Example request:**
```
GET /analytics/daily?node_id=node_001&start=2024-05-01&end=2024-05-07
```

**Response `200`:**
```json
[
  {
    "node_id": "node_001",
    "division": "Floor 1 - East Wing",
    "date": "2024-05-04",
    "total_consumption_wh": 58820.0,
    "avg_power_w": 411.2,
    "peak_power_w": 512.1,
    "reading_count": 144
  }
]
```

| Field | Type | Notes |
|---|---|---|
| `node_id` | string | Device/meter identifier |
| `division` | string\|null | Building/division grouping — may be null |
| `date` | string | ISO 8601 date (YYYY-MM-DD) |
| `total_consumption_wh` | float | Total energy consumed that day |
| `avg_power_w` | float\|null | Average power in watts over the day |
| `peak_power_w` | float\|null | Peak power in watts over the day |
| `reading_count` | integer\|null | Number of raw readings that contributed |

Results are ordered newest first. Returns an empty array `[]` if the Spark pipeline has not yet run.

---

## Errors

| Status | Meaning | What to do |
|---|---|---|
| `400` | Bad request — invalid input | Fix the request (e.g. send exactly 10 readings) |
| `503` | E2 database or model unavailable | Retry with exponential backoff — start at 2 s, cap at 30 s |

Error body always:
```json
{ "detail": "Description of the error" }
```

---

## Node discovery

There is no `/nodes` endpoint. E3 cannot query E2 for the list of available node IDs. Node IDs come from E1 (the edge devices). Coordinate with E1 to get the list of active node IDs, or display data dynamically based on what appears in `/anomalies` and `/forecast/forecasts` responses.

---

## Pagination

There is no cursor or offset pagination. Use the `limit` parameter (max 1000). If you need all records beyond 1000, contact E2. We can add offset support.

---

## Timestamps

All `timestamp` fields are **Unix epoch milliseconds** (13 digit integers). Convert to local time in the UI:

```js
// JavaScript
new Date(1714800000000).toLocaleString()

// Or with a formatting library
import { format } from 'date-fns';
format(new Date(1714800000000), 'dd MMM yyyy HH:mm')
```

`generated_at` on recommendations is an ISO 8601 string with UTC offset — parse directly with `new Date(generated_at)`.

---

## CORS

CORS is enabled. If you hit browser CORS errors, share your origin URL with E2 and we will whitelist it via `CORS_ALLOWED_ORIGINS`.

---

## Polling recommendations

| Endpoint | Suggested approach |
|---|---|
| `/ws/live` | Connect once — server pushes data as it arrives |
| `/anomalies` | Poll every 30–60 s for live alert feeds |
| `/recommendations` | Poll every 60 s maximum — generates live on each call |
| `/forecast/forecasts` | Load once on page load, refresh every few minutes |
| `/forecast/predict` | On user action only — not for polling |
| `/telemetry/history` | Load on demand (user selects time range) — not for polling |
| `/analytics/hourly` | Load on demand or once on page load for trend charts |
| `/analytics/daily` | Load on demand or once on page load for daily summaries |
| `/health` | Once on app startup |

---

## Quick start

```js
const BASE = "http://localhost:8000";

// Get high-severity anomalies for a node
const anomalies = await fetch(`${BASE}/anomalies?node_id=node_001&severity=high`)
  .then(r => r.json());
// Returns: [{ node_id, timestamp, anomaly_type, score, severity }, ...]

// Get recommendations
const recs = await fetch(`${BASE}/recommendations`)
  .then(r => r.json());
// Returns: [{ node_id, type, severity, message, generated_at, metadata }, ...]

// On-demand forecast
const result = await fetch(`${BASE}/forecast/predict`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    power_readings: [400, 420, 450, 480, 500, 470, 420, 380, 350, 340]
  })
}).then(r => r.json());
// result.forecast → array of 24 watts values

// Convert timestamp to display time
const displayTime = new Date(anomalies[0]?.timestamp).toLocaleString();

// Get raw telemetry for a node over the last 24 hours
const now = Date.now();
const oneDayAgo = now - 24 * 60 * 60 * 1000;
const readings = await fetch(`${BASE}/telemetry/history?node_id=node_001&start=${oneDayAgo}&end=${now}`)
  .then(r => r.json());
// Returns: [{ node_id, timestamp, voltage, current, power, energy_wh }, ...]

// Get hourly rollups for a node over the last 7 days
const sevenDaysAgo = now - 7 * 24 * 60 * 60 * 1000;
const hourly = await fetch(`${BASE}/analytics/hourly?node_id=node_001&start=${sevenDaysAgo}&end=${now}`)
  .then(r => r.json());
// Returns: [{ node_id, division, hour_start, total_consumption_wh, avg_power_w, peak_power_w, reading_count }, ...]

// Get daily rollups for a date range
const daily = await fetch(`${BASE}/analytics/daily?node_id=node_001&start=2024-05-01&end=2024-05-07`)
  .then(r => r.json());
// Returns: [{ node_id, division, date, total_consumption_wh, avg_power_w, peak_power_w, reading_count }, ...]
```