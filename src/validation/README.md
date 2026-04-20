# Telemetry Validation

This module validates telemetry records using Great Expectations.

Rules checked:
- required fields: `node_id`, `timestamp`, `voltage`, `current`, `power`, `energy_wh`
- `node_id` must be a string
- `timestamp` must be a positive 13-digit epoch millisecond integer
- `voltage` must be between `200` and `250`
- `current` must be greater than `0`
- `power` must be greater than `0`
- `energy_wh` must be `0` or greater

## Run Locally

From the `data-intelligence` folder:

```bash
python3 -m src.validation.telemetry_expectations
```
