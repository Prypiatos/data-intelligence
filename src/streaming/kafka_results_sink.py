import os

from pyflink.common.serialization import SimpleStringSchema
from pyflink.datastream.connectors.kafka import (
    KafkaRecordSerializationSchema,
    KafkaSink,
)


def build_kafka_sink():
    """Build the Kafka sink for processed telemetry summaries."""
    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

    return (
        KafkaSink.builder()
        .set_bootstrap_servers(bootstrap_servers)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic("energy.telemetry.results")
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .build()
    )
