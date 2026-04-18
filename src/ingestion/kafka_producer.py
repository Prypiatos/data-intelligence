import json
from kafka import KafkaProducer

producer = None


def get_producer():
    global producer

    if producer is None:
        producer = KafkaProducer(
            bootstrap_servers="localhost:9092",
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
        )

    return producer


def publish_telemetry(data):
    kafka_producer = get_producer()
    kafka_producer.send("energy.telemetry", data)
    kafka_producer.flush()
    print("Sent to Kafka topic: energy.telemetry")


def publish_events(data):
    kafka_producer = get_producer()
    kafka_producer.send("energy.events", data)
    kafka_producer.flush()
    print("Sent to Kafka topic: energy.events")


def publish_health(data):
    kafka_producer = get_producer()
    kafka_producer.send("energy.health", data)
    kafka_producer.flush()
    print("Sent to Kafka topic: energy.health")