# InfluxDB Setup For Issue #8

This project should use the following InfluxDB configuration for telemetry data:

- Bucket: `energy_telemetry`
- Retention: `30d`
- Measurement: `telemetry`
- Tags: `node_id`
- Fields: `voltage`, `current`, `power`, `energy_wh`

## Create The Bucket

If InfluxDB 2.x is already running, create the bucket with the CLI:

```bash
influx bucket create \
  --name energy_telemetry \
  --retention 720h \
  --org energy-org \
  --token energy-token-123
```

`720h` is equal to 30 days.

## Docker Compose Setup

If you want Docker to initialize the correct bucket during startup, use these environment values for the InfluxDB service:

```env
DOCKER_INFLUXDB_INIT_MODE=setup
DOCKER_INFLUXDB_INIT_USERNAME=admin
DOCKER_INFLUXDB_INIT_PASSWORD=admin12345
DOCKER_INFLUXDB_INIT_ORG=energy-org
DOCKER_INFLUXDB_INIT_BUCKET=energy_telemetry
DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=energy-token-123
```

## Expected Line Protocol Shape

Telemetry points should be written to the `telemetry` measurement with `node_id` as a tag, for example:

```text
telemetry,node_id=plug_01 voltage=230.5,current=1.4,power=322.7,energy_wh=1185.0
```

## Note

The ingestion code is configured to use bucket `energy_telemetry` in `src/ingestion/influx_writer.py`, matching this setup.
