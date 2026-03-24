"""ADC conversion utilities shared across ESP32 sensor devices.

Pure math — no hardware dependencies. Testable on host CPython.
"""


def adc_to_voltage(raw, bits=12, v_ref=3.3):
    """Convert raw ADC count to voltage.

    ESP32 ADC is 12-bit (0-4095) with 11dB attenuation for ~0-3.3V range.
    v_ref defaults to 3.3V but can be overridden per-device.
    """
    max_count = (1 << bits) - 1
    if max_count == 0:
        return 0.0
    return raw / max_count * v_ref
