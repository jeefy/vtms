"""Main loop: read MAX6675 thermocouple, publish temperature to MQTT.

Runs after boot.py connects to WiFi. Reads a MAX6675 thermocouple
via bit-bang SPI and publishes Fahrenheit temperature to MQTT.
"""

import time

try:
    from machine import Pin, reset
    import network
except ImportError:
    Pin = None
    reset = None

from config import (
    THERMO_CLK,
    THERMO_CS,
    THERMO_DO,
    MQTT_TOPIC,
    POLL_INTERVAL_MS,
)
from max6675 import read_raw, raw_to_celsius, celsius_to_fahrenheit, is_fault
import mqtt_client
from boot import connect_wifi


def main():
    """Main thermocouple reading loop."""
    print("Thermoprobe: starting")

    boot_count_reset = False

    # Set up SPI pins
    clk = Pin(THERMO_CLK, Pin.OUT)
    cs = Pin(THERMO_CS, Pin.OUT)
    do = Pin(THERMO_DO, Pin.IN)
    cs.value(1)  # deselect

    # Connect MQTT
    mqtt = None
    while mqtt is None:
        try:
            mqtt = mqtt_client.connect()
        except Exception as e:
            print("MQTT connect failed:", e)
            time.sleep(5)

    mqtt_client.publish_firmware_hash(mqtt)

    # Hardware watchdog — resets ESP32 if main loop hangs
    try:
        from machine import WDT

        wdt = WDT(timeout=30000)  # 30 second timeout
    except (ImportError, Exception):
        wdt = None

    print("Thermoprobe: monitoring started")

    while True:
        try:
            # Reconnect MQTT if needed
            if mqtt is None:
                try:
                    mqtt = mqtt_client.connect()
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
                    mqtt = mqtt_client.connect()
                except Exception as e:
                    print("MQTT reconnect failed:", e)
                    time.sleep_ms(POLL_INTERVAL_MS)
                    continue

            # Process any pending status requests
            mqtt.check_msg()

            # Check for MQTT-triggered OTA update
            ota_result = mqtt_client.run_pending_ota()
            if ota_result == "updated":
                print("OTA: update applied, rebooting...")
                reset()

            # Read thermocouple
            raw = read_raw(clk, cs, do)

            if is_fault(raw):
                print("Thermoprobe: thermocouple open/fault")
                time.sleep_ms(POLL_INTERVAL_MS)
                continue

            temp_c = raw_to_celsius(raw)
            temp_f = celsius_to_fahrenheit(temp_c)

            print("Temp: {:.1f}F ({:.1f}C)".format(temp_f, temp_c))
            mqtt_client.publish(mqtt, MQTT_TOPIC, "{:.0f}".format(temp_f))

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
                mqtt = mqtt_client.connect()
            except Exception:
                print("MQTT reconnect failed, will retry next loop")

        except Exception as e:
            print("Unexpected error:", e)
            time.sleep(10)
            reset()

        time.sleep_ms(POLL_INTERVAL_MS)


# Run
main()
