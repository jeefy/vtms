"""Sensor conversion functions for ESP32 analog readings.

Pure math -- no hardware dependencies. Runs on both CPython (tests)
and MicroPython (ESP32).
"""

from adc_utils import adc_to_voltage  # noqa: F401 (re-exported for main.py)


def voltage_to_fuel_level(voltage, v_full, v_empty):
    """Map tap voltage to fuel level percentage.

    Calibrated empirically from debug readings at known fuel states.
    Linear interpolation between calibrated endpoints.
    """
    if v_full == v_empty:
        return 0.0
    level = (voltage - v_empty) / (v_full - v_empty) * 100.0
    return max(0.0, min(100.0, level))


def voltage_to_oil_pressure(voltage, v_0psi, v_max, max_psi):
    """Map tap voltage to oil pressure in PSI.

    Calibrated empirically from debug readings at known pressures.
    Linear interpolation between calibrated endpoints.
    """
    if v_max == v_0psi:
        return 0.0
    psi = (voltage - v_0psi) / (v_max - v_0psi) * max_psi
    return max(0.0, min(max_psi, psi))


def ema_smooth(new_value, prev_smoothed, alpha=0.3):
    """Exponential moving average filter.

    alpha: weight for new value (0-1). Higher = less smoothing.
    If prev_smoothed is None (first reading), returns new_value.
    """
    if prev_smoothed is None:
        return new_value
    return alpha * new_value + (1.0 - alpha) * prev_smoothed
