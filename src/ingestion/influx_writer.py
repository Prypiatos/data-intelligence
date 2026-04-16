from influxdb_client import InfluxDBClient, Point, WritePrecision

# InfluxDB config (same as docker-compose)
url = "http://localhost:8086"
token = "energy-token-123"
org = "energy-org"
bucket = "energy_data"

client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api()


def write_telemetry(data):
    try:
        point = (
            Point("energy_metrics")
            .tag("node_id", data["node_id"])
            .field("voltage", float(data["voltage"]))
            .field("current", float(data["current"]))
            .field("power", float(data["power"]))
            .field("energy_wh", float(data["energy_wh"]))
            .time(data["timestamp"], WritePrecision.MS)
        )

        write_api.write(bucket=bucket, org=org, record=point)

        print("Inserted into InfluxDB")

    except Exception as e:
        print("InfluxDB error:", e)