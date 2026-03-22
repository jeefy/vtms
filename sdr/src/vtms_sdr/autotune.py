"""Auto-tune: dynamic signal probing to determine optimal SDR settings.

Analyzes IQ samples to classify modulation type (FM/AM/SSB) and recommend
gain and squelch settings based on measured signal characteristics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from .utils import power_to_db

logger = logging.getLogger(__name__)

__all__ = [
    "AutoTuneResult",
    "classify_signal",
    "suggest_gain",
    "suggest_squelch",
]

# Classification thresholds (empirically derived from synthetic signals)
#
# Envelope coefficient of variation (std / mean of |IQ|):
#   FM:  ~0.0 (constant envelope)
#   AM:  ~0.3-0.6 depending on modulation depth
#   SSB: ~0.0 (constant envelope, like FM)
#   Noise: ~0.52 (Rayleigh distribution)
_ENVELOPE_CV_THRESHOLD = 0.25

# Spectral asymmetry ratio (upper_power / lower_power or inverse):
#   SSB: >> 3.0 (energy concentrated in one sideband)
#   FM/AM: ~1.0 (roughly symmetric)
_SPECTRAL_ASYMMETRY_THRESHOLD = 3.0

# Power thresholds for gain mapping (dB)
_POWER_STRONG = -10.0
_POWER_MODERATE_HIGH = -20.0
_POWER_MODERATE_LOW = -40.0
_POWER_WEAK = -55.0

# Minimum signal power to attempt classification (below this is noise floor)
_NOISE_FLOOR_DB = -60.0


@dataclass
class AutoTuneResult:
    """Result of signal analysis with recommended settings."""

    modulation: str
    """Detected modulation type: 'fm', 'am', or 'ssb'."""

    gain: float
    """Recommended gain in dB."""

    squelch_db: float
    """Recommended squelch threshold in dB."""

    signal_power_db: float
    """Measured signal power in dB."""

    confidence: float
    """Classification confidence from 0.0 (guess) to 1.0 (certain)."""

    def summary(self) -> str:
        """One-line human-readable summary of the result."""
        return (
            f"Auto-tuned: {self.modulation.upper()} | "
            f"Gain: {self.gain:.1f} dB | "
            f"Squelch: {self.squelch_db:.1f} dB | "
            f"Power: {self.signal_power_db:.1f} dB | "
            f"Confidence: {self.confidence:.0%}"
        )


def classify_signal(
    iq_samples: np.ndarray,
    sample_rate: int,
) -> AutoTuneResult:
    """Analyze IQ samples and return recommended SDR settings.

    Classification pipeline:
      1. Measure signal power.
      2. Compute spectral asymmetry (SSB detection).
      3. Compute envelope coefficient of variation (FM vs AM).
      4. Derive gain and squelch from measured power.

    Args:
        iq_samples: Complex64 numpy array of IQ samples.  At least 1024
            samples are recommended for reliable classification.
        sample_rate: IQ sample rate in samples/second.

    Returns:
        AutoTuneResult with recommended settings.
    """
    # --- Step 1: Power measurement ---
    signal_power = float(np.mean(np.abs(iq_samples) ** 2))
    power_db = power_to_db(signal_power)

    # If below noise floor, return defaults with low confidence
    if power_db < _NOISE_FLOOR_DB:
        logger.info(
            "Signal power %.1f dB below noise floor (%.1f dB), using FM defaults",
            power_db,
            _NOISE_FLOOR_DB,
        )
        return AutoTuneResult(
            modulation="fm",
            gain=suggest_gain(power_db),
            squelch_db=suggest_squelch(power_db),
            signal_power_db=power_db,
            confidence=0.0,
        )

    # --- Step 2: Spectral asymmetry (SSB detection) ---
    asymmetry_ratio, dominant_sideband = _spectral_asymmetry(iq_samples)

    # --- Step 3: Envelope analysis (FM vs AM) ---
    envelope_cv = _envelope_coefficient_of_variation(iq_samples)

    # --- Step 4: Classification decision tree ---
    modulation, confidence = _classify(envelope_cv, asymmetry_ratio)

    logger.info(
        "Auto-tune: power=%.1f dB, envelope_cv=%.3f, "
        "asymmetry=%.2f, classified=%s (%.0f%%)",
        power_db,
        envelope_cv,
        asymmetry_ratio,
        modulation,
        confidence * 100,
    )

    return AutoTuneResult(
        modulation=modulation,
        gain=suggest_gain(power_db),
        squelch_db=suggest_squelch(power_db),
        signal_power_db=power_db,
        confidence=confidence,
    )


def suggest_gain(power_db: float) -> float:
    """Suggest an appropriate gain setting based on measured signal power.

    Maps measured power to a gain value that should place the signal in
    a good dynamic range for the RTL-SDR's 8-bit ADC.

    Args:
        power_db: Measured signal power in dB.

    Returns:
        Suggested gain in dB (0.0 to 49.6 range).
    """
    if power_db > _POWER_STRONG:
        # Very strong signal — use minimal gain to avoid ADC saturation
        return 10.0
    elif power_db > _POWER_MODERATE_HIGH:
        # Strong signal — moderate-low gain
        return 20.0
    elif power_db > _POWER_MODERATE_LOW:
        # Moderate signal — standard gain
        return 30.0
    elif power_db > _POWER_WEAK:
        # Weak signal — higher gain
        return 40.0
    else:
        # Very weak or no signal — maximum useful gain
        return 49.6


def suggest_squelch(power_db: float) -> float:
    """Suggest a squelch threshold based on measured signal power.

    Sets the threshold a few dB below the measured power so the squelch
    opens when the signal is present but stays closed during silence.

    Args:
        power_db: Measured signal power in dB.

    Returns:
        Suggested squelch threshold in dB.
    """
    # Set squelch 6 dB below signal power, but not lower than -60 dB
    return max(power_db - 6.0, -60.0)


def _envelope_coefficient_of_variation(iq_samples: np.ndarray) -> float:
    """Compute the coefficient of variation of the IQ envelope.

    CV = std(|IQ|) / mean(|IQ|)

    FM signals have near-constant envelope (CV ≈ 0).
    AM signals have modulated envelope (CV > 0.25).
    Noise has Rayleigh-distributed envelope (CV ≈ 0.52).

    Args:
        iq_samples: Complex IQ samples.

    Returns:
        Coefficient of variation (0.0 = constant, higher = more variation).
    """
    envelope = np.abs(iq_samples)
    mean_env = float(np.mean(envelope))
    if mean_env < 1e-10:
        return 0.0
    std_env = float(np.std(envelope))
    return std_env / mean_env


def _spectral_asymmetry(
    iq_samples: np.ndarray,
) -> tuple[float, str]:
    """Measure spectral asymmetry between upper and lower sidebands.

    SSB signals concentrate energy in one sideband, producing a high
    asymmetry ratio.  FM and AM signals are roughly symmetric.

    Args:
        iq_samples: Complex IQ samples.

    Returns:
        Tuple of (asymmetry_ratio, dominant_sideband).
        asymmetry_ratio >= 1.0 (ratio of stronger to weaker sideband).
        dominant_sideband is 'upper' or 'lower'.
    """
    fft_data = np.fft.fft(iq_samples)
    power_spectrum = np.abs(fft_data) ** 2
    n = len(power_spectrum)
    half = n // 2

    # In NumPy's complex FFT layout:
    #   Bins 1..half-1:   positive frequencies (upper sideband)
    #   Bins half+1..N-1: negative frequencies (lower sideband)
    # Skip DC bin (index 0) and Nyquist bin (index half)
    upper_power = float(np.sum(power_spectrum[1:half]))
    lower_power = float(np.sum(power_spectrum[half + 1 :]))

    if lower_power < 1e-20 and upper_power < 1e-20:
        return 1.0, "upper"

    if upper_power >= lower_power:
        ratio = upper_power / max(lower_power, 1e-20)
        return ratio, "upper"
    else:
        ratio = lower_power / max(upper_power, 1e-20)
        return ratio, "lower"


def _classify(
    envelope_cv: float,
    asymmetry_ratio: float,
) -> tuple[str, float]:
    """Apply the classification decision tree.

    Order of checks:
      1. SSB: high spectral asymmetry (energy in one sideband only)
      2. AM: high envelope variation (amplitude-modulated carrier)
      3. FM: default (constant envelope, symmetric spectrum)

    Args:
        envelope_cv: Envelope coefficient of variation.
        asymmetry_ratio: Spectral asymmetry ratio (>= 1.0).

    Returns:
        Tuple of (modulation_type, confidence).
    """
    # Check SSB first: high spectral asymmetry with low envelope variation
    if (
        asymmetry_ratio > _SPECTRAL_ASYMMETRY_THRESHOLD
        and envelope_cv < _ENVELOPE_CV_THRESHOLD
    ):
        # Confidence scales with how asymmetric the spectrum is
        confidence = min(
            1.0, (asymmetry_ratio - _SPECTRAL_ASYMMETRY_THRESHOLD) / 10.0 + 0.5
        )
        return "ssb", confidence

    # Check AM: high envelope variation
    if envelope_cv > _ENVELOPE_CV_THRESHOLD:
        # Confidence scales with how much the envelope varies
        confidence = min(1.0, (envelope_cv - _ENVELOPE_CV_THRESHOLD) / 0.3 + 0.4)
        return "am", confidence

    # Default: FM (constant envelope, symmetric spectrum)
    # Confidence is higher when envelope is very stable
    confidence = min(1.0, (1.0 - envelope_cv / _ENVELOPE_CV_THRESHOLD) * 0.6 + 0.4)
    return "fm", confidence
