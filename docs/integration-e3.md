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

### GET /nodes

Returns all known nodes with their learning mode status. Use this as your dashboard entry point — load this first to know which nodes exist and whether anomaly detection is active for each.

**Response `200`:**
```json
[
  {
    "node_id": "node_001",
    "learning_mode": true,
    "first_seen_ms": 1714800000000,
    "days_since_first_seen": 5.2,
    "days_remaining": 24.8
  },
  {
    "node_id": "node_002",
    "learning_mode": false,
    "first_seen_ms": 1712000000000,
    "days_since_first_seen": 38.1,
    "days_remaining": 0.0
  }
]
```

| Field | Type | Notes |
|---|---|---|
| `node_id` | string | Device/meter identifier |
| `learning_mode` | boolean | `true` = still collecting data, anomaly detection not yet active |
| `first_seen_ms` | integer | Unix epoch ms of the first reading ever received from this node |
| `days_since_first_seen` | float | How many days since the node was first seen |
| `days_remaining` | float | Days until anomaly detection activates. `0.0` when active |

**If `learning_mode` is `true`:** show "Learning mode — X days remaining" instead of an anomaly panel. No anomalies will be generated for this node yet.

**If `learning_mode` is `false`:** anomaly detection is active. Show the anomaly panel and poll `/anomalies?node_id=...`.

Returns an empty array `[]` if no nodes have sent data yet.

---

### GET /nodes/{node_id}/status

Returns learning mode status for a single node.

**Example request:**
```
GET /nodes/node_001/status
```

**Response `200`:** same shape as a single object from `GET /nodes`.

**Response `404`:** node not found (no readings received yet).

---

### GET /anomalies

Returns detected energy anomalies. Only call this for nodes where `learning_mode` is `false`. Returns an empty array for nodes still in learning mode since no anomalies are generated during that period.

**Query parameters:**

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `node_id` | string | — | — | Filter to a specific node |
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
    "anomaly_type": "consumption_anomaly",
    "score": -0.18,
    "severity": "high"
  }
]
```

| Field | Type | Notes |
|---|---|---|
| `node_id` | string | Device/meter identifier |
| `timestamp` | integer | Unix epoch milliseconds |
| `anomaly_type` | string | Currently always `"consumption_anomaly"` |
| `score` | float | Isolation Forest anomaly score — see score section below |
| `severity` | string | `"high"`, `"medium"`, or `"low"` |

Returns an empty array `[]` if no anomalies exist. Not a 404.

**Only non-normal readings are stored.** The `severity` field will never be `"normal"` in this response.

#### Anomaly score interpretation

The model detects nodes operating outside their learned normal hours — e.g. a device active at 3am when it is never active at night.

| Score range | Severity | Meaning |
|---|---|---|
| ≤ −0.15 | `high` | Strong anomaly — device active at highly unusual hour |
| −0.15 to −0.05 | `medium` | Moderate anomaly — worth investigating |
| −0.05 to 0.0 | `low` | Mild deviation — monitor |

More negative = more anomalous. Scores above 0 are normal and not stored.

---

### GET /recommendations

Returns energy optimization recommendations derived from anomaly data and forecasts. Use this for the recommendations panel or notification feed.

**Important:** Generates results live on each call by querying the last 6 hours of anomaly data and 24-hour forecasts. Response time is typically under 200 ms.

**Response `200`:**
```json
[
  {
    "node_id": "node_001",
    "type": "high_anomaly",
    "severity": "high",
    "message": "Node node_001 flagged with high-severity anomaly (score -0.180). Inspect for irregular consumption.",
    "generated_at": "2026-05-04T07:00:00+00:00",
    "metadata": { "anomaly_score": -0.18 }
  }
]
```

| Field | Type | Notes |
|---|---|---|
| `node_id` | string | Device/meter identifier |
| `type` | string | `"high_anomaly"`, `"load_shift"`, or `"high_consumption"` |
| `severity` | string | `"high"` or `"medium"` — recommendations are never `"low"` |
| `message` | string | Ready-to-display text — no formatting needed |
| `generated_at` | string | ISO 8601 datetime with UTC offset |
| `metadata` | object | Additional context — may be empty `{}` |

**Recommendation types:**

| Type | Trigger | Meaning for user |
|---|---|---|
| `high_anomaly` | Node has high/medium severity anomalies in last 6h | Device operating at unusual hours — inspect |
| `load_shift` | Forecasted consumption peaks in top 10% | Suggest shifting load away from peak hours |
| `high_consumption` | Predicted consumption exceeds 800W | Unusually high usage — review connected devices |

---

### GET /forecast/forecasts

Returns stored 24-hour load forecasts. Use this to display forecast charts per node.

**Query parameters:**

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `node_id` | string | — | — | Filter to a specific node |
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

Returns an empty array `[]` if no forecasts have been generated yet.

> **Note:** Forecasts are not generated while a node is in learning mode (`learning_mode: true`). Use `GET /nodes` to check — if `days_remaining > 0`, show the same "Learning mode — X days remaining" message instead of an empty chart.

---

### GET /telemetry/history

Returns raw sensor readings. Use this for detailed historical charts or per-reading data.

**Query parameters:**

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `node_id` | string | — | — | Filter to a specific node |
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
    "current": 0.26,
    "power": 60.0,
    "energy_wh": 0.083
  }
]
```

| Field | Type | Notes |
|---|---|---|
| `node_id` | string | Device/meter identifier |
| `timestamp` | integer | Unix epoch milliseconds |
| `voltage` | float | Volts |
| `current` | float | Amps — can be 0.0 when device is off |
| `power` | float | Watts — can be 0.0 when device is off |
| `energy_wh` | float | Energy in watt-hours for this reading interval |

Results are ordered newest first. Returns an empty array `[]` if no readings exist.

> **Note:** Raw readings are high-frequency. Always provide `start`/`end` or a low `limit`. For charting over longer periods, prefer `/analytics/hourly` or `/analytics/daily`.
>
> **Data window:** InfluxDB retains 30 days of raw telemetry. Requests with `start` older than 30 days will return no data for that range.

---

### GET /analytics/hourly

Returns hourly energy consumption rollups. Use this for trend charts or hourly breakdowns.

**Query parameters:**

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `node_id` | string | — | — | Filter to a specific node |
| `division` | string | — | — | Filter by building division |
| `start` | integer | — | — | Start time (Unix epoch ms, inclusive) |
| `end` | integer | — | — | End time (Unix epoch ms, inclusive) |
| `limit` | integer | 100 | 1000 | Max records returned |

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

Returns an empty array `[]` if the Spark pipeline has not yet run.

---

### GET /analytics/daily

Returns daily energy consumption rollups. Use this for daily summaries or long-range trend charts.

**Query parameters:**

| Parameter | Type | Default | Max | Description |
|---|---|---|---|---|
| `node_id` | string | — | — | Filter to a specific node |
| `division` | string | — | — | Filter by building division |
| `start` | string | — | — | Start date (YYYY-MM-DD, inclusive) |
| `end` | string | — | — | End date (YYYY-MM-DD, inclusive) |
| `limit` | integer | 100 | 1000 | Max records returned |

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
| `avg_power_w` | float\|null | Average power in watts |
| `peak_power_w` | float\|null | Peak power in watts |
| `reading_count` | integer\|null | Number of raw readings that contributed |

Returns an empty array `[]` if the Spark pipeline has not yet run.

---

### WS /ws/live

Live stream of Flink window summaries over WebSocket. Connect once and receive data as it arrives — no polling needed.

**URL:** `ws://localhost:8000/ws/live` (local dev) / `ws://energy-api:8000/ws/live` (Docker)

**Message format:**
```json
{
  "node_id": "node_001",
  "window_start": 1714800000000,
  "window_end": 1714800002000,
  "avg_power": 60.0,
  "max_power": 60.2,
  "avg_voltage": 230.0,
  "avg_current": 0.26,
  "avg_energy_wh": 0.083,
  "record_count": 4
}
```

| Field | Type | Notes |
|---|---|---|
| `node_id` | string | Device/meter identifier |
| `window_start` | integer | Unix epoch ms — start of the 2-second window |
| `window_end` | integer | Unix epoch ms — end of the 2-second window |
| `avg_power` | float | Average power in watts over the window |
| `max_power` | float | Peak power in watts over the window |
| `avg_voltage` | float | Average voltage over the window |
| `avg_current` | float | Average current over the window |
| `avg_energy_wh` | float | Average energy in watt-hours over the window |
| `record_count` | integer | Number of readings in this window |

**Keepalive:** If no data arrives within 30 seconds the server sends `{"type": "ping"}` — ignore in your message handler.

**Error:** If Kafka is unreachable the server sends `{"error": "..."}` and the connection stays open.

```js
const ws = new WebSocket("ws://localhost:8000/ws/live");

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === "ping") return;
  if (data.error) { console.error("Stream error:", data.error); return; }
  // handle live window summary
};
```

---

## Errors

| Status | Meaning | What to do |
|---|---|---|
| `400` | Bad request — invalid input | Fix the request parameters |
| `404` | Resource not found | Node does not exist or has no data yet |
| `503` | E2 database or model unavailable | Retry with exponential backoff — start at 2 s, cap at 30 s |

Error body always:
```json
{ "detail": "Description of the error" }
```

---

## Node discovery

Call `GET /nodes` to get all active nodes and their status. This is the correct starting point for building a node list or dashboard. Node IDs originate from E1 (edge devices) — you do not need to hardcode them.

**Recommended dashboard flow:**
1. On page load call `GET /nodes`
2. For each node: if `learning_mode: true` → show "Learning mode — X days remaining" for **both** the anomaly panel and the forecast chart
3. For each node: if `learning_mode: false` → show anomaly panel (poll `/anomalies?node_id=...`) and forecast chart (poll `/forecast/forecasts?node_id=...`)

---

## Pagination

No cursor/offset pagination. Use the `limit` parameter (max 1000). Contact E2 if you need offset support.

---

## Timestamps

All `timestamp` fields are **Unix epoch milliseconds** (13-digit integers).

```js
new Date(1714800000000).toLocaleString()

import { format } from 'date-fns';
format(new Date(1714800000000), 'dd MMM yyyy HH:mm')
```

`generated_at` on recommendations is ISO 8601 — parse with `new Date(generated_at)`.

---

## CORS

CORS is enabled. If you hit browser CORS errors, share your origin URL with E2 and we will whitelist it via `CORS_ALLOWED_ORIGINS`.

---

## Polling recommendations

| Endpoint | Suggested approach |
|---|---|
| `/ws/live` | Connect once — server pushes data |
| `/nodes` | Poll every 60 s to track learning mode progress |
| `/anomalies` | Poll every 30–60 s for nodes where `learning_mode: false` |
| `/recommendations` | Poll every 60 s maximum |
| `/forecast/forecasts` | Load once on page load, refresh every few minutes |
| `/telemetry/history` | Load on demand (user selects time range) |
| `/analytics/hourly` | Load on demand or once on page load |
| `/analytics/daily` | Load on demand or once on page load |
| `/health` | Once on app startup |

---

## Quick start

```js
const BASE = "http://localhost:8000";

// 1. Load all nodes and their status
const nodes = await fetch(`${BASE}/nodes`).then(r => r.json());
// Returns: [{ node_id, learning_mode, days_remaining, ... }, ...]

// 2. For each node, check learning mode
for (const node of nodes) {
  if (node.learning_mode) {
    console.log(`${node.node_id}: learning mode — ${node.days_remaining} days remaining`);
  } else {
    // 3. Fetch anomalies for active nodes
    const anomalies = await fetch(`${BASE}/anomalies?node_id=${node.node_id}&severity=high`)
      .then(r => r.json());
    console.log(`${node.node_id}: ${anomalies.length} high-severity anomalies`);
  }
}

// Get recommendations
const recs = await fetch(`${BASE}/recommendations`).then(r => r.json());

// Get raw telemetry for a node over the last 24 hours
const now = Date.now();
const oneDayAgo = now - 24 * 60 * 60 * 1000;
const readings = await fetch(
  `${BASE}/telemetry/history?node_id=node_001&start=${oneDayAgo}&end=${now}`
).then(r => r.json());

// Get hourly rollups for the last 7 days
const sevenDaysAgo = now - 7 * 24 * 60 * 60 * 1000;
const hourly = await fetch(
  `${BASE}/analytics/hourly?node_id=node_001&start=${sevenDaysAgo}&end=${now}`
).then(r => r.json());

// Get daily rollups for a date range
const daily = await fetch(
  `${BASE}/analytics/daily?node_id=node_001&start=2024-05-01&end=2024-05-07`
).then(r => r.json());
```
