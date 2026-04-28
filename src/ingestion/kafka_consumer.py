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
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )


def process_telemetry(data):
    is_valid, message = validate_telemetry(data)

    if not is_valid:
        print("Invalid telemetry:", message)
        return False

    print("Valid telemetry from Kafka:", data)

    inserted = insert_telemetry(data)

    if inserted:
        try:
            write_telemetry(data)  
        except Exception as e:
            print("InfluxDB write failed:", e)
            return False
    else:
        print("Skipped InfluxDB write for duplicate telemetry")

    return True


def main():
    consumer = create_consumer()

    print("Kafka consumer started for topic: energy.telemetry")

    for message in consumer:
        try:
            success = process_telemetry(message.value)

            # ✅ commit ONLY after success
            if success:
                consumer.commit()

        except Exception as e:
            print("Error processing message:", e)


if __name__ == "__main__":
    main()
