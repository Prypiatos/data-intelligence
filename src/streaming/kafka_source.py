import os

from pyflink.common.serialization import SimpleStringSchema
from pyflink.datastream.connectors.kafka import KafkaOffsetsInitializer, KafkaSource


def build_kafka_source():
    """Build a kafka source for the telemetry stream."""
    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")

    return (
        KafkaSource.builder()
        .set_bootstrap_servers(bootstrap_servers)
        .set_group_id("stream-processing-group")
        .set_topics("energy.telemetry")
        .set_starting_offsets(KafkaOffsetsInitializer.earliest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )
