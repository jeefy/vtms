"""Sensor conversion functions for ESP32 analog temperature sensor.

Pure math functions testable on host CPython.
"""

from config import V_REF


def adc_to_voltage(raw, bits=12):
    """Convert raw ADC count to voltage."""
    max_count = (1 << bits) - 1
    if max_count == 0:
        return 0.0
    return raw / max_count * V_REF
