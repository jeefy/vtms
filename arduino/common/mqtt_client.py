"""MQTT client wrapper for ESP32 MicroPython devices.

Thin wrapper around umqtt.robust with topic management.
Shared across all MicroPython ESP32 devices.
"""

try:
    from umqtt.robust import MQTTClient
except ImportError:
    MQTTClient = None

try:
    import ujson
except ImportError:
    import json as ujson

import gc

try:
    import network
except ImportError:
    network = None

import time

from config import MQTT_BROKER, MQTT_PORT, MQTT_CLIENT_PREFIX

import ota_update


def _client_id():
    """Generate a unique client ID from the MAC address."""
    import ubinascii

    mac = network.WLAN(network.STA_IF).config("mac")
    suffix = ubinascii.hexlify(mac[-3:]).decode()
    return "{}-{}".format(MQTT_CLIENT_PREFIX, suffix)


def _handle_status_request(client):
    """Build and publish device diagnostics as JSON.

    Publishes to lemons/status/response/{DEVICE_TYPE}.
    """
    from config import DEVICE_TYPE
    from ota_update import HASH_FILE

    fw_hash = ota_update.read_file(HASH_FILE)
    if not fw_hash:
        fw_hash = "unknown"

    wlan = network.WLAN(network.STA_IF)
    response = {
        "device_type": DEVICE_TYPE,
        "client_id": _client_id(),
        "firmware_hash": fw_hash,
        "uptime_s": time.ticks_ms() // 1000,
        "free_mem": gc.mem_free(),
        "wifi_rssi": wlan.status("rssi"),
        "wifi_ssid": wlan.config("essid"),
        "ip": wlan.ifconfig()[0],
    }

    topic = "lemons/status/response/{}".format(DEVICE_TYPE)
    client.publish(topic.encode(), ujson.dumps(response).encode())


def connect(user_callback=None):
    """Create and connect an MQTT client. Returns the client instance.

    If user_callback is provided, non-status messages are forwarded to it.
    Signature: user_callback(topic_bytes, msg_bytes)
    """
    if MQTTClient is None:
        raise RuntimeError(
            "umqtt.robust not installed — flash micropython-umqtt.robust"
        )

    from config import DEVICE_TYPE

    client_id = _client_id()
    client = MQTTClient(client_id, MQTT_BROKER, port=MQTT_PORT, keepalive=60)

    print("MQTT: connecting as", client_id, "to", MQTT_BROKER)
    client.connect()
    print("MQTT: connected")

    status_topics = (
        b"lemons/status/request",
        "lemons/status/request/{}".format(DEVICE_TYPE).encode(),
    )

    def combined_callback(topic, msg):
        if topic in status_topics:
            _handle_status_request(client)
        elif user_callback is not None:
            user_callback(topic, msg)

    client.set_callback(combined_callback)
    client.subscribe(b"lemons/status/request")
    client.subscribe("lemons/status/request/{}".format(DEVICE_TYPE).encode())
    print("MQTT: subscribed to status request topics")

    return client


def publish_firmware_hash(client):
    """Publish the current OTA firmware hash on boot.

    Reads the stored hash from _ota_hash and publishes it to
    lemons/firmware/{DEVICE_TYPE} so operators can verify which
    firmware version is running remotely.
    """
    from config import DEVICE_TYPE
    from ota_update import read_file, HASH_FILE

    fw_hash = read_file(HASH_FILE)
    if not fw_hash:
        fw_hash = "unknown"
    topic = "lemons/firmware/{}".format(DEVICE_TYPE)
    publish(client, topic, fw_hash)
    print("Firmware hash:", fw_hash)


def publish(client, topic, value):
    """Publish a value to an MQTT topic.

    topic: full topic string (e.g. "lemons/temp/oil_F")
    value: will be converted to string
    """
    msg = str(value)
    client.publish(topic.encode(), msg.encode())


def subscribe(client, topic, callback):
    """Subscribe to an MQTT topic with a message callback.

    WARNING: umqtt supports only one global callback. Calling subscribe()
    again with a different callback replaces the previous one.

    callback signature: callback(topic_bytes, msg_bytes)
    """
    client.set_callback(callback)
    client.subscribe(topic.encode())
    print("MQTT: subscribed to", topic)


def subscribe_topic(client, topic):
    """Subscribe to an MQTT topic without setting the callback.

    Use this after connect() to add additional topic subscriptions
    without overwriting the combined callback set by connect().
    """
    client.subscribe(topic.encode())
    print("MQTT: subscribed to", topic)
