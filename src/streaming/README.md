# Stream Processing

This module contains the Sprint 1 baseline Flink job for telemetry data.

Current behavior:
- reads mock telemetry records from `tests/fixtures/energy-readings.json`
- validates each message using `src.validation.telemetry_expectations`
- groups valid records into 2-second tumbling windows
- prints summary per window

## Run Locally
Install the dependencies in `requirements.txt` before running the job.

From the `data-intelligence` folder:

```bash
python3 -m src.streaming.flink_stream_job
```

This is the Sprint 1 mock-data version.
