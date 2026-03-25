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

_cached_client_id = None
_ota_pending = False


def _client_id():
    """Generate a unique client ID from the MAC address.

    Result is cached — the MAC address never changes at runtime.
    """
    global _cached_client_id
    if _cached_client_id is not None:
        return _cached_client_id
    import ubinascii

    mac = network.WLAN(network.STA_IF).config("mac")
    suffix = ubinascii.hexlify(mac[-3:]).decode()
    _cached_client_id = "{}-{}".format(MQTT_CLIENT_PREFIX, suffix)
    return _cached_client_id


def _handle_status_request(client):
    """Build and publish device diagnostics as JSON.

    Publishes to lemons/status/response/{DEVICE_TYPE}.
    Errors are caught and printed — status should never crash the main loop.
    """
    try:
        from config import DEVICE_TYPE
        from ota_update import HASH_FILE

        fw_hash = ota_update.read_file(HASH_FILE)
        if not fw_hash:
            fw_hash = "unknown"

        free_mem = gc.mem_free()
        wlan = network.WLAN(network.STA_IF)
        response = {
            "device_type": DEVICE_TYPE,
            "client_id": _client_id(),
            "firmware_hash": fw_hash,
            "uptime_s": time.ticks_ms() // 1000,
            "free_mem": free_mem,
            "wifi_rssi": wlan.status("rssi"),
            "wifi_ssid": wlan.config("essid"),
            "ip": wlan.ifconfig()[0],
        }

        topic = "lemons/status/response/{}".format(DEVICE_TYPE)
        client.publish(topic.encode(), ujson.dumps(response).encode())
    except Exception as e:
        print("Status request failed:", e)


def _handle_ota_notification(topic, msg):
    """Check OTA hash notification and flag for update if firmware has changed.

    Compares the announced hash against the locally stored hash.
    If they differ (and a local hash exists), sets _ota_pending flag
    so the main loop can safely apply the OTA update.

    Errors are caught and printed — OTA notification should never crash
    the main loop.
    """
    global _ota_pending
    try:
        payload = ujson.loads(msg)
        server_hash = payload.get("hash", "")
        if not server_hash:
            return

        from ota_update import HASH_FILE

        local_hash = ota_update.read_file(HASH_FILE)
        if not local_hash:
            # First boot or no hash file — boot.py already ran OTA check
            return

        if server_hash != local_hash:
            print("OTA: new firmware detected, flagging for update")
            _ota_pending = True
    except Exception as e:
        print("OTA notification error:", e)


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

    ota_topic = "vtms/ota/{}/notify".format(DEVICE_TYPE).encode()

    def combined_callback(topic, msg):
        if topic in status_topics:
            _handle_status_request(client)
        elif topic == ota_topic:
            _handle_ota_notification(topic, msg)
        elif user_callback is not None:
            user_callback(topic, msg)

    client.set_callback(combined_callback)
    client.subscribe(b"lemons/status/request")
    client.subscribe("lemons/status/request/{}".format(DEVICE_TYPE).encode())
    client.subscribe(ota_topic)
    print("MQTT: subscribed to status request and OTA notification topics")

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
    publish(client, topic, fw_hash, retain=True)
    print("Firmware hash:", fw_hash)


def ota_pending():
    """Check if an OTA update has been flagged by MQTT notification."""
    return _ota_pending


def run_pending_ota():
    """If OTA is pending, attempt the update.

    Returns "updated", "current", "error", or None if no OTA was pending.
    Clears the pending flag regardless of outcome.
    """
    global _ota_pending
    if not _ota_pending:
        return None
    _ota_pending = False
    from config import OTA_SERVER, DEVICE_TYPE

    print("OTA: running pending update check")
    return ota_update.check_and_update(OTA_SERVER, DEVICE_TYPE)


def publish(client, topic, value, retain=False):
    """Publish a value to an MQTT topic.

    topic: full topic string (e.g. "lemons/temp/oil_F")
    value: will be converted to string
    retain: if True, broker stores the message for new subscribers
    """
    msg = str(value)
    client.publish(topic.encode(), msg.encode(), retain=retain)


def subscribe(client, topic, callback):
    """Subscribe to an MQTT topic with a message callback.

    WARNING: umqtt supports only one global callback. Calling subscribe()
    again with a different callback replaces the previous one.

    DEPRECATED: Use subscribe_topic() instead to avoid overwriting the
    combined callback set by connect().

    callback signature: callback(topic_bytes, msg_bytes)
    """
    print(
        "WARNING: subscribe() overwrites the combined callback set by"
        " connect(). Use subscribe_topic() instead."
    )
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
