# Stream Processing

This module contains the Flink streaming job for telemetry data.

## Current Behavior

- reads telemetry JSON messages from Kafka topic `energy.telemetry`
- validates each message using `src.validation.telemetry_expectations`
- keeps only valid telemetry records for aggregation
- assigns event time from the telemetry `timestamp` field
- uses bounded out-of-order watermarks to handle delayed events
- groups valid records into 2-second tumbling event-time windows
- writes window summaries to Kafka topic `energy.telemetry.results`

## Kafka Topics

Input topic:

`energy.telemetry`

Output topic:

`energy.telemetry.results`

These topics are created automatically by the `kafka-init` service in
`docker-compose.yml` after Kafka becomes healthy.

## Run With Docker

From the `data-intelligence` folder:

```bash
docker compose up streaming
```

This starts Kafka dependencies, runs `kafka-init`, and then starts the streaming
processor.

## Test Locally

Use two terminals from the `data-intelligence` folder.

Terminal 1:

```bash
docker compose up streaming
```

Terminal 2:

```bash
docker exec -i energy-kafka kafka-console-producer \
  --bootstrap-server localhost:9092 \
  --topic energy.telemetry
```

Paste test telemetry messages into the producer:

```json
{"node_id":"plug_01","timestamp":1712908800000,"voltage":230.1,"current":1.78,"power":401.6,"energy_wh":1250.4}
{"node_id":"plug_01","timestamp":1712908801000,"voltage":231.0,"current":1.80,"power":415.8,"energy_wh":1255.0}
{"node_id":"plug_01","timestamp":1712908805000,"voltage":230.5,"current":1.75,"power":402.0,"energy_wh":1260.0}
```

Check the streaming logs:

```bash
docker compose logs streaming --tail=100
```

Consume the window summaries:

```bash
docker exec energy-kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic energy.telemetry.results \
  --from-beginning \
  --max-messages 5
```

Expected result shape:

```json
{"window_start":1712908800000,"window_end":1712908802000,"record_count":2}
{"window_start":1712908804000,"window_end":1712908806000,"record_count":1}
```

## Event Time

Telemetry `timestamp` values are epoch milliseconds.

Example:

```json
"timestamp": 1712908800000
```

The job uses this field as Flink event time.
