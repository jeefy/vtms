"""MQTT client wrapper for ESP32 analog sensors.

Thin wrapper around umqtt.robust with topic prefix management.
"""

try:
    from umqtt.robust import MQTTClient
except ImportError:
    MQTTClient = None

from config import MQTT_BROKER, MQTT_PORT, MQTT_CLIENT_PREFIX, MQTT_TOPIC_PREFIX


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


def publish(client, subtopic, value):
    """Publish a value to a subtopic under the configured prefix.

    Full topic: lemons/analog/<subtopic>
    """
    topic = "{}/{}".format(MQTT_TOPIC_PREFIX, subtopic)
    msg = str(value)
    client.publish(topic.encode(), msg.encode())
