import json

from src.validation.telemetry_expectations import validate_telemetry

INPUT_TOPIC = "energy.telemetry"
OUTPUT_TOPIC = "energy.telemetry.results"


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
            "source_topic": INPUT_TOPIC,
            "target_topic": OUTPUT_TOPIC,
            "status": "invalid",
            "reason": "Invalid JSON format",
            "data": message,
        }

    is_valid, validation_message = validate_telemetry(data)

    if is_valid:
        return {
            "source_topic": INPUT_TOPIC,
            "target_topic": OUTPUT_TOPIC,
            "status": "valid",
            "reason": validation_message,
            "data": data,
        }

    return {
        "source_topic": INPUT_TOPIC,
        "target_topic": OUTPUT_TOPIC,
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


def summarize_windows(results, window_size_ms=2000):
    """Summarize results into time windows."""
    window_summaries = {}

    for result in results:
        data = result["data"]

        if result["status"] == "invalid":
            continue

        timestamp = data["timestamp"]
        window_start = (timestamp // window_size_ms) * window_size_ms
        window_end = window_start + window_size_ms - 1

        if window_start not in window_summaries:
            window_summaries[window_start] = {
                "source_topic": INPUT_TOPIC,
                "target_topic": OUTPUT_TOPIC,
                "window_start": window_start,
                "window_end": window_end,
                "record_count": 0,
            }

        window_summaries[window_start]["record_count"] += 1

    return list(window_summaries.values())


if __name__ == "__main__":

    # open the sample data file and load the energy readings
    with open("tests/fixtures/energy-readings.json", "r") as f:
        records = json.load(f)
        energy_readings = []

        for record in records:
            message = json.dumps(record)
            energy_readings.append(message)

    results = process_stream(energy_readings)
    window_summaries = summarize_windows(results)

    for summary in window_summaries:
        print(summary)
