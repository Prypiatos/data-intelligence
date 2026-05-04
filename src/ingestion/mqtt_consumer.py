import json
import os

import paho.mqtt.client as mqtt

from kafka_producer import publish_events, publish_health, publish_telemetry
from validator import validate_telemetry

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))


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

    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_forever()


if __name__ == "__main__":
    main()
