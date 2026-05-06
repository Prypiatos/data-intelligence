from pyflink.common.typeinfo import Types
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.common.watermark_strategy import WatermarkStrategy

from src.streaming.kafka_source import build_kafka_source
from src.streaming.kafka_results_sink import build_kafka_sink
from src.streaming.telemetry_transforms import (
    SummarizeWindow,
    extract_valid_records,
    validate_stream,
    window_records,
)


def build_environment():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)
    return env


def build_kafka_job():
    env = build_environment()
    source = build_kafka_source()
    sink = build_kafka_sink()
    stream = env.from_source(source, WatermarkStrategy.no_watermarks(), "kafka-source")
    validated = validate_stream(stream)
    valid_records = extract_valid_records(validated)
    windowed = window_records(valid_records)
    summaries = windowed.process(SummarizeWindow(), output_type=Types.STRING())
    summaries.print()
    summaries.sink_to(sink)
    env.execute("streaming-kafka-job")


if __name__ == "__main__":
    build_kafka_job()
