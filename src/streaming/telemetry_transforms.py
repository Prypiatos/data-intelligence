import json

from pyflink.common import Time, WatermarkStrategy
from pyflink.datastream.functions import ProcessWindowFunction
from pyflink.datastream.window import TumblingProcessingTimeWindows

from src.validation.telemetry_expectations import validate_telemetry

WINDOW_SIZE_MS = 2000


def validate_message(value):
    if not value or value.strip() == "":
        return json.dumps({"status": "invalid", "reason": "Empty message", "data": None})
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return json.dumps({"status": "invalid", "reason": "Invalid JSON", "data": None})

    is_valid, message = validate_telemetry(payload)
    return json.dumps({
        "status": "valid" if is_valid else "invalid",
        "reason": message,
        "data": payload,
    })


def validate_stream(stream):
    return stream.map(validate_message)


def extract_valid_records(stream):
    return (
        stream.map(json.loads)
        .filter(lambda record: record["status"] == "valid")
        .map(lambda record: record["data"])
    )


def assign_event_time(stream):
    return stream.assign_timestamps_and_watermarks(WatermarkStrategy.no_watermarks())


def window_records(stream):
    return stream.key_by(lambda record: record["node_id"]).window(
        TumblingProcessingTimeWindows.of(Time.milliseconds(WINDOW_SIZE_MS))
    )


class SummarizeWindow(ProcessWindowFunction):
    def process(self, key, context, elements):
        records = list(elements)
        powers = [r["power"] for r in records]
        voltages = [r["voltage"] for r in records]
        currents = [r["current"] for r in records]
        energies = [r["energy_wh"] for r in records]
        return [
            json.dumps({
                "window_start": context.window().start,
                "window_end": context.window().end,
                "node_id": key,
                "avg_power": sum(powers) / len(powers),
                "max_power": max(powers),
                "avg_voltage": sum(voltages) / len(voltages),
                "avg_current": sum(currents) / len(currents),
                "avg_energy_wh": sum(energies) / len(energies),
                "record_count": len(records),
            })
        ]
