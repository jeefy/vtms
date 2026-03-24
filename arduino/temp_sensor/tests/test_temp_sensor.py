"""Tests for temp sensor voltage conversion.

Run on host with CPython/pytest.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "common"))

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

    def test_quarter(self):
        from sensors import adc_to_voltage

        v = adc_to_voltage(1024)
        assert abs(v - 0.825) < 0.01
