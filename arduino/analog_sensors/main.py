"""Main loop: read analog sensors, convert, publish to MQTT.

Runs after boot.py connects to WiFi. Reads gauge voltages through
HiLetgo 0-25V voltage divider modules on GPIO34 (fuel) and GPIO35 (oil).
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
    FUEL_ADC_PIN,
    OIL_ADC_PIN,
    FUEL_V_FULL,
    FUEL_V_EMPTY,
    OIL_V_0PSI,
    OIL_V_MAX,
    OIL_MAX_PSI,
    POLL_INTERVAL,
    EMA_ALPHA,
    MQTT_TOPIC_PREFIX,
    DEBUG,
)
from sensors import (
    adc_to_voltage,
    voltage_to_fuel_level,
    voltage_to_oil_pressure,
    ema_smooth,
)
import mqtt_client
from boot import connect_wifi


def setup_adc(pin_num):
    """Configure an ADC channel on the given GPIO pin."""
    adc = ADC(Pin(pin_num))
    adc.atten(ADC.ATTN_11DB)  # 0-3.6V range
    adc.width(ADC.WIDTH_12BIT)  # 0-4095
    return adc


def _topic(name):
    """Build full MQTT topic from prefix and name."""
    return "{}/{}".format(MQTT_TOPIC_PREFIX, name)


def main():
    """Main sensor loop."""
    print("Analog sensors: starting")

    boot_count_reset = False

    # Set up ADC channels
    fuel_adc = setup_adc(FUEL_ADC_PIN)
    oil_adc = setup_adc(OIL_ADC_PIN)

    # Connect MQTT
    mqtt = None
    while mqtt is None:
        try:
            mqtt = mqtt_client.connect()
        except Exception as e:
            print("MQTT connect failed:", e)
            time.sleep(5)

    # Smoothed values (None = first reading)
    fuel_smoothed = None
    oil_smoothed = None

    print("Analog sensors: monitoring started")

    while True:
        try:
            # Check WiFi
            wlan = network.WLAN(network.STA_IF)
            if not wlan.isconnected():
                print("WiFi: disconnected, reconnecting...")
                connect_wifi()
                try:
                    mqtt = mqtt_client.connect()
                except Exception as e:
                    print("MQTT reconnect failed:", e)
                    time.sleep(POLL_INTERVAL)
                    continue

            # Read ADC (voltage after HiLetgo 5:1 divider)
            fuel_raw = fuel_adc.read()
            oil_raw = oil_adc.read()

            fuel_voltage = adc_to_voltage(fuel_raw)
            oil_voltage = adc_to_voltage(oil_raw)

            # Publish debug voltages for calibration
            if DEBUG:
                mqtt_client.publish(
                    mqtt, _topic("raw/a0_voltage"), "{:.4f}".format(fuel_voltage)
                )
                mqtt_client.publish(
                    mqtt, _topic("raw/a1_voltage"), "{:.4f}".format(oil_voltage)
                )

            # Smooth voltages
            fuel_smoothed = ema_smooth(fuel_voltage, fuel_smoothed, EMA_ALPHA)
            oil_smoothed = ema_smooth(oil_voltage, oil_smoothed, EMA_ALPHA)

            # Convert and publish fuel level
            fuel_level = voltage_to_fuel_level(fuel_smoothed, FUEL_V_FULL, FUEL_V_EMPTY)
            mqtt_client.publish(mqtt, _topic("fuel_level"), "{:.1f}".format(fuel_level))

            # Convert and publish oil pressure
            oil_psi = voltage_to_oil_pressure(
                oil_smoothed, OIL_V_0PSI, OIL_V_MAX, OIL_MAX_PSI
            )
            mqtt_client.publish(mqtt, _topic("oil_pressure"), "{:.1f}".format(oil_psi))

            if not boot_count_reset:
                from ota_update import reset_boot_count

                reset_boot_count()
                boot_count_reset = True

        except OSError as e:
            print("Error:", e)
            try:
                mqtt = mqtt_client.connect()
            except Exception:
                pass

        except Exception as e:
            print("Unexpected error:", e)
            time.sleep(10)
            reset()

        time.sleep(POLL_INTERVAL)


# Run
main()
