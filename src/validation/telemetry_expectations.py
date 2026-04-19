REQUIRED_FIELDS = [
    "node_id",
    "timestamp",
    "voltage",
    "current",
    "power",
    "energy_wh",
]


def validate_telemetry(data):
    """Check whether one telemetry message has the required fields and values."""

    for field in REQUIRED_FIELDS:
        if field not in data:
            return False, f"Missing required field: {field}"

    if not isinstance(data["node_id"], str):
        return False, "Field 'node_id' must be a string"

    if not isinstance(data["timestamp"], int):
        return False, "Field 'timestamp' must be an integer"

    if data["timestamp"] <= 0:
        return False, "Field 'timestamp' must be positive"

    if len(str(data["timestamp"])) != 13:
        return False, "Field 'timestamp' must be a valid epoch ms value"

    for field in ["voltage", "current", "power", "energy_wh"]:
        if not isinstance(data[field], (int, float)):
            return False, f"Field '{field}' must be a number"

    if not 200 <= data["voltage"] <= 250:
        return False, "Field 'voltage' must be between 200 and 250"

    if data["current"] <= 0:
        return False, "Field 'current' must be greater than 0"

    if data["power"] <= 0:
        return False, "Field 'power' must be greater than 0"

    if data["energy_wh"] < 0:
        return False, "Field 'energy_wh' must be a non-negative number"

    return True, "Telemetry data is valid"
