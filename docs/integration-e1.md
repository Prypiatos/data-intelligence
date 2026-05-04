# E2 Integration Guide - E1 (Device & Edge)

This document tells E1 exactly what to publish and how to connect to the E2 data pipeline.

---

## Connection

| Setting | Value |
|---|---|
| Protocol | MQTT v3.1.1 |
| Host | `mosquitto` (Docker internal) / `localhost` (local dev) |
| Port | `1883` |
| Authentication | None required |
| QoS | 1 (at least once) — required for reliable delivery |
| Keep-alive | 60 seconds recommended |

If the broker is unreachable, use exponential backoff before retrying (start at 1 s, cap at 60 s). Do not flood reconnect attempts.

---

## Topics

E1 must publish to exactly these three topic patterns:

| Topic | Purpose |
|---|---|
| `energy/nodes/{node_id}/telemetry` | Power readings from a meter |
| `energy/nodes/{node_id}/events` | Device events (alarms, state changes) |
| `energy/nodes/{node_id}/health` | Heartbeat / device health status |

`{node_id}` is the unique identifier for the device. Rules:

- Use alphanumeric characters and underscores only (e.g. `node_001`, `meter_e1_42`)
- Max 64 characters
- Must be consistent per device — it is used as the primary key throughout the E2 pipeline and cannot be changed after first use
- The `{node_id}` in the topic must match the `node_id` field in the payload

---

## Payload Schemas

All payloads must be valid JSON. **One reading per message**. Do not batch multiple readings in a single payload. Invalid messages are logged and dropped. They will not reach the database.

### Telemetry — `energy/nodes/{node_id}/telemetry`

```json
{
  "node_id": "node_001",
  "timestamp": 1714800000000,
  "voltage": 230.5,
  "current": 4.2,
  "power": 968.1,
  "energy_wh": 16.135
}
```

| Field | Type | Constraints |
|---|---|---|
| `node_id` | string | Non-empty, matches topic segment, max 64 chars |
| `timestamp` | integer | Unix epoch **milliseconds** (13 digits) |
| `voltage` | float | 200 – 250 V (inclusive) — outside this range is rejected |
| `current` | float | > 0 |
| `power` | float | > 0 (watts) |
| `energy_wh` | float | ≥ 0 |

The payload must contain **exactly** these six fields. No extra/missing fields. Messages that fail validation are logged and discarded.

### Events — `energy/nodes/{node_id}/events`

```json
{
  "node_id": "node_001",
  "node_type": "smart_meter",
  "timestamp": 1714800000000,
  "event_type": "high_voltage",
  "severity": "high",
  "message": "Voltage exceeded 250V threshold",
  "buffered": false
}
```

| Field | Type | Notes |
|---|---|---|
| `node_id` | string | Device identifier |
| `node_type` | string | e.g. `"smart_meter"`, `"sensor"` |
| `timestamp` | integer | Unix epoch milliseconds — use the time the event occurred, not the time of publish |
| `event_type` | string | e.g. `"high_voltage"`, `"disconnect"`, `"alarm"` |
| `severity` | string | `"high"`, `"medium"`, or `"low"` |
| `message` | string | Human-readable description |
| `buffered` | boolean | Set `true` if the message was queued while offline and is being sent late. E2 uses this to distinguish real-time events from replayed ones |

### Health — `energy/nodes/{node_id}/health`

```json
{
  "node_id": "node_001",
  "node_type": "smart_meter",
  "timestamp": 1714800000000,
  "sequence_no": 42,
  "status": "online",
  "uptime_sec": 86400,
  "mqtt_connected": true,
  "wifi_connected": true,
  "sensor_ok": true,
  "buffered_count": 0
}
```

| Field | Type | Notes |
|---|---|---|
| `node_id` | string | Device identifier |
| `node_type` | string | Device type |
| `timestamp` | integer | Unix epoch milliseconds |
| `sequence_no` | integer | Monotonically increasing counter per device — used to detect gaps |
| `status` | string | `"online"` or `"offline"` |
| `uptime_sec` | integer | Seconds since last boot |
| `mqtt_connected` | boolean | MQTT broker reachability from device perspective |
| `wifi_connected` | boolean | Network status |
| `sensor_ok` | boolean | Sensor hardware status |
| `buffered_count` | integer | Number of messages currently queued offline waiting to be sent |

---

## Publishing frequency

| Topic | Recommended interval |
|---|---|
| `telemetry` | Every 60 seconds |
| `health` | Every 60 seconds |
| `events` | On occurrence only |

Higher frequency is supported but not needed. The pipeline processes at 60 second granularity. Publishing faster wastes bandwidth without benefit.

---

## Offline buffering

If the device loses connectivity, buffer telemetry and events locally. When reconnected:

1. Replay buffered messages in chronological order using the original `timestamp` values — do not backfill with the current time
2. Set `buffered: true` on replayed event messages
3. Set `buffered_count` in the health message to reflect the queue depth before drain

E2 deduplicates telemetry on `(node_id, timestamp)` — replaying the same reading twice is safe.

---

## What happens to your data

```
E1 device
    │ MQTT publish (QoS 1)
    ▼
Mosquitto broker (port 1883)
    │
    ▼
E2 ingestion service
    ├── validates telemetry payload (rejects invalid)
    ├── publishes to Kafka: energy.telemetry
    └── bridges events/health to their Kafka topics
            │
            ▼
    Storage consumer  → PostgreSQL telemetry_readings
    Anomaly pipeline  → PostgreSQL anomaly_records (non-normal readings only)
    Flink stream      → windowed aggregations → Kafka energy.telemetry.results
```

---

## Testing your integration

1. Connect to `localhost:1883`
2. Publish a test telemetry message:
   ```json
   {
     "node_id": "test_node_001",
     "timestamp": 1714800000000,
     "voltage": 230.0,
     "current": 3.5,
     "power": 805.0,
     "energy_wh": 13.4
   }
   ```
   to topic `energy/nodes/test_node_001/telemetry`
3. Check ingestion logs: `docker logs energy-ingestion`
   - A valid message prints: `Valid telemetry message: {...}`
   - An invalid message prints: `Invalid telemetry: <reason>`
4. Confirm the row appears in PostgreSQL:
   ```sql
   SELECT * FROM telemetry_readings WHERE node_id = 'test_node_001';
   ```
