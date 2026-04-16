import json
import paho.mqtt.client as mqtt
from validator import validate_telemetry


def on_connect(client, userdata, flags, reason_code, properties):
    print("Connected to MQTT broker")
    client.subscribe("energy/nodes/+/telemetry")


def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)

        is_valid, validation_message = validate_telemetry(data)

        if not is_valid:
            print("Invalid telemetry:", validation_message)
            return

        print("Topic:", msg.topic)
        print("Valid telemetry message:", data)

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