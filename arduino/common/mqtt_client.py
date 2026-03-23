"""MQTT client wrapper for ESP32 MicroPython devices.

Thin wrapper around umqtt.robust with topic management.
Shared across all MicroPython ESP32 devices.
"""

try:
    from umqtt.robust import MQTTClient
except ImportError:
    MQTTClient = None

from config import MQTT_BROKER, MQTT_PORT, MQTT_CLIENT_PREFIX


def _client_id():
    """Generate a unique client ID from the MAC address."""
    import network
    import ubinascii

    mac = network.WLAN(network.STA_IF).config("mac")
    suffix = ubinascii.hexlify(mac[-3:]).decode()
    return "{}-{}".format(MQTT_CLIENT_PREFIX, suffix)


def connect():
    """Create and connect an MQTT client. Returns the client instance."""
    client_id = _client_id()
    client = MQTTClient(client_id, MQTT_BROKER, port=MQTT_PORT)

    print("MQTT: connecting as", client_id, "to", MQTT_BROKER)
    client.connect()
    print("MQTT: connected")
    return client


def publish(client, topic, value):
    """Publish a value to an MQTT topic.

    topic: full topic string (e.g. "lemons/temp/oil_F")
    value: will be converted to string
    """
    msg = str(value)
    client.publish(topic.encode(), msg.encode())


def subscribe(client, topic, callback):
    """Subscribe to an MQTT topic with a message callback.

    callback signature: callback(topic_bytes, msg_bytes)
    """
    client.set_callback(callback)
    client.subscribe(topic.encode())
    print("MQTT: subscribed to", topic)
