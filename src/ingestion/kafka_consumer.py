import json

from kafka import KafkaConsumer

from db_writer import insert_telemetry
from influx_writer import write_telemetry
from validator import validate_telemetry


def create_consumer():
    return KafkaConsumer(
        "energy.telemetry",
        bootstrap_servers="localhost:9092",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        group_id="energy-storage-writer",
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )


def process_telemetry(data):
    is_valid, message = validate_telemetry(data)

    if not is_valid:
        print("Invalid telemetry:", message)
        return True

    print("Valid telemetry from Kafka:", data)

    inserted = insert_telemetry(data)

    if inserted is None:
        print("PostgreSQL insert failed")
        return False

    if inserted is False:
        print("Skipped InfluxDB write for duplicate telemetry")
        return True

    try:
        write_telemetry(data)
    except Exception as error:
        print(f"WARNING: InfluxDB write failed for {data.get('node_id')}: {error}")

    return True


def main():
    consumer = create_consumer()

    print("Kafka consumer started for topic: energy.telemetry")

    for message in consumer:
        try:
            success = process_telemetry(message.value)

            if success:
                consumer.commit()

        except Exception as error:
            print("Error processing message:", error)


if __name__ == "__main__":
    main()
