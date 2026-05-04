# E2 Integration Guide — E1 (Device & Edge)

This document tells E1 exactly what to publish and how to connect to the E2 data pipeline.

---

## Connection

| Setting | Value |
|---|---|
| Protocol | MQTT v3.1.1 |
| Host | `mosquitto` (Docker internal) / `localhost` (local dev) |
| Port | `1883` |
| Authentication | None required |
| QoS | 1 (at least once) recommended |

---

## Topics

E1 must publish to exactly these three topic patterns:

| Topic | Purpose |
|---|---|
| `energy/nodes/{node_id}/telemetry` | Power readings from a meter |
| `energy/nodes/{node_id}/events` | Device events (alarms, state changes) |
| `energy/nodes/{node_id}/health` | Heartbeat / device health status |

`{node_id}` is the unique identifier for the device (e.g. `node_001`, `e1_meter_42`). Use a consistent ID per device — it is used as the primary key throughout the E2 pipeline.

---

## Payload Schemas

All payloads must be valid JSON. Invalid messages are silently dropped.

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
| `node_id` | string | Non-empty, must match the topic segment |
| `timestamp` | integer | Unix epoch **milliseconds** (13 digits) |
| `voltage` | float | 200 – 250 V (inclusive) |
| `current` | float | > 0 |
| `power` | float | > 0 (watts) |
| `energy_wh` | float | ≥ 0 |

The payload must contain **exactly** these six fields — no extras, no missing fields. Messages that fail validation are logged and discarded; they will not reach the database.

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
| `timestamp` | integer | Unix epoch milliseconds |
| `event_type` | string | e.g. `"high_voltage"`, `"disconnect"`, `"alarm"` |
| `severity` | string | `"high"`, `"medium"`, or `"low"` |
| `message` | string | Human-readable description |
| `buffered` | boolean | `true` if the message was queued offline and sent later |

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
| `sequence_no` | integer | Monotonically increasing per device |
| `status` | string | `"online"` or `"offline"` |
| `uptime_sec` | integer | Seconds since last boot |
| `mqtt_connected` | boolean | MQTT broker reachability |
| `wifi_connected` | boolean | Network status |
| `sensor_ok` | boolean | Sensor hardware status |
| `buffered_count` | integer | Messages queued offline waiting to send |

---

## Publishing frequency

| Topic | Recommended interval |
|---|---|
| `telemetry` | Every 60 seconds |
| `health` | Every 60 seconds |
| `events` | On occurrence |

Higher frequency is supported but unnecessary — the pipeline processes at 60-second granularity.

---

## What happens to your data

```
E1 device
    │ MQTT publish
    ▼
Mosquitto broker (port 1883)
    │
    ▼
E2 ingestion service
    ├── validates telemetry payload
    ├── publishes to Kafka topic: energy.telemetry
    └── bridges events/health to their Kafka topics
            │
            ▼
    Storage consumer → PostgreSQL (telemetry_readings table)
    Anomaly pipeline  → PostgreSQL (anomaly_records table)
    Flink stream      → windowed aggregations → Kafka results topic
```

Telemetry that fails validation is logged and dropped — it will not appear in the database.

---

## Testing your integration

1. Connect to the broker at `localhost:1883`
2. Publish a test telemetry message to `energy/nodes/test_node/telemetry`
3. Check the E2 ingestion logs: `docker logs energy-ingestion`
4. Confirm the row appears in PostgreSQL:
   ```sql
   SELECT * FROM telemetry_readings WHERE node_id = 'test_node';
   ```

---

## Contact

E2 team: Tharupahan Jayawardana (architecture), Jitharsanan Thiruketheeswaran (ingestion/storage)
