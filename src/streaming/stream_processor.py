import json

from src.validation.telemetry_expectations import validate_telemetry


def parse_message(message):
    """Convert one JSON message string into a Python dictionary."""
    try:
        return json.loads(message)
    except json.JSONDecodeError:
        return None


def process_message(message):
    """Parse and validate one telemetry message."""
    data = parse_message(message)

    if data is None:
        return {
            "status": "invalid",
            "reason": "Invalid JSON format",
            "data": message,
        }

    is_valid, validation_message = validate_telemetry(data)

    if is_valid:
        return {
            "status": "valid",
            "reason": validation_message,
            "data": data,
        }

    return {
        "status": "invalid",
        "reason": validation_message,
        "data": data,
    }


def process_stream(messages):
    """Process many messages one by one and return all results."""
    results = []

    for message in messages:
        result = process_message(message)
        results.append(result)

    return results


if __name__ == "__main__":

    # open the sample data file and load the energy readings
    with open ("tests/fixtures/energy-readings.json", "r") as f:
        records = json.load(f)
        energy_readings = []

        for record in records:
            message = json.dumps(record)
            energy_readings.append(message)




    results = process_stream(energy_readings)

    for result in results:
        print(result)
