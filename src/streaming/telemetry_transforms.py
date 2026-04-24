import json

from pyflink.common import Time, WatermarkStrategy
from pyflink.datastream.functions import ProcessWindowFunction
from pyflink.datastream.window import TumblingEventTimeWindows
from pyflink.common.watermark_strategy import TimestampAssigner

from src.validation.telemetry_expectations import validate_telemetry

WINDOW_SIZE_MS = 2000


def validate_message(value):
    """Validate one telemetry message."""
    payload = json.loads(value)
    is_valid, message = validate_telemetry(payload)

    return json.dumps(
        {
            "status": "valid" if is_valid else "invalid",
            "reason": message,
            "data": payload,
        }
    )


def validate_stream(stream):
    """Validate each incoming JSON message."""
    return stream.map(validate_message)


def extract_valid_records(stream):
    """Keep only valid telemetry records."""
    return (
        stream.map(json.loads)
        .filter(lambda record: record["status"] == "valid")
        .map(lambda record: record["data"])
    )


class TelemetryTimestampAssigner(TimestampAssigner):
    """Assign event time timestamps based on the 'timestamp' field in telemetry records."""

    def extract_timestamp(self, value, record_timestamp):
        """Extract the timestamp from the telemetry record."""
        return value["timestamp"]


def assign_event_time(stream):
    """Assign event time stamps to the stream based on the 'timestamp' field in telemetry records."""
    watermark_strategy = (
        WatermarkStrategy.for_monotonous_timestamps().with_timestamp_assigner(
            TelemetryTimestampAssigner()
        )
    )
    return stream.assign_timestamps_and_watermarks(watermark_strategy)


def window_records(stream):
    """Group valid records into 2-second windows."""
    return stream.key_by(lambda record: "all").window(
        TumblingEventTimeWindows.of(Time.milliseconds(WINDOW_SIZE_MS))
    )


class SummarizeWindow(ProcessWindowFunction):
    """Build one summary for each time window."""

    def process(self, key, context, elements):
        records = list(elements)
        return [
            json.dumps(
                {
                    "window_start": context.window().start,
                    "window_end": context.window().end,
                    "record_count": len(records),
                }
            )
        ]
