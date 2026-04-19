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
    sample_messages = [
        '{"node_id":"plug_01","timestamp":1618032900000,"voltage":230.1,"current":1.78,"power":401.6,"energy_wh":1250.4}',
        '{"node_id":"plug_02","timestamp":"bad_timestamp","voltage":230.0,"current":1.5,"power":345.0,"energy_wh":1200.0}',
        "invalid json",
    ]

    results = process_stream(sample_messages)

    for result in results:
        print(result)
