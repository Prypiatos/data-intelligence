# Stream Processing

This module contains the Sprint 1 baseline stream processor for telemetry data.

Current behavior:
- reads mock telemetry records from `tests/fixtures/energy-readings.json`
- validates each message using `src.validation.telemetry_expectations`
- groups valid records into 2-second tumbling windows
- prints one summary per window with the valid record count

Windowing:
- window size is `2000` milliseconds

## Run Locally

From the `data-intelligence` folder:

```bash
python3 -m src.streaming.stream_processor
```

This is a mock-data version for Sprint 1. Kafka input and output can be added in Sprint 2.
