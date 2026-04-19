
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

    for field in ["voltage", "current", "power", "energy_wh"]:
        if not isinstance(data[field], (int, float)):
            return False, f"Field '{field}' must be a number"

    if data["voltage"] <= 0:
        return False, "Field 'voltage' must be greater than 0"

    for field in ["current", "power", "energy_wh"]:
        if data[field] < 0:
            return False, f"Field '{field}' must be a non-negative number"

    return True, "Telemetry data is valid"
