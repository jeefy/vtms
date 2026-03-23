"""Tests for MAX6675 thermocouple conversion functions.

Run on host with CPython/pytest. Same functions run on ESP32 MicroPython.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


class TestRawToCelsius:
    """Test raw 16-bit value to Celsius conversion."""

    def test_zero_temp(self):
        from max6675 import raw_to_celsius

        # Bits 3-14 all zero = 0.0C, bit 2 = 0 (no fault)
        raw = 0b0000000000000000
        assert raw_to_celsius(raw) == 0.0

    def test_known_temp(self):
        from max6675 import raw_to_celsius

        # 100.0C = 400 quarter-degrees. 400 = 0b110010000
        # Shifted left by 3: 0b110010000_000 = 0b0000110010000000
        raw = 0b0000110010000000
        assert abs(raw_to_celsius(raw) - 100.0) < 0.5

    def test_max_temp(self):
        from max6675 import raw_to_celsius

        # Max = 1023.75C = 4095 quarter-degrees
        # 4095 = 0b111111111111, shifted left 3: 0b111111111111000
        raw = 0b0111111111111000
        assert abs(raw_to_celsius(raw) - 1023.75) < 0.01

    def test_quarter_degree_resolution(self):
        from max6675 import raw_to_celsius

        # 1 quarter-degree = 0.25C. Value 1 shifted left 3 = 0b1000
        raw = 0b0000000000001000
        assert abs(raw_to_celsius(raw) - 0.25) < 0.01


class TestCelsiusToFahrenheit:
    """Test Celsius to Fahrenheit conversion."""

    def test_freezing(self):
        from max6675 import celsius_to_fahrenheit

        assert abs(celsius_to_fahrenheit(0.0) - 32.0) < 0.01

    def test_boiling(self):
        from max6675 import celsius_to_fahrenheit

        assert abs(celsius_to_fahrenheit(100.0) - 212.0) < 0.01

    def test_body_temp(self):
        from max6675 import celsius_to_fahrenheit

        assert abs(celsius_to_fahrenheit(37.0) - 98.6) < 0.01


class TestIsFault:
    """Test thermocouple open fault detection."""

    def test_no_fault(self):
        from max6675 import is_fault

        raw = 0b0001100100000000  # bit 2 = 0
        assert is_fault(raw) is False

    def test_fault(self):
        from max6675 import is_fault

        raw = 0b0001100100000100  # bit 2 = 1
        assert is_fault(raw) is True
