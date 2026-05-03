from pathlib import Path

from pyflink.common.typeinfo import Types
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.common.watermark_strategy import WatermarkStrategy

from src.streaming.kafka_source import build_kafka_source
from src.streaming.kafka_results_sink import build_kafka_sink
from src.streaming.telemetry_transforms import (
    SummarizeWindow,
    assign_event_time,
    extract_valid_records,
    validate_stream,
    window_records,
)


def build_environment():
    """Create the Flink execution environment."""
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)

    project_root = Path(__file__).resolve().parents[2]
    flink_kafka_jar = project_root / "lib" / "flink-connector-kafka-1.17.2.jar"
    kafka_clients_jar = project_root / "lib" / "kafka-clients-3.2.3.jar"
    env.add_jars(
        flink_kafka_jar.as_uri(),
        kafka_clients_jar.as_uri(),
    )

    return env


def build_kafka_job():
    """Build the Kafka Flink job."""
    env = build_environment()
    source = build_kafka_source()
    sink = build_kafka_sink()
    # Kafka records are raw JSON strings here; event time is assigned after validation.
    stream = env.from_source(source, WatermarkStrategy.no_watermarks(), "kafka-source")
    validated = validate_stream(stream)
    validated.print()
    valid_records = extract_valid_records(validated)
    event_time_records = assign_event_time(valid_records)
    windowed = window_records(event_time_records)
    summaries = windowed.process(SummarizeWindow(), output_type=Types.STRING())
    summaries.print()
    summaries.sink_to(sink)
    env.execute("streaming-kafka-job")


if __name__ == "__main__":
    build_kafka_job()
