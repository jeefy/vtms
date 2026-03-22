"""Tests for vtms_sdr.dcs — DCS code decoder."""

import numpy as np
import pytest

from vtms_sdr.dcs import (
    DCS_CODES,
    DCSDecoder,
    dcs_code_to_word,
    dcs_word_to_code,
)
from vtms_sdr.demod import AUDIO_SAMPLE_RATE


def generate_dcs_signal(
    code: int,
    sample_rate: int = AUDIO_SAMPLE_RATE,
    duration: float = 0.5,
    amplitude: float = 0.1,
) -> np.ndarray:
    """Generate a synthetic DCS FSK signal for testing.

    DCS sends a 23-bit codeword at 134.4 baud using continuous-phase FSK.
    The sub-audible signal uses two tones centered at ~134.4 Hz:
    - Bit 1 → 134.4 + 67.2 = 201.6 Hz (mark)
    - Bit 0 → 134.4 - 67.2 = 67.2 Hz  (space)

    This produces a real-valued sub-audible signal below 300 Hz.
    """
    word = dcs_code_to_word(code)
    baud_rate = 134.4
    center_freq = 134.4  # center of FSK tones
    deviation = 67.2  # Hz deviation from center
    samples_per_bit = sample_rate / baud_rate
    n_samples = int(sample_rate * duration)

    # Build bit stream: repeat the 23-bit word to fill duration
    bits = []
    while len(bits) * samples_per_bit < n_samples:
        for i in range(23):
            bits.append((word >> i) & 1)

    # Generate continuous-phase FSK
    signal = np.zeros(n_samples, dtype=np.float32)
    phase = 0.0
    sample_idx = 0
    for bit_idx, bit in enumerate(bits):
        freq = center_freq + deviation if bit == 1 else center_freq - deviation
        bit_end = int((bit_idx + 1) * samples_per_bit)
        bit_end = min(bit_end, n_samples)
        for s in range(sample_idx, bit_end):
            signal[s] = amplitude * np.sin(phase)
            phase += 2 * np.pi * freq / sample_rate
        sample_idx = bit_end
        if sample_idx >= n_samples:
            break

    return signal


class TestDCSCodeTable:
    """Test the DCS code table and word conversion."""

    def test_dcs_codes_is_tuple_of_ints(self):
        assert isinstance(DCS_CODES, tuple)
        assert all(isinstance(c, int) for c in DCS_CODES)

    def test_standard_codes_present(self):
        """Common DCS codes should be in the table."""
        for code in (23, 25, 71, 114, 155, 223, 411, 654):
            assert code in DCS_CODES, f"DCS code {code} missing"

    def test_code_to_word_returns_23_bit_int(self):
        word = dcs_code_to_word(23)
        assert isinstance(word, int)
        assert 0 < word < (1 << 23)

    def test_word_to_code_roundtrips(self):
        for code in (23, 71, 155, 411):
            word = dcs_code_to_word(code)
            recovered = dcs_word_to_code(word)
            assert recovered == code, f"Roundtrip failed for code {code}"

    def test_invalid_code_raises(self):
        with pytest.raises(ValueError, match="[Ii]nvalid DCS"):
            dcs_code_to_word(999)

    def test_word_to_code_unknown_returns_none(self):
        assert dcs_word_to_code(0) is None


class TestDCSDecoder:
    """Test DCSDecoder detection logic."""

    def test_can_create_decoder(self):
        dec = DCSDecoder(target_code=23, sample_rate=AUDIO_SAMPLE_RATE)
        assert dec.target_code == 23

    def test_detects_matching_code(self):
        """Decoder should detect when the target DCS code is present."""
        dec = DCSDecoder(target_code=23, sample_rate=AUDIO_SAMPLE_RATE)
        signal = generate_dcs_signal(23, duration=0.5)
        # Feed several blocks
        block_size = 4800  # 100ms at 48kHz
        matched = False
        for i in range(0, len(signal) - block_size, block_size):
            block = signal[i : i + block_size]
            if dec.process(block):
                matched = True
                break
        assert matched, "Decoder should detect matching DCS code"

    def test_rejects_wrong_code(self):
        """Decoder should NOT match a different DCS code."""
        dec = DCSDecoder(target_code=23, sample_rate=AUDIO_SAMPLE_RATE)
        signal = generate_dcs_signal(71, duration=0.5)
        block_size = 4800
        matched = False
        for i in range(0, len(signal) - block_size, block_size):
            block = signal[i : i + block_size]
            if dec.process(block):
                matched = True
                break
        assert not matched, "Decoder should NOT match wrong DCS code"

    def test_no_false_positive_on_silence(self):
        """Decoder should not match on silence."""
        dec = DCSDecoder(target_code=23, sample_rate=AUDIO_SAMPLE_RATE)
        silence = np.zeros(48000, dtype=np.float32)
        block_size = 4800
        for i in range(0, len(silence), block_size):
            assert not dec.process(silence[i : i + block_size])

    def test_no_false_positive_on_noise(self):
        """Decoder should not match on random noise."""
        rng = np.random.default_rng(42)
        dec = DCSDecoder(target_code=23, sample_rate=AUDIO_SAMPLE_RATE)
        noise = (rng.standard_normal(48000) * 0.1).astype(np.float32)
        block_size = 4800
        for i in range(0, len(noise), block_size):
            assert not dec.process(noise[i : i + block_size])

    def test_is_matched_property(self):
        """is_matched should reflect the latest process() result."""
        dec = DCSDecoder(target_code=23, sample_rate=AUDIO_SAMPLE_RATE)
        assert dec.is_matched is False
        signal = generate_dcs_signal(23, duration=0.5)
        block_size = 4800
        for i in range(0, len(signal) - block_size, block_size):
            dec.process(signal[i : i + block_size])
        # After processing valid signal, should be matched
        assert dec.is_matched is True

    def test_process_returns_bool(self):
        dec = DCSDecoder(target_code=23, sample_rate=AUDIO_SAMPLE_RATE)
        result = dec.process(np.zeros(4800, dtype=np.float32))
        assert isinstance(result, bool)
