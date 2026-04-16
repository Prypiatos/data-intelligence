def validate_telemetry(data):
    required_fields = ["node_id", "timestamp", "voltage", "current", "power", "energy_wh"]

    for field in required_fields:
        if field not in data:
            return False, f"Missing field: {field}"

    if not isinstance(data["node_id"], str):
        return False, "node_id must be a string"

    if not isinstance(data["timestamp"], int):
        return False, "timestamp must be an integer"

    numeric_fields = ["voltage", "current", "power", "energy_wh"]
    for field in numeric_fields:
        if not isinstance(data[field], (int, float)):
            return False, f"{field} must be a number"
        if data[field] < 0:
            return False, f"{field} cannot be negative"

    return True, "Valid telemetry message"