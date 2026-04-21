def validate_telemetry(data):
    required_fields = [
        "node_id",
        "timestamp",
        "voltage",
        "current",
        "power",
        "energy_wh",
    ]

    # Ensure the record contains exactly the required fields
    if set(data.keys()) != set(required_fields):
        return False, "Telemetry record must contain exactly the required fields"

    # node_id must be a non-empty string
    if not isinstance(data["node_id"], str) or not data["node_id"].strip():
        return False, "node_id must be a non-empty string"

    # timestamp must be an integer and 13 digits (epoch milliseconds)
    if not isinstance(data["timestamp"], int):
        return False, "timestamp must be an integer"

    if not 1000000000000 <= data["timestamp"] <= 9999999999999:
        return False, "timestamp must be a 13-digit epoch in milliseconds"

    # voltage must be numeric and within 200-250V
    if not isinstance(data["voltage"], (int, float)):
        return False, "voltage must be a number"

    if not 200 <= data["voltage"] <= 250:
        return False, "voltage must be between 200 and 250"

    # current must be numeric and greater than 0
    if not isinstance(data["current"], (int, float)):
        return False, "current must be a number"

    if data["current"] <= 0:
        return False, "current must be greater than 0"

    # power must be numeric and greater than 0
    if not isinstance(data["power"], (int, float)):
        return False, "power must be a number"

    if data["power"] <= 0:
        return False, "power must be greater than 0"

    # energy_wh must be numeric and non-negative
    if not isinstance(data["energy_wh"], (int, float)):
        return False, "energy_wh must be a number"

    if data["energy_wh"] < 0:
        return False, "energy_wh cannot be negative"

    return True, "Valid telemetry message"
