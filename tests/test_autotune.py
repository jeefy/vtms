"""Tests for vtms_sdr.autotune — signal classification and settings suggestion."""

import numpy as np
import pytest

from vtms_sdr.autotune import (
    AutoTuneResult,
    classify_signal,
    suggest_gain,
    suggest_squelch,
    _envelope_coefficient_of_variation,
    _spectral_asymmetry,
    _classify,
)

SAMPLE_RATE = 2_400_000
NUM_SAMPLES = 65_536


# ---------------------------------------------------------------------------
# Synthetic signal generators (reuse patterns from test_demod.py)
# ---------------------------------------------------------------------------


def generate_fm_iq(
    tone_freq: float = 1000.0,
    deviation: float = 5000.0,
    sample_rate: int = SAMPLE_RATE,
    num_samples: int = NUM_SAMPLES,
    amplitude: float = 1.0,
) -> np.ndarray:
    """Generate synthetic FM IQ: constant envelope, frequency-modulated."""
    t = np.arange(num_samples) / sample_rate
    modulator = np.sin(2 * np.pi * tone_freq * t)
    phase = 2 * np.pi * deviation * np.cumsum(modulator) / sample_rate
    iq = amplitude * np.exp(1j * phase)
    return iq.astype(np.complex64)


def generate_am_iq(
    tone_freq: float = 1000.0,
    mod_depth: float = 0.8,
    carrier_offset: float = 0.0,
    sample_rate: int = SAMPLE_RATE,
    num_samples: int = NUM_SAMPLES,
    amplitude: float = 1.0,
) -> np.ndarray:
    """Generate synthetic AM IQ: modulated envelope, constant frequency."""
    t = np.arange(num_samples) / sample_rate
    modulator = np.sin(2 * np.pi * tone_freq * t)
    envelope = 1.0 + mod_depth * modulator
    carrier = np.exp(2j * np.pi * carrier_offset * t)
    iq = amplitude * envelope * carrier
    return iq.astype(np.complex64)


def generate_ssb_iq(
    tone_freq: float = 1000.0,
    sideband: str = "usb",
    sample_rate: int = SAMPLE_RATE,
    num_samples: int = NUM_SAMPLES,
    amplitude: float = 1.0,
) -> np.ndarray:
    """Generate synthetic SSB IQ: energy in one sideband only."""
    t = np.arange(num_samples) / sample_rate
    freq = tone_freq if sideband == "usb" else -tone_freq
    iq = amplitude * np.exp(2j * np.pi * freq * t)
    return iq.astype(np.complex64)


def generate_noise_iq(
    sample_rate: int = SAMPLE_RATE,
    num_samples: int = NUM_SAMPLES,
    power: float = 0.001,
) -> np.ndarray:
    """Generate pure Gaussian noise IQ (no signal)."""
    scale = np.sqrt(power / 2)
    noise = scale * (np.random.randn(num_samples) + 1j * np.random.randn(num_samples))
    return noise.astype(np.complex64)


# ---------------------------------------------------------------------------
# AutoTuneResult tests
# ---------------------------------------------------------------------------


class TestAutoTuneResult:
    def test_dataclass_fields(self):
        result = AutoTuneResult(
            modulation="fm",
            gain=25.0,
            squelch_db=-35.0,
            signal_power_db=-20.0,
            confidence=0.8,
        )
        assert result.modulation == "fm"
        assert result.gain == 25.0
        assert result.squelch_db == -35.0
        assert result.signal_power_db == -20.0
        assert result.confidence == 0.8

    def test_summary_string(self):
        result = AutoTuneResult(
            modulation="am",
            gain=30.0,
            squelch_db=-40.0,
            signal_power_db=-25.0,
            confidence=0.7,
        )
        summary = result.summary()
        assert "AM" in summary
        assert "30.0" in summary
        assert "-40.0" in summary
        assert "70%" in summary


# ---------------------------------------------------------------------------
# Envelope coefficient of variation tests
# ---------------------------------------------------------------------------


class TestEnvelopeCV:
    def test_constant_envelope_gives_zero_cv(self):
        """A pure complex exponential has constant |IQ| = 1."""
        iq = generate_fm_iq(amplitude=1.0)
        cv = _envelope_coefficient_of_variation(iq)
        assert cv < 0.05, f"FM signal should have near-zero CV, got {cv:.4f}"

    def test_am_signal_gives_high_cv(self):
        """AM signal with mod_depth=0.8 should have substantial CV."""
        iq = generate_am_iq(mod_depth=0.8)
        cv = _envelope_coefficient_of_variation(iq)
        assert cv > 0.25, f"AM signal should have high CV, got {cv:.4f}"

    def test_low_mod_depth_am_gives_lower_cv(self):
        """AM signal with mod_depth=0.2 has smaller CV than mod_depth=0.8."""
        iq_lo = generate_am_iq(mod_depth=0.2)
        iq_hi = generate_am_iq(mod_depth=0.8)
        cv_lo = _envelope_coefficient_of_variation(iq_lo)
        cv_hi = _envelope_coefficient_of_variation(iq_hi)
        assert cv_lo < cv_hi

    def test_ssb_has_constant_envelope(self):
        """SSB single-tone signal has constant envelope."""
        iq = generate_ssb_iq(tone_freq=1000.0)
        cv = _envelope_coefficient_of_variation(iq)
        assert cv < 0.05, f"SSB tone should have near-zero CV, got {cv:.4f}"

    def test_zero_signal_returns_zero(self):
        """All-zero input should return CV of 0."""
        iq = np.zeros(1024, dtype=np.complex64)
        cv = _envelope_coefficient_of_variation(iq)
        assert cv == 0.0


# ---------------------------------------------------------------------------
# Spectral asymmetry tests
# ---------------------------------------------------------------------------


class TestSpectralAsymmetry:
    def test_usb_signal_is_asymmetric(self):
        """USB signal should have energy predominantly in upper sideband."""
        iq = generate_ssb_iq(tone_freq=1000.0, sideband="usb")
        ratio, dominant = _spectral_asymmetry(iq)
        assert ratio > 3.0, f"USB should be highly asymmetric, got ratio {ratio:.2f}"
        assert dominant == "upper"

    def test_lsb_signal_is_asymmetric(self):
        """LSB signal should have energy predominantly in lower sideband."""
        iq = generate_ssb_iq(tone_freq=1000.0, sideband="lsb")
        ratio, dominant = _spectral_asymmetry(iq)
        assert ratio > 3.0, f"LSB should be highly asymmetric, got ratio {ratio:.2f}"
        assert dominant == "lower"

    def test_fm_signal_is_symmetric(self):
        """FM signal should be roughly symmetric."""
        iq = generate_fm_iq(tone_freq=1000.0)
        ratio, _ = _spectral_asymmetry(iq)
        assert ratio < 3.0, f"FM should be symmetric, got ratio {ratio:.2f}"

    def test_am_signal_is_symmetric(self):
        """AM signal with zero carrier offset should be roughly symmetric."""
        iq = generate_am_iq(tone_freq=1000.0, carrier_offset=0.0)
        ratio, _ = _spectral_asymmetry(iq)
        assert ratio < 3.0, f"AM should be symmetric, got ratio {ratio:.2f}"

    def test_noise_is_symmetric(self):
        """Pure noise should have symmetric spectrum."""
        np.random.seed(42)
        iq = generate_noise_iq(power=0.1)
        ratio, _ = _spectral_asymmetry(iq)
        assert ratio < 2.0, f"Noise should be symmetric, got ratio {ratio:.2f}"


# ---------------------------------------------------------------------------
# Classification decision tree tests
# ---------------------------------------------------------------------------


class TestClassifyDecisionTree:
    def test_low_cv_low_asymmetry_gives_fm(self):
        mod, conf = _classify(envelope_cv=0.05, asymmetry_ratio=1.2)
        assert mod == "fm"
        assert conf > 0.5

    def test_high_cv_gives_am(self):
        mod, conf = _classify(envelope_cv=0.5, asymmetry_ratio=1.2)
        assert mod == "am"
        assert conf > 0.5

    def test_high_asymmetry_low_cv_gives_ssb(self):
        mod, conf = _classify(envelope_cv=0.05, asymmetry_ratio=5.0)
        assert mod == "ssb"
        assert conf > 0.5

    def test_high_asymmetry_high_cv_gives_am_not_ssb(self):
        """High envelope variation overrides asymmetry for SSB check."""
        mod, _ = _classify(envelope_cv=0.5, asymmetry_ratio=5.0)
        # SSB check requires low envelope CV, so this should be AM
        assert mod == "am"

    def test_confidence_bounded(self):
        """Confidence should always be between 0 and 1."""
        for cv in [0.0, 0.1, 0.3, 0.5, 0.8, 1.0]:
            for asym in [1.0, 2.0, 5.0, 20.0]:
                _, conf = _classify(envelope_cv=cv, asymmetry_ratio=asym)
                assert 0.0 <= conf <= 1.0, (
                    f"Confidence out of range for cv={cv}, asym={asym}: {conf}"
                )


# ---------------------------------------------------------------------------
# Full classify_signal integration tests
# ---------------------------------------------------------------------------


class TestClassifySignal:
    def test_fm_signal_classified_as_fm(self):
        iq = generate_fm_iq(tone_freq=1000.0, deviation=5000.0)
        result = classify_signal(iq, SAMPLE_RATE)
        assert result.modulation == "fm"
        assert result.confidence > 0.3

    def test_am_signal_classified_as_am(self):
        iq = generate_am_iq(tone_freq=1000.0, mod_depth=0.8)
        result = classify_signal(iq, SAMPLE_RATE)
        assert result.modulation == "am"
        assert result.confidence > 0.3

    def test_ssb_usb_classified_as_ssb(self):
        iq = generate_ssb_iq(tone_freq=1000.0, sideband="usb")
        result = classify_signal(iq, SAMPLE_RATE)
        assert result.modulation == "ssb"
        assert result.confidence > 0.3

    def test_ssb_lsb_classified_as_ssb(self):
        iq = generate_ssb_iq(tone_freq=1000.0, sideband="lsb")
        result = classify_signal(iq, SAMPLE_RATE)
        assert result.modulation == "ssb"
        assert result.confidence > 0.3

    def test_very_weak_signal_returns_low_confidence(self):
        """Signal below noise floor should return FM defaults with 0 confidence."""
        iq = generate_noise_iq(power=1e-10)
        result = classify_signal(iq, SAMPLE_RATE)
        assert result.confidence == 0.0
        assert result.modulation == "fm"  # default

    def test_result_has_valid_gain(self):
        iq = generate_fm_iq()
        result = classify_signal(iq, SAMPLE_RATE)
        assert 0.0 <= result.gain <= 49.6

    def test_result_has_valid_squelch(self):
        iq = generate_fm_iq()
        result = classify_signal(iq, SAMPLE_RATE)
        assert result.squelch_db <= result.signal_power_db

    def test_strong_signal_gets_low_gain(self):
        """A strong signal (amplitude=10) should be suggested low gain."""
        iq = generate_fm_iq(amplitude=10.0)
        result = classify_signal(iq, SAMPLE_RATE)
        assert result.gain <= 20.0

    def test_different_fm_tones(self):
        """FM at various tone frequencies should still classify as FM."""
        for tone in [500.0, 1000.0, 2000.0, 3000.0]:
            iq = generate_fm_iq(tone_freq=tone)
            result = classify_signal(iq, SAMPLE_RATE)
            assert result.modulation == "fm", (
                f"FM with {tone} Hz tone misclassified as {result.modulation}"
            )

    def test_different_am_depths(self):
        """AM at various modulation depths should classify as AM."""
        for depth in [0.5, 0.6, 0.8, 0.95]:
            iq = generate_am_iq(mod_depth=depth)
            result = classify_signal(iq, SAMPLE_RATE)
            assert result.modulation == "am", (
                f"AM with depth={depth} misclassified as {result.modulation}"
            )


# ---------------------------------------------------------------------------
# Gain suggestion tests
# ---------------------------------------------------------------------------


class TestSuggestGain:
    def test_strong_signal(self):
        assert suggest_gain(-5.0) == 10.0

    def test_moderate_high_signal(self):
        assert suggest_gain(-15.0) == 20.0

    def test_moderate_low_signal(self):
        assert suggest_gain(-30.0) == 30.0

    def test_weak_signal(self):
        assert suggest_gain(-50.0) == 40.0

    def test_very_weak_signal(self):
        assert suggest_gain(-70.0) == 49.6

    def test_gain_at_boundaries(self):
        """Gain at exact boundary values."""
        assert suggest_gain(-10.0) == 20.0  # exactly at boundary → next tier
        assert suggest_gain(-20.0) == 30.0
        assert suggest_gain(-40.0) == 40.0
        assert suggest_gain(-55.0) == 49.6


# ---------------------------------------------------------------------------
# Squelch suggestion tests
# ---------------------------------------------------------------------------


class TestSuggestSquelch:
    def test_squelch_below_signal(self):
        """Squelch should be set below the signal power."""
        squelch = suggest_squelch(-20.0)
        assert squelch == -26.0

    def test_squelch_floor(self):
        """Squelch should not go below -60 dB."""
        squelch = suggest_squelch(-58.0)
        assert squelch == -60.0

    def test_squelch_very_weak(self):
        """Very weak signal: squelch capped at -60 dB."""
        squelch = suggest_squelch(-80.0)
        assert squelch == -60.0

    def test_squelch_strong_signal(self):
        """Strong signal gets squelch 6 dB below."""
        squelch = suggest_squelch(-5.0)
        assert squelch == -11.0
