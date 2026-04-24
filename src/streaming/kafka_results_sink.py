from pyflink.common.serialization import SimpleStringSchema
from pyflink.datastream.connectors.kafka import (
    KafkaRecordSerializationSchema,
    KafkaSink,
)


def build_kafka_sink():
    """Build the Kafka sink for processed telemetry summaries."""
    return (
        KafkaSink.builder()
        .set_bootstrap_servers("localhost:9092")
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic("energy.telemetry.results")
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .build()
    )
