import json
from kafka import KafkaProducer


producer = KafkaProducer(
    bootstrap_servers="localhost:9092",
    value_serializer=lambda value: json.dumps(value).encode("utf-8"),
)


def publish_telemetry(data):
    producer.send("energy.telemetry", data)
    producer.flush()
    print("Sent to Kafka topic: energy.telemetry")