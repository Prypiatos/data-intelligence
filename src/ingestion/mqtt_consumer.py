import json
import paho.mqtt.client as mqtt

from validator import validate_telemetry
from kafka_producer import publish_telemetry, publish_events, publish_health
from db_writer import insert_telemetry
from influx_writer import write_telemetry


def on_connect(client, userdata, flags, reason_code, properties):
    print("Connected to MQTT broker")
    client.subscribe("energy/nodes/+/telemetry")
    client.subscribe("energy/nodes/+/events")
    client.subscribe("energy/nodes/+/health")


def handle_telemetry(topic, data):
    is_valid, validation_message = validate_telemetry(data)

    if not is_valid:
        print("Invalid telemetry:", validation_message)
        return

    print("Topic:", topic)
    print("Valid telemetry message:", data)

    publish_telemetry(data)
    insert_telemetry(data)
    write_telemetry(data)


def handle_event(topic, data):
    print("Topic:", topic)
    print("Event message received:", data)
    publish_events(data)


def handle_health(topic, data):
    print("Topic:", topic)
    print("Health message received:", data)
    publish_health(data)


def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)

        if topic.endswith("/telemetry"):
            handle_telemetry(topic, data)

        elif topic.endswith("/events"):
            handle_event(topic, data)

        elif topic.endswith("/health"):
            handle_health(topic, data)

        else:
            print("Unknown topic:", topic)

    except json.JSONDecodeError:
        print("Error: invalid JSON payload")

    except Exception as error:
        print("Error processing MQTT message:", error)


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect("localhost", 1883, 60)
    client.loop_forever()


if __name__ == "__main__":
    main()
