from validator import validate_telemetry

# Valid data
valid_data = {
    "node_id": "plug_01",
    "timestamp": 1710000000000,
    "voltage": 230,
    "current": 1.5,
    "power": 350,
    "energy_wh": 1200
}

# Invalid data (missing field)
invalid_data = {
    "node_id": "plug_01",
    "timestamp": 1710000000000,
    "voltage": 230
}

print("Valid test:", validate_telemetry(valid_data))
print("Invalid test:", validate_telemetry(invalid_data))