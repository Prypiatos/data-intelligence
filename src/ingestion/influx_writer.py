from influxdb_client import InfluxDBClient, Point, WritePrecision

url = "http://localhost:8086"
token = "energy-token-123"
org = "energy-org"
bucket = "energy_telemetry"

client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api()


def write_telemetry(data):
    try:
        point = (
            Point("telemetry")
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
