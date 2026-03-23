"""Sensor conversion functions for ESP32 analog readings.

Pure math -- no hardware dependencies. Runs on both CPython (tests)
and MicroPython (ESP32).
"""

# Default reference voltage (can be overridden by config on ESP32)
_V_REF = 3.3


def adc_to_voltage(raw, bits=12):
    """Convert raw ADC count to voltage.

    ESP32 ADC is 12-bit (0-4095) with 11dB attenuation for ~0-3.3V range.
    """
    max_count = (1 << bits) - 1
    if max_count == 0:
        return 0.0
    return raw / max_count * _V_REF


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
