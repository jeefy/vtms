"""Main loop: subscribe to MQTT topics, control GPIO LEDs.

Runs after boot.py connects to WiFi. Subscribes to race flag and
pit/box MQTT topics and sets corresponding GPIO pins high/low.
"""

import time

try:
    from machine import Pin, reset
    import network
except ImportError:
    Pin = None
    reset = None

from config import LED_PINS, MQTT_SUBSCRIBE_TOPICS
from led_logic import parse_led_value, topic_to_pin
import mqtt_client
from boot import connect_wifi


# Pin objects (initialized on ESP32 only)
_pin_objects = {}


def _get_pin(pin_num):
    """Get or create a Pin output object."""
    if pin_num not in _pin_objects:
        _pin_objects[pin_num] = Pin(pin_num, Pin.OUT)
    return _pin_objects[pin_num]


def _mqtt_callback(topic, msg):
    """Handle incoming MQTT messages."""
    pin_num = topic_to_pin(topic)
    if pin_num is None:
        return

    value = parse_led_value(msg)
    if value is None:
        return

    pin = _get_pin(pin_num)
    pin.value(value)
    print("LED: {} -> {}".format(topic.decode(), value))


def main():
    """Main LED controller loop."""
    print("LED controller: starting")

    boot_count_reset = False

    # Initialize all LED pins to LOW
    for pin_num in LED_PINS.values():
        pin = _get_pin(pin_num)
        pin.value(0)

    # Connect MQTT and subscribe
    mqtt = None
    while mqtt is None:
        try:
            mqtt = mqtt_client.connect(user_callback=_mqtt_callback)
            for topic in MQTT_SUBSCRIBE_TOPICS:
                mqtt_client.subscribe_topic(mqtt, topic)
        except Exception as e:
            print("MQTT connect failed:", e)
            mqtt = None
            time.sleep(5)

    mqtt_client.publish_firmware_hash(mqtt)

    # Hardware watchdog — resets ESP32 if main loop hangs
    try:
        from machine import WDT

        wdt = WDT(timeout=30000)  # 30 second timeout
    except (ImportError, Exception):
        wdt = None

    print("LED controller: listening")

    while True:
        try:
            # Reconnect MQTT if needed
            if mqtt is None:
                try:
                    mqtt = mqtt_client.connect(user_callback=_mqtt_callback)
                    for topic in MQTT_SUBSCRIBE_TOPICS:
                        mqtt_client.subscribe_topic(mqtt, topic)
                except Exception:
                    print("MQTT reconnect failed, will retry")
                    time.sleep(5)
                    continue

            # Check WiFi
            wlan = network.WLAN(network.STA_IF)
            if not wlan.isconnected():
                print("WiFi: disconnected, reconnecting...")
                connect_wifi()
                try:
                    mqtt = mqtt_client.connect(user_callback=_mqtt_callback)
                    for topic in MQTT_SUBSCRIBE_TOPICS:
                        mqtt_client.subscribe_topic(mqtt, topic)
                except Exception as e:
                    print("MQTT reconnect failed:", e)
                    time.sleep(1)
                    continue

            # Process incoming messages
            mqtt.check_msg()

            if not boot_count_reset:
                from ota_update import reset_boot_count

                reset_boot_count()
                boot_count_reset = True

            if wdt:
                wdt.feed()

        except OSError as e:
            print("Error:", e)
            mqtt = None
            time.sleep(5)
            try:
                mqtt = mqtt_client.connect(user_callback=_mqtt_callback)
                for topic in MQTT_SUBSCRIBE_TOPICS:
                    mqtt_client.subscribe_topic(mqtt, topic)
            except Exception:
                print("MQTT reconnect failed, will retry next loop")

        except Exception as e:
            print("Unexpected error:", e)
            time.sleep(10)
            reset()

        time.sleep_ms(100)


# Run
main()
