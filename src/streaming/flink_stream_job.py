from pyflink.datastream import StreamExecutionEnvironment


from src.streaming.mock_source import build_mock_stream
from src.streaming.telemetry_transforms import (
    SummarizeWindow,
    extract_valid_records,
    validate_stream,
    window_records,
    assign_event_time,
)


def build_environment():
    """Create the Flink execution environment."""
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)
    return env


def build_mock_job():
    """Build the mock Flink job."""
    env = build_environment()
    stream = build_mock_stream(env)
    validated = validate_stream(stream)
    validated.print()  # Print validation results for debugging
    valid_records = extract_valid_records(validated)
    event_time_records = assign_event_time(valid_records)
    windowed = window_records(event_time_records)
    summaries = windowed.process(SummarizeWindow())
    summaries.print()  # Print summaries for debugging
    env.execute("streaming-mock-job")


if __name__ == "__main__":
    build_mock_job()
