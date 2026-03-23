"""MAX6675 thermocouple driver for MicroPython.

Bit-bang SPI read of the MAX6675 16-bit output.
Pure conversion functions are testable on host CPython.
"""

try:
    from machine import Pin
    import time
except ImportError:
    Pin = None
    time = None


def raw_to_celsius(raw):
    """Convert raw 16-bit MAX6675 value to temperature in Celsius.

    Bits 14-3 contain the temperature in 0.25C increments.
    """
    temp_bits = (raw >> 3) & 0x0FFF
    return temp_bits * 0.25


def celsius_to_fahrenheit(celsius):
    """Convert Celsius to Fahrenheit."""
    return celsius * 9.0 / 5.0 + 32.0


def is_fault(raw):
    """Check if thermocouple is open (bit 2 of raw value)."""
    return bool(raw & 0x04)


def read_raw(clk_pin, cs_pin, do_pin):
    """Read 16-bit raw value from MAX6675 via bit-bang SPI.

    Requires machine.Pin objects. Only runs on ESP32.
    """
    cs_pin.value(0)
    time.sleep_us(10)

    raw = 0
    for _ in range(16):
        clk_pin.value(1)
        time.sleep_us(10)
        raw <<= 1
        if do_pin.value():
            raw |= 1
        clk_pin.value(0)
        time.sleep_us(10)

    cs_pin.value(1)
    return raw
