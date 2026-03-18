"""Utility functions for frequency parsing, dB conversion, and helpers."""

import re

import numpy as np

__all__ = [
    "RTL_SDR_MAX_FREQ",
    "RTL_SDR_MIN_FREQ",
    "VALID_MODULATIONS",
    "db_to_power",
    "estimate_scan_time",
    "format_frequency",
    "generate_frequency_list",
    "iq_power_db",
    "parse_frequency",
    "power_to_db",
    "validate_frequency",
]


# RTL-SDR frequency range (Hz)
RTL_SDR_MIN_FREQ = 24_000_000  # 24 MHz
RTL_SDR_MAX_FREQ = 1_766_000_000  # 1.766 GHz

VALID_MODULATIONS = ("fm", "am", "ssb")


def parse_frequency(freq_str: str) -> int:
    """Parse a frequency string with suffix into Hz.

    Supports suffixes: Hz, k/kHz, M/MHz, G/GHz (case-insensitive).
    Plain numbers are treated as Hz.

    Examples:
        "146.52M"   -> 146_520_000
        "146.52MHz" -> 146_520_000
        "7200k"     -> 7_200_000
        "7200kHz"   -> 7_200_000
        "1.42G"     -> 1_420_000_000
        "1420000000" -> 1_420_000_000

    Raises:
        ValueError: If the frequency string cannot be parsed.
    """
    freq_str = freq_str.strip()

    multipliers = {
        "ghz": 1_000_000_000,
        "g": 1_000_000_000,
        "mhz": 1_000_000,
        "m": 1_000_000,
        "khz": 1_000,
        "k": 1_000,
        "hz": 1,
    }

    # Try matching number + optional suffix
    match = re.match(
        r"^([0-9]*\.?[0-9]+)\s*(ghz|mhz|khz|g|m|k|hz)?$",
        freq_str,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError(
            f"Invalid frequency '{freq_str}'. "
            "Use format like 146.52M, 7200k, or 1420000000"
        )

    value = float(match.group(1))
    suffix = (match.group(2) or "hz").lower()
    multiplier = multipliers[suffix]

    freq_hz = int(value * multiplier)
    return freq_hz


def validate_frequency(freq_hz: int) -> None:
    """Validate that a frequency is within RTL-SDR range.

    Raises:
        ValueError: If frequency is out of range.
    """
    if freq_hz < RTL_SDR_MIN_FREQ or freq_hz > RTL_SDR_MAX_FREQ:
        raise ValueError(
            f"Frequency {format_frequency(freq_hz)} is out of RTL-SDR range "
            f"({format_frequency(RTL_SDR_MIN_FREQ)} - "
            f"{format_frequency(RTL_SDR_MAX_FREQ)})"
        )


def format_frequency(freq_hz: int) -> str:
    """Format a frequency in Hz to a human-readable string.

    Examples:
        146_520_000  -> "146.520 MHz"
        7_200_000    -> "7.200 MHz"
        1_420_000_000 -> "1.420 GHz"
    """
    if freq_hz >= 1_000_000_000:
        return f"{freq_hz / 1_000_000_000:.3f} GHz"
    elif freq_hz >= 1_000_000:
        return f"{freq_hz / 1_000_000:.3f} MHz"
    elif freq_hz >= 1_000:
        return f"{freq_hz / 1_000:.3f} kHz"
    else:
        return f"{freq_hz} Hz"


def power_to_db(power: float | np.floating) -> float:
    """Convert linear power to dB (10 * log10).

    Returns -100.0 for zero or negative power to avoid log errors.
    """
    if power <= 0:
        return -100.0
    return float(10.0 * np.log10(float(power)))


def db_to_power(db: float) -> float:
    """Convert dB to linear power (10^(dB/10))."""
    return float(np.power(10.0, db / 10.0))


def generate_frequency_list(start_hz: int, end_hz: int, step_hz: int) -> list[int]:
    """Generate a list of frequencies from start to end with given step.

    Both start and end are inclusive.

    Raises:
        ValueError: If parameters are invalid.
    """
    if start_hz >= end_hz:
        raise ValueError(
            f"Start frequency ({format_frequency(start_hz)}) must be less than "
            f"end frequency ({format_frequency(end_hz)})"
        )
    if step_hz <= 0:
        raise ValueError("Step size must be positive")

    freqs = []
    freq = start_hz
    while freq <= end_hz:
        freqs.append(freq)
        freq += step_hz
    return freqs


def estimate_scan_time(num_channels: int, dwell_time_ms: int = 100) -> float:
    """Estimate scan time in seconds for a given number of channels.

    Args:
        num_channels: Number of frequencies to scan.
        dwell_time_ms: Time spent on each frequency in milliseconds.

    Returns:
        Estimated time in seconds.
    """
    return num_channels * dwell_time_ms / 1000.0


def iq_power_db(iq_samples: np.ndarray) -> float:
    """Compute mean power of IQ samples in dB.

    Args:
        iq_samples: Complex64 numpy array of IQ samples.

    Returns:
        Power in dB (10 * log10(mean(|IQ|^2))). Returns -100.0 for silence.
    """
    power = float(np.mean(np.abs(iq_samples) ** 2))
    if power <= 0:
        return -100.0
    return float(10.0 * np.log10(power))
