"""Main loop: read analog temperature sensor, publish voltage to MQTT.

Runs after boot.py connects to WiFi. Reads an analog temperature sensor
on a single ADC pin and publishes the voltage reading to MQTT.
"""

import time

try:
    from machine import ADC, Pin, reset
    import network
except ImportError:
    ADC = None
    Pin = None
    reset = None

from config import (
    TEMP_ADC_PIN,
    MQTT_TOPIC,
    POLL_INTERVAL_MS,
)
from sensors import adc_to_voltage
import mqtt_client
from boot import connect_wifi


def setup_adc(pin_num):
    """Configure an ADC channel on the given GPIO pin."""
    adc = ADC(Pin(pin_num))
    adc.atten(ADC.ATTN_11DB)
    adc.width(ADC.WIDTH_12BIT)
    return adc


def main():
    """Main temperature reading loop."""
    print("Temp sensor: starting")

    boot_count_reset = False

    temp_adc = setup_adc(TEMP_ADC_PIN)

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

    print("Temp sensor: monitoring started")

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

            # Read ADC and convert to voltage
            raw = temp_adc.read()
            voltage = adc_to_voltage(raw)

            print("Voltage: {:.3f}".format(voltage))
            mqtt_client.publish(mqtt, MQTT_TOPIC, "{:.3f}".format(voltage))

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
