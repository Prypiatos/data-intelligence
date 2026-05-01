import json
from pathlib import Path

MOCK_FIXTURE_PATH = Path("tests/fixtures/energy-readings.json")


def load_mock_messages(path=MOCK_FIXTURE_PATH):
    """Load mock telemetry records and convert them to JSON strings."""
    with open(path, "r", encoding="utf-8") as file:
        records = json.load(file)

    return [json.dumps(record) for record in records]


def build_mock_stream(env):
    """Build a Flink stream from mock telemetry messages."""
    messages = load_mock_messages()
    return env.from_collection(messages)
