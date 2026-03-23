"""Tests for sensor conversion functions.

Run on host with CPython/pytest. Same functions run on ESP32 MicroPython.
"""

import sys
import os

# Add parent directory so we can import sensors module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


class TestAdcToVoltage:
    """Test raw ADC count to voltage conversion."""

    def test_zero(self):
        from sensors import adc_to_voltage

        assert adc_to_voltage(0) == 0.0

    def test_max(self):
        from sensors import adc_to_voltage

        v = adc_to_voltage(4095)
        assert abs(v - 3.3) < 0.01

    def test_midpoint(self):
        from sensors import adc_to_voltage

        v = adc_to_voltage(2048)
        assert abs(v - 1.65) < 0.01


class TestVoltageToFuelLevel:
    """Test voltage-to-fuel-level mapping."""

    def test_full(self):
        from sensors import voltage_to_fuel_level

        level = voltage_to_fuel_level(0.20, v_full=0.20, v_empty=0.80)
        assert abs(level - 100.0) < 1.0

    def test_empty(self):
        from sensors import voltage_to_fuel_level

        level = voltage_to_fuel_level(0.80, v_full=0.20, v_empty=0.80)
        assert abs(level - 0.0) < 1.0

    def test_half(self):
        from sensors import voltage_to_fuel_level

        level = voltage_to_fuel_level(0.50, v_full=0.20, v_empty=0.80)
        assert abs(level - 50.0) < 1.0

    def test_clamps_above_full(self):
        from sensors import voltage_to_fuel_level

        level = voltage_to_fuel_level(0.10, v_full=0.20, v_empty=0.80)
        assert level == 100.0

    def test_clamps_below_empty(self):
        from sensors import voltage_to_fuel_level

        level = voltage_to_fuel_level(0.90, v_full=0.20, v_empty=0.80)
        assert level == 0.0

    def test_inverted_calibration(self):
        """Works when v_full > v_empty (different gauge polarity)."""
        from sensors import voltage_to_fuel_level

        level = voltage_to_fuel_level(0.80, v_full=0.80, v_empty=0.20)
        assert abs(level - 100.0) < 1.0

    def test_equal_calibration_returns_zero(self):
        """Graceful handling of bad calibration."""
        from sensors import voltage_to_fuel_level

        level = voltage_to_fuel_level(0.50, v_full=0.50, v_empty=0.50)
        assert level == 0.0


class TestVoltageToOilPressure:
    """Test voltage-to-oil-pressure mapping."""

    def test_zero_pressure(self):
        from sensors import voltage_to_oil_pressure

        psi = voltage_to_oil_pressure(0.15, v_0psi=0.15, v_max=0.70, max_psi=150.0)
        assert abs(psi - 0.0) < 1.0

    def test_max_pressure(self):
        from sensors import voltage_to_oil_pressure

        psi = voltage_to_oil_pressure(0.70, v_0psi=0.15, v_max=0.70, max_psi=150.0)
        assert abs(psi - 150.0) < 1.0

    def test_half_pressure(self):
        from sensors import voltage_to_oil_pressure

        mid = (0.15 + 0.70) / 2  # 0.425
        psi = voltage_to_oil_pressure(mid, v_0psi=0.15, v_max=0.70, max_psi=150.0)
        assert abs(psi - 75.0) < 1.0

    def test_clamps_below_zero(self):
        from sensors import voltage_to_oil_pressure

        psi = voltage_to_oil_pressure(0.05, v_0psi=0.15, v_max=0.70, max_psi=150.0)
        assert psi == 0.0

    def test_clamps_above_max(self):
        from sensors import voltage_to_oil_pressure

        psi = voltage_to_oil_pressure(0.90, v_0psi=0.15, v_max=0.70, max_psi=150.0)
        assert psi == 150.0

    def test_equal_calibration_returns_zero(self):
        from sensors import voltage_to_oil_pressure

        psi = voltage_to_oil_pressure(0.50, v_0psi=0.50, v_max=0.50, max_psi=150.0)
        assert psi == 0.0


class TestEMA:
    """Test exponential moving average smoothing."""

    def test_first_reading(self):
        from sensors import ema_smooth

        result = ema_smooth(100.0, None, alpha=0.3)
        assert result == 100.0

    def test_smoothing(self):
        from sensors import ema_smooth

        result = ema_smooth(100.0, 50.0, alpha=0.3)
        expected = 0.3 * 100.0 + 0.7 * 50.0  # 65.0
        assert abs(result - expected) < 0.01

    def test_no_change(self):
        from sensors import ema_smooth

        result = ema_smooth(50.0, 50.0, alpha=0.3)
        assert abs(result - 50.0) < 0.01
