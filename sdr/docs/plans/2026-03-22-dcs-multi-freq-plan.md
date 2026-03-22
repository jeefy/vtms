# DCS Squelch & Multi-Frequency Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add DCS (Digital-Coded Squelch) code-matching as a per-frequency squelch gate, and support monitoring up to 2 frequencies simultaneously via wide-IQ or multi-dongle backends.

**Architecture:** New `dcs.py` module decodes DCS from sub-audible audio tapped from FM demod before the 300 Hz high-pass filter. A `ChannelConfig` dataclass replaces the single-frequency `RecordConfig` for multi-channel orchestration. Two backends are supported: wide-IQ (one dongle, nearby frequencies channelized via DDC) and multi-dongle (separate SDR per frequency). Each channel gets its own recorder/file.

**Tech Stack:** Python 3.10+, numpy, scipy (Goertzel/correlation for DCS), Click (CLI), PyYAML (presets), pytest (testing)

---

### Task 1: DCS Decoder Module

**Files:**
- Create: `src/vtms_sdr/dcs.py`
- Test: `tests/test_dcs.py`

**Context:** DCS (Digital-Coded Squelch) uses a continuous 134.4 baud FSK sub-audible data stream below 300 Hz. Each code is a 23-bit word (9-bit code + 3 fixed + 11-bit CRC) sent repeatedly. The decoder receives audio that still contains sub-audible content (tapped before the 300 Hz HP filter in FMDemodulator). It lowpass-filters to isolate the sub-300 Hz band, detects the FSK bit stream, and correlates against the target DCS code word.

**Step 1: Write the failing tests**

Create `tests/test_dcs.py`:

```python
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

    DCS sends a 23-bit codeword at 134.4 baud using FSK:
    - Bit 1 → +67.2 Hz  (half the baud rate above a ~zero center)
    - Bit 0 → -67.2 Hz

    The signal is sub-audible (below ~300 Hz).
    """
    word = dcs_code_to_word(code)
    baud_rate = 134.4
    samples_per_bit = sample_rate / baud_rate
    n_samples = int(sample_rate * duration)

    # Build bit stream: repeat the 23-bit word to fill duration
    bits = []
    while len(bits) * samples_per_bit < n_samples:
        for i in range(23):
            bits.append((word >> i) & 1)

    # Generate FSK: +67.2 Hz for 1, -67.2 Hz for 0
    signal = np.zeros(n_samples, dtype=np.float32)
    phase = 0.0
    sample_idx = 0
    for bit_idx, bit in enumerate(bits):
        freq = 67.2 if bit == 1 else -67.2
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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_dcs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtms_sdr.dcs'`

**Step 3: Write the DCS decoder module**

Create `src/vtms_sdr/dcs.py`:

```python
"""DCS (Digital-Coded Squelch) decoder for sub-audible signaling.

DCS transmits a continuous 134.4 baud FSK data stream below 300 Hz.
Each codeword is 23 bits: 9-bit octal code + 3 fixed bits + 11-bit CRC.

This module:
- Maintains the standard DCS code table (83 codes).
- Converts between octal code numbers and 23-bit codewords.
- Decodes DCS from pre-HP-filtered FM audio in real time.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import firwin, lfilter

__all__ = [
    "DCS_CODES",
    "DCSDecoder",
    "dcs_code_to_word",
    "dcs_word_to_code",
]

# Standard 83 DCS codes (octal representation as decimal integers).
DCS_CODES: tuple[int, ...] = (
    23, 25, 26, 31, 32, 36, 43, 47, 51, 53, 54, 65, 71, 72, 73, 74,
    114, 115, 116, 122, 125, 131, 132, 134, 143, 145, 152, 155, 156,
    162, 165, 172, 174, 205, 212, 223, 225, 226, 243, 244, 245, 246,
    251, 252, 255, 261, 263, 265, 266, 271, 274, 306, 311, 315, 325,
    331, 332, 343, 346, 351, 356, 364, 365, 371, 411, 412, 413, 423,
    431, 432, 445, 446, 452, 454, 455, 462, 464, 465, 466, 503, 506,
    516, 523, 526, 532, 546, 565, 606, 612, 624, 627, 631, 632, 654,
    662, 664, 703, 712, 723, 731, 732, 734, 743, 754,
)

# DCS generator polynomial for CRC: x^11 + x^9 + x^8 + x^6 + x^5 + x^4 + 1
# = 0b101101110001 = 0x5B1 (note: bit ordering is LSB-first in DCS)
_DCS_POLY = 0x5B1  # generator polynomial (12 bits, degree 11)

# Precomputed lookup: code -> 23-bit word
_CODE_TO_WORD: dict[int, int] = {}
# Precomputed lookup: 23-bit word -> code
_WORD_TO_CODE: dict[int, int] = {}


def _compute_crc(code_9bit: int) -> int:
    """Compute the 11-bit DCS CRC for a 9-bit code.

    The DCS codeword is 23 bits: [8:0] = code, [11:9] = fixed 100,
    [22:12] = CRC.  CRC is computed over the 12-bit value (code + fixed).
    """
    # The 12-bit data is: 9-bit code (LSB) + 3 fixed bits (100 = 0b100)
    data = code_9bit | (0b100 << 9)  # 12 bits

    # CRC computation: divide data by polynomial in GF(2)
    # Shift data up by 11 bits (CRC length)
    remainder = data << 11  # 23 bits max

    for i in range(22, 10, -1):  # bits 22 down to 11
        if remainder & (1 << i):
            remainder ^= _DCS_POLY << (i - 11)

    return remainder & 0x7FF  # 11-bit CRC


def _init_lookup_tables() -> None:
    """Build code <-> word lookup tables for all standard DCS codes."""
    for code in DCS_CODES:
        # Convert octal-as-decimal to actual 9-bit value
        # e.g. code=023 means octal 023 = 0o23 = 19 decimal
        # But codes are stored as decimal representations of octal:
        # code 23 means the digits "023" in octal = 2*8 + 3 = 19
        octal_str = f"{code:03d}"
        code_9bit = int(octal_str, 8)

        # 3 fixed bits are 100 (binary)
        fixed = 0b100

        # Compute CRC
        crc = _compute_crc(code_9bit)

        # Assemble 23-bit word: [8:0]=code, [11:9]=fixed, [22:12]=CRC
        word = code_9bit | (fixed << 9) | (crc << 12)

        _CODE_TO_WORD[code] = word
        _WORD_TO_CODE[word] = code


_init_lookup_tables()


def dcs_code_to_word(code: int) -> int:
    """Convert a DCS code number to its 23-bit codeword.

    Args:
        code: DCS code as displayed (e.g. 23, 71, 155).

    Returns:
        23-bit integer codeword.

    Raises:
        ValueError: If code is not a valid standard DCS code.
    """
    if code not in _CODE_TO_WORD:
        raise ValueError(
            f"Invalid DCS code {code}. "
            f"Must be one of the {len(DCS_CODES)} standard codes."
        )
    return _CODE_TO_WORD[code]


def dcs_word_to_code(word: int) -> int | None:
    """Convert a 23-bit DCS codeword back to its code number.

    Args:
        word: 23-bit codeword.

    Returns:
        DCS code number, or None if the word doesn't match any standard code.
    """
    return _WORD_TO_CODE.get(word)


class DCSDecoder:
    """Real-time DCS decoder that processes audio blocks.

    Expects audio at 48 kHz that still contains sub-audible content
    (i.e., tapped BEFORE the 300 Hz high-pass filter).

    Usage:
        decoder = DCSDecoder(target_code=23)
        for audio_block in stream:
            if decoder.process(audio_block):
                print("DCS match!")
    """

    _BAUD_RATE = 134.4
    _LP_CUTOFF = 300.0  # Hz — isolate sub-audible band

    def __init__(self, target_code: int, sample_rate: int = 48_000) -> None:
        self.target_code = target_code
        self.sample_rate = sample_rate
        self._target_word = dcs_code_to_word(target_code)
        self._is_matched = False

        # Low-pass filter to isolate sub-300 Hz DCS band
        nyquist = sample_rate / 2.0
        cutoff = min(self._LP_CUTOFF / nyquist, 0.99)
        self._lp_filter = firwin(101, cutoff)
        self._lp_zi = np.zeros(100)

        # Bit recovery state
        self._samples_per_bit = sample_rate / self._BAUD_RATE
        self._prev_sample = 0.0
        self._bit_phase = 0.0
        self._bit_buffer: list[int] = []

        # Match tracking
        self._consecutive_matches = 0
        self._match_threshold = 2  # need 2 consecutive word matches

    @property
    def is_matched(self) -> bool:
        """Whether the target DCS code is currently detected."""
        return self._is_matched

    def process(self, audio: np.ndarray) -> bool:
        """Process an audio block and check for DCS code match.

        Args:
            audio: Float32 audio samples (pre-HP, contains sub-audible).

        Returns:
            True if the target DCS code is detected in this block.
        """
        if len(audio) == 0:
            return False

        # Low-pass filter to isolate DCS band
        filtered, self._lp_zi = lfilter(
            self._lp_filter, 1.0, audio.astype(np.float64), zi=self._lp_zi
        )

        # FSK demodulation: detect zero crossings to recover bits.
        # In DCS FSK, bit 1 = positive frequency (+67.2 Hz),
        #               bit 0 = negative frequency (-67.2 Hz).
        # We use the sign of the derivative (instantaneous frequency).
        matched_this_block = False

        for sample in filtered:
            # Simple zero-crossing frequency discriminator
            diff = sample - self._prev_sample
            self._prev_sample = sample

            self._bit_phase += 1.0
            if self._bit_phase >= self._samples_per_bit:
                self._bit_phase -= self._samples_per_bit

                # Determine bit value from accumulated frequency direction
                bit = 1 if diff > 0 else 0
                self._bit_buffer.append(bit)

                # Keep buffer at 23 bits
                if len(self._bit_buffer) > 23:
                    self._bit_buffer.pop(0)

                # Check for word match when we have 23 bits
                if len(self._bit_buffer) == 23:
                    word = 0
                    for i, b in enumerate(self._bit_buffer):
                        word |= b << i

                    if word == self._target_word:
                        self._consecutive_matches += 1
                        if self._consecutive_matches >= self._match_threshold:
                            self._is_matched = True
                            matched_this_block = True
                    else:
                        # Also check inverted (DCS uses inverted codes too)
                        inv_word = word ^ 0x7FFFFF  # invert all 23 bits
                        if inv_word == self._target_word:
                            self._consecutive_matches += 1
                            if self._consecutive_matches >= self._match_threshold:
                                self._is_matched = True
                                matched_this_block = True
                        else:
                            self._consecutive_matches = max(
                                0, self._consecutive_matches - 1
                            )

        if not matched_this_block and self._consecutive_matches == 0:
            self._is_matched = False

        return matched_this_block
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_dcs.py -v`
Expected: PASS — all DCS tests green

**Step 5: Run full test suite for regressions**

Run: `uv run pytest --tb=short -q`
Expected: All existing tests still pass + new DCS tests pass

**Step 6: Commit**

```bash
git add src/vtms_sdr/dcs.py tests/test_dcs.py
git commit -m "feat: add DCS decoder module with code table and real-time detection"
```

---

### Task 2: FM Demodulator Pre-HP Audio Tap

**Files:**
- Modify: `src/vtms_sdr/demod.py:109-259`
- Test: `tests/test_demod.py`

**Context:** The current FMDemodulator applies a 300 Hz high-pass filter (Stage 6) that removes sub-audible tones including DCS. We need to expose the audio after de-emphasis but BEFORE the HP filter so a DCS decoder can access it. The tap must not alter the existing audio output.

**Step 1: Write failing tests**

Add to `tests/test_demod.py`:

```python
class TestFMDemodulatorPreHPTap:
    """Test the pre-high-pass audio tap for DCS/CTCSS decoding."""

    def test_pre_hp_audio_attribute_exists(self):
        """FMDemodulator should have a pre_hp_audio attribute after demodulate."""
        demod = FMDemodulator(SAMPLE_RATE)
        iq = generate_fm_signal(tone_freq=1000.0)
        demod.demodulate(iq)
        assert hasattr(demod, "pre_hp_audio")

    def test_pre_hp_audio_is_numpy_array(self):
        demod = FMDemodulator(SAMPLE_RATE)
        iq = generate_fm_signal(tone_freq=1000.0)
        demod.demodulate(iq)
        assert isinstance(demod.pre_hp_audio, np.ndarray)

    def test_pre_hp_audio_has_same_length_as_output(self):
        demod = FMDemodulator(SAMPLE_RATE)
        iq = generate_fm_signal(tone_freq=1000.0)
        audio = demod.demodulate(iq)
        assert len(demod.pre_hp_audio) == len(audio)

    def test_pre_hp_audio_contains_low_frequencies(self):
        """Pre-HP audio should contain sub-300 Hz content."""
        demod = FMDemodulator(SAMPLE_RATE)
        # Generate FM signal with a 150 Hz tone (below HP cutoff)
        iq = generate_fm_signal(tone_freq=150.0, deviation=5000.0)
        audio = demod.demodulate(iq)

        # The pre-HP audio should have more low-frequency energy
        pre_hp_spectrum = np.abs(np.fft.rfft(demod.pre_hp_audio))
        post_hp_spectrum = np.abs(np.fft.rfft(audio))

        # Below 300 Hz bins
        freq_bins = np.fft.rfftfreq(len(audio), d=1.0 / AUDIO_SAMPLE_RATE)
        low_mask = freq_bins < 300
        pre_hp_low_energy = np.sum(pre_hp_spectrum[low_mask] ** 2)
        post_hp_low_energy = np.sum(post_hp_spectrum[low_mask] ** 2)

        assert pre_hp_low_energy > post_hp_low_energy * 2, (
            "Pre-HP audio should have significantly more sub-300 Hz energy"
        )

    def test_output_audio_unchanged(self):
        """Adding the tap should not change the demodulate() output."""
        demod = FMDemodulator(SAMPLE_RATE)
        iq = generate_fm_signal(tone_freq=1000.0, deviation=5000.0)
        audio = demod.demodulate(iq)

        # Output should still be float32, in [-1, 1], with 1kHz dominant
        assert audio.dtype == np.float32
        assert np.max(np.abs(audio)) <= 1.0
        dominant = get_dominant_frequency(audio)
        assert abs(dominant - 1000.0) < 150.0

    def test_pre_hp_audio_none_before_first_call(self):
        """pre_hp_audio should be None before first demodulate() call."""
        demod = FMDemodulator(SAMPLE_RATE)
        assert demod.pre_hp_audio is None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_demod.py::TestFMDemodulatorPreHPTap -v`
Expected: FAIL — `AttributeError: 'FMDemodulator' object has no attribute 'pre_hp_audio'`

**Step 3: Add the pre-HP tap to FMDemodulator**

In `src/vtms_sdr/demod.py`, modify `FMDemodulator`:

1. Add `self.pre_hp_audio = None` at the end of `_setup_filters()` (after line 203).

2. In `demodulate()`, after Stage 5 (de-emphasis, line 245) and before Stage 6 (HP filter, line 247), store a copy:

```python
        # --- Tap: save pre-HP audio for DCS/CTCSS decoders ---
        self.pre_hp_audio = audio.copy().astype(np.float32)
```

The existing Stage 6, 7, 8 code remains unchanged.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_demod.py -v`
Expected: PASS — all demod tests including new pre-HP tap tests

**Step 5: Commit**

```bash
git add src/vtms_sdr/demod.py tests/test_demod.py
git commit -m "feat: add pre-HP audio tap to FMDemodulator for DCS/CTCSS decoding"
```

---

### Task 3: Integrate DCS into Recorder Squelch

**Files:**
- Modify: `src/vtms_sdr/recorder.py:32-117`
- Modify: `src/vtms_sdr/session.py:30-94`
- Test: `tests/test_recorder.py`
- Test: `tests/test_session.py`

**Context:** Currently squelch is power-only (`_is_above_squelch` in recorder.py:106-116). When a DCS code is specified, the squelch should only open when BOTH the power threshold is met AND the DCS decoder reports a match. The audio generator in session.py must also pass the pre-HP audio from the demodulator to make it available.

**Step 1: Write failing tests for recorder DCS integration**

Add to `tests/test_recorder.py`:

```python
class TestAudioRecorderDCSSquelch:
    """Test DCS code integration with squelch gating."""

    def test_accepts_dcs_decoder_param(self, tmp_path):
        """AudioRecorder should accept a dcs_decoder parameter."""
        from unittest.mock import MagicMock
        decoder = MagicMock()
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(
            output, audio_format="wav", squelch_db=-20, dcs_decoder=decoder
        )
        assert recorder._dcs_decoder is decoder

    def test_dcs_decoder_none_by_default(self, tmp_path):
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, audio_format="wav")
        assert recorder._dcs_decoder is None

    def test_dcs_match_required_when_decoder_set(self, tmp_path):
        """When DCS decoder is set, squelch should require DCS match too."""
        from unittest.mock import MagicMock
        decoder = MagicMock()
        decoder.process.return_value = False  # DCS never matches
        decoder.is_matched = False

        output = tmp_path / "test.wav"
        recorder = AudioRecorder(
            output, audio_format="wav", squelch_db=-100, dcs_decoder=decoder
        )

        def gen_with_pre_hp():
            for iq_power, audio in make_audio_generator(num_blocks=3):
                # pre_hp_audio is the 3rd element of the tuple
                yield (iq_power, audio, audio)  # pre_hp = same as audio for test

        stats = recorder.record(gen_with_pre_hp())
        # Nothing should be recorded because DCS never matched
        assert stats["samples_written"] == 0

    def test_records_when_dcs_matches(self, tmp_path):
        """When DCS decoder matches, audio should be recorded."""
        from unittest.mock import MagicMock
        decoder = MagicMock()
        decoder.process.return_value = True
        decoder.is_matched = True

        output = tmp_path / "test.wav"
        recorder = AudioRecorder(
            output, audio_format="wav", squelch_db=-100, dcs_decoder=decoder
        )

        def gen_with_pre_hp():
            for iq_power, audio in make_audio_generator(num_blocks=3):
                yield (iq_power, audio, audio)

        stats = recorder.record(gen_with_pre_hp())
        assert stats["samples_written"] > 0

    def test_no_dcs_decoder_accepts_2tuple(self, tmp_path):
        """Without DCS, recorder should still accept (power, audio) tuples."""
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, audio_format="wav", squelch_db=-100)
        stats = recorder.record(make_audio_generator(num_blocks=3))
        assert stats["samples_written"] > 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_recorder.py::TestAudioRecorderDCSSquelch -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'dcs_decoder'`

**Step 3: Implement DCS integration in recorder**

In `src/vtms_sdr/recorder.py`:

1. Add `dcs_decoder` parameter to `__init__` (after `audio_monitor`):
```python
    def __init__(
        self,
        ...
        audio_monitor: AudioMonitor | None = None,
        dcs_decoder=None,
        squelch_callback: ...
    ):
        ...
        self._dcs_decoder = dcs_decoder
```

2. Modify `_record_wav` to handle both 2-tuple and 3-tuple audio generators:
```python
    for item in audio_generator:
        if self._stopped.is_set():
            break

        # Unpack: support both (power, audio) and (power, audio, pre_hp_audio)
        if len(item) == 3:
            iq_power, audio_block, pre_hp_audio = item
        else:
            iq_power, audio_block = item
            pre_hp_audio = None

        ...

        is_above = self._is_above_squelch(iq_power)

        # If DCS decoder is active, require DCS match too
        if self._dcs_decoder is not None and pre_hp_audio is not None:
            self._dcs_decoder.process(pre_hp_audio)
            if not self._dcs_decoder.is_matched:
                is_above = False

        ...
```

**Step 4: Update session.py audio_stream to include pre_hp_audio**

In `src/vtms_sdr/session.py`, modify the `audio_stream` generator inside `run()`:

```python
    def audio_stream():
        for iq_block in sdr.stream():
            iq_pwr = iq_power_db(iq_block)
            audio = demod_holder[0].demodulate(iq_block)
            # Include pre-HP audio if the demodulator provides it
            pre_hp = getattr(demod_holder[0], 'pre_hp_audio', None)
            if pre_hp is not None:
                yield (iq_pwr, audio, pre_hp)
            else:
                yield (iq_pwr, audio)
```

Add `dcs_decoder` to `RecordConfig`:
```python
@dataclass
class RecordConfig:
    ...
    dcs_code: int | None = None
```

Wire up DCS decoder creation in `_run_headless` and `_run_with_monitor` when `cfg.dcs_code` is set.

**Step 5: Run tests**

Run: `uv run pytest tests/test_recorder.py tests/test_session.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/vtms_sdr/recorder.py src/vtms_sdr/session.py tests/test_recorder.py tests/test_session.py
git commit -m "feat: integrate DCS decoder into recorder squelch gating"
```

---

### Task 4: Preset Schema — Add dcs_code Support

**Files:**
- Modify: `src/vtms_sdr/presets.py:62-104`
- Test: `tests/test_presets.py`

**Context:** Presets currently support freq, mod, gain, squelch, label, ppm. Add optional `dcs_code` field validation. The value must be a valid DCS code integer from the standard table.

**Step 1: Write failing tests**

Add to `tests/test_presets.py`:

```python
class TestPresetDCSCode:
    """Test dcs_code field in presets."""

    def test_valid_dcs_code_accepted(self, tmp_path):
        from vtms_sdr.presets import load_presets

        data = {"presets": {"ok": {"freq": "462.5625M", "dcs_code": 23}}}
        p = tmp_path / "presets.yaml"
        p.write_text(yaml.dump(data))
        result = load_presets(p)
        assert result["ok"]["dcs_code"] == 23

    def test_invalid_dcs_code_raises(self, tmp_path):
        from vtms_sdr.presets import load_presets

        data = {"presets": {"bad": {"freq": "462.5625M", "dcs_code": 999}}}
        p = tmp_path / "presets.yaml"
        p.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="dcs_code"):
            load_presets(p)

    def test_dcs_code_must_be_int(self, tmp_path):
        from vtms_sdr.presets import load_presets

        data = {"presets": {"bad": {"freq": "462.5625M", "dcs_code": "abc"}}}
        p = tmp_path / "presets.yaml"
        p.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="dcs_code"):
            load_presets(p)

    def test_preset_without_dcs_code_still_works(self, tmp_path):
        from vtms_sdr.presets import load_presets

        data = {"presets": {"ok": {"freq": "146.52M"}}}
        p = tmp_path / "presets.yaml"
        p.write_text(yaml.dump(data))
        result = load_presets(p)
        assert "dcs_code" not in result["ok"]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_presets.py::TestPresetDCSCode -v`
Expected: FAIL — invalid DCS code 999 does not raise

**Step 3: Add dcs_code validation to _validate_preset**

In `src/vtms_sdr/presets.py`, add to `_validate_preset()` after the label validation:

```python
    dcs_code = settings.get("dcs_code")
    if dcs_code is not None:
        if not isinstance(dcs_code, int):
            raise ValueError(
                f"Preset '{name}': dcs_code must be an integer, "
                f"got {type(dcs_code).__name__}"
            )
        from .dcs import DCS_CODES
        if dcs_code not in DCS_CODES:
            raise ValueError(
                f"Preset '{name}': dcs_code {dcs_code} is not a valid standard DCS code"
            )
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_presets.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/vtms_sdr/presets.py tests/test_presets.py
git commit -m "feat: add dcs_code validation to preset schema"
```

---

### Task 5: CLI — Add --dcs Flag to Record Command

**Files:**
- Modify: `src/vtms_sdr/cli.py:69-414`
- Test: `tests/test_cli.py`

**Context:** Add a `--dcs` option to the `record` command that accepts a DCS code integer. It should be validated against the standard DCS code table. When provided, it gets passed through to `RecordConfig.dcs_code`.

**Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
class TestRecordDCSOption:
    """Test --dcs CLI option for record command."""

    def test_dcs_option_exists(self):
        """record command should accept --dcs option."""
        from click.testing import CliRunner
        from vtms_sdr.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["record", "--help"])
        assert "--dcs" in result.output

    def test_dcs_invalid_code_rejected(self):
        """Invalid DCS code should produce an error."""
        from click.testing import CliRunner
        from vtms_sdr.cli import main

        runner = CliRunner()
        result = runner.invoke(
            main, ["record", "-f", "462.5625M", "--dcs", "999"]
        )
        assert result.exit_code != 0

    def test_dcs_from_preset(self, tmp_path):
        """DCS code from preset should be used when --dcs not given on CLI."""
        import yaml
        preset_data = {
            "presets": {
                "test": {"freq": "462.5625M", "mod": "fm", "dcs_code": 23}
            }
        }
        preset_file = tmp_path / "presets.yaml"
        preset_file.write_text(yaml.dump(preset_data))

        from click.testing import CliRunner
        from vtms_sdr.cli import main

        runner = CliRunner()
        # This will fail trying to open SDR but we just check it gets past parsing
        result = runner.invoke(
            main,
            ["record", "--preset", "test", "--preset-file", str(preset_file)],
        )
        # Should fail at SDR, not at CLI parsing
        assert "dcs_code" not in (result.output or "").lower() or result.exit_code != 0
```

**Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestRecordDCSOption -v`
Expected: FAIL — `--dcs` not in help output

**Step 3: Add --dcs option to record command**

In `src/vtms_sdr/cli.py`:

1. Add the Click option before the `record` function:
```python
@click.option(
    "--dcs",
    "dcs_code",
    type=int,
    default=None,
    help="DCS code for squelch gating (e.g. 23, 71, 155). Only opens squelch when this code matches.",
)
```

2. Add `dcs_code` to the function signature.

3. In the preset resolution block, add:
```python
    if dcs_code is None and preset_name:
        dcs_code = preset.get("dcs_code")
```

4. Validate the DCS code if provided:
```python
    if dcs_code is not None:
        from .dcs import DCS_CODES
        if dcs_code not in DCS_CODES:
            click.echo(f"Error: Invalid DCS code {dcs_code}.", err=True)
            sys.exit(1)
```

5. Pass `dcs_code` to `RecordConfig`.

6. Print DCS code in configuration output:
```python
    if dcs_code:
        click.echo(f"DCS Code:   {dcs_code}", err=True)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/vtms_sdr/cli.py tests/test_cli.py
git commit -m "feat: add --dcs CLI option for DCS code squelch gating"
```

---

### Task 6: Multi-Channel Orchestration

**Files:**
- Modify: `src/vtms_sdr/session.py`
- Create: `src/vtms_sdr/channel.py`
- Test: `tests/test_channel.py`
- Test: `tests/test_session.py`

**Context:** Currently `RecordingSession` handles one frequency. For multi-frequency support, we need a `ChannelConfig` dataclass representing per-channel settings and a `MultiChannelSession` that manages parallel recording pipelines. Each channel gets its own demodulator, optional DCS decoder, and output file.

**Step 1: Write failing tests for ChannelConfig**

Create `tests/test_channel.py`:

```python
"""Tests for vtms_sdr.channel — per-channel configuration."""

from pathlib import Path
import pytest

from vtms_sdr.channel import ChannelConfig


class TestChannelConfig:
    def test_create_minimal(self):
        ch = ChannelConfig(freq=462_562_500, mod="fm", output_path=Path("ch1.wav"))
        assert ch.freq == 462_562_500
        assert ch.mod == "fm"
        assert ch.dcs_code is None

    def test_with_dcs(self):
        ch = ChannelConfig(
            freq=462_562_500, mod="fm", output_path=Path("ch1.wav"), dcs_code=23
        )
        assert ch.dcs_code == 23

    def test_label(self):
        ch = ChannelConfig(
            freq=462_562_500,
            mod="fm",
            output_path=Path("ch1.wav"),
            label="SPOTTER",
        )
        assert ch.label == "SPOTTER"
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_channel.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Create channel.py**

Create `src/vtms_sdr/channel.py`:

```python
"""Per-channel configuration for multi-frequency recording."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["ChannelConfig"]


@dataclass
class ChannelConfig:
    """Configuration for a single recording channel.

    Each channel has its own frequency, modulation, output file,
    and optional DCS code.
    """

    freq: int
    mod: str
    output_path: Path
    audio_format: str = "wav"
    squelch_db: float = -30.0
    dcs_code: int | None = None
    label: str | None = None
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_channel.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/vtms_sdr/channel.py tests/test_channel.py
git commit -m "feat: add ChannelConfig dataclass for multi-frequency recording"
```

---

### Task 7: Wide-IQ Backend for Nearby Frequencies

**Files:**
- Modify: `src/vtms_sdr/sdr.py`
- Create: `src/vtms_sdr/channelizer.py`
- Test: `tests/test_channelizer.py`

**Context:** When two frequencies are within the RTL-SDR bandwidth (~2 MHz), a single dongle can capture both using a wide IQ capture centered between them. A channelizer (DDC — Digital Downconversion) extracts each channel's baseband IQ from the wide capture. This avoids needing a second dongle.

**Step 1: Write failing tests**

Create `tests/test_channelizer.py`:

```python
"""Tests for vtms_sdr.channelizer — DDC channel extraction."""

import numpy as np
import pytest

from vtms_sdr.channelizer import Channelizer


class TestChannelizer:
    def test_create_channelizer(self):
        ch = Channelizer(
            center_freq=462_600_000,
            sample_rate=2_400_000,
            channel_freqs=[462_562_500, 462_612_500],
        )
        assert ch.num_channels == 2

    def test_extract_returns_list_of_iq(self):
        ch = Channelizer(
            center_freq=462_600_000,
            sample_rate=2_400_000,
            channel_freqs=[462_562_500, 462_612_500],
        )
        iq = np.zeros(262144, dtype=np.complex64)
        channels = ch.extract(iq)
        assert len(channels) == 2
        for ch_iq in channels:
            assert ch_iq.dtype == np.complex64
            assert len(ch_iq) > 0

    def test_channel_isolation(self):
        """A tone at channel 1's offset should appear in channel 1, not channel 2."""
        center = 462_600_000
        f1 = 462_562_500  # -37.5 kHz offset
        f2 = 462_637_500  # +37.5 kHz offset
        sr = 2_400_000

        ch = Channelizer(
            center_freq=center, sample_rate=sr, channel_freqs=[f1, f2]
        )

        # Generate tone at f1's offset
        n = 262144
        t = np.arange(n) / sr
        offset = f1 - center  # negative
        iq = np.exp(2j * np.pi * offset * t).astype(np.complex64)

        channels = ch.extract(iq)
        # Channel 0 (f1) should have much more energy than channel 1 (f2)
        power_0 = np.mean(np.abs(channels[0]) ** 2)
        power_1 = np.mean(np.abs(channels[1]) ** 2)
        assert power_0 > power_1 * 10, (
            f"Channel isolation failed: ch0={power_0:.4f}, ch1={power_1:.4f}"
        )

    def test_rejects_out_of_bandwidth_freq(self):
        """Frequencies outside capture bandwidth should raise ValueError."""
        with pytest.raises(ValueError, match="[Bb]andwidth|[Oo]utside"):
            Channelizer(
                center_freq=462_600_000,
                sample_rate=2_400_000,
                channel_freqs=[462_562_500, 470_000_000],  # 7.4 MHz away
            )

    def test_single_channel(self):
        """Channelizer should work with a single channel (degenerate case)."""
        ch = Channelizer(
            center_freq=462_562_500,
            sample_rate=2_400_000,
            channel_freqs=[462_562_500],
        )
        iq = np.zeros(262144, dtype=np.complex64)
        channels = ch.extract(iq)
        assert len(channels) == 1
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_channelizer.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Create channelizer.py**

Create `src/vtms_sdr/channelizer.py`:

```python
"""DDC channelizer for extracting multiple narrowband channels from wide-IQ.

When two frequencies are within the RTL-SDR bandwidth (~2 MHz), a single
dongle captures both. This module extracts each channel's baseband IQ
via frequency shifting and decimation.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import firwin, lfilter

__all__ = ["Channelizer"]

# NBFM channel needs ~25 kHz bandwidth; we use a wider filter for safety
_CHANNEL_BW = 25_000  # Hz, one-sided


class Channelizer:
    """Extracts narrowband channels from a wide-IQ capture.

    Each channel is shifted to baseband, filtered, and decimated
    to produce IQ at a lower sample rate suitable for demodulation.
    """

    def __init__(
        self,
        center_freq: int,
        sample_rate: int,
        channel_freqs: list[int],
        channel_bw: int = _CHANNEL_BW,
    ) -> None:
        """Initialize channelizer.

        Args:
            center_freq: Center frequency of the wide-IQ capture (Hz).
            sample_rate: Sample rate of the wide-IQ capture (sps).
            channel_freqs: List of target channel frequencies (Hz).
            channel_bw: One-sided channel bandwidth (Hz).

        Raises:
            ValueError: If any channel is outside the capture bandwidth.
        """
        self.center_freq = center_freq
        self.sample_rate = sample_rate
        self.channel_freqs = list(channel_freqs)
        self.channel_bw = channel_bw

        max_offset = sample_rate / 2 - channel_bw
        for freq in self.channel_freqs:
            offset = abs(freq - center_freq)
            if offset > max_offset:
                raise ValueError(
                    f"Channel {freq} Hz is outside capture bandwidth. "
                    f"Max offset from center: {max_offset:.0f} Hz, "
                    f"actual: {offset:.0f} Hz"
                )

        # Design channel filter (lowpass at channel_bw)
        nyquist = sample_rate / 2
        cutoff = min(channel_bw / nyquist, 0.99)
        self._channel_filter = firwin(101, cutoff)

        # Per-channel state
        self._filter_states = [np.zeros(100) for _ in self.channel_freqs]

    @property
    def num_channels(self) -> int:
        return len(self.channel_freqs)

    def extract(self, iq_samples: np.ndarray) -> list[np.ndarray]:
        """Extract all channels from a block of wide-IQ samples.

        Args:
            iq_samples: Complex64 wideband IQ samples.

        Returns:
            List of complex64 arrays, one per channel, at the original
            sample rate (no decimation — demodulator handles that).
        """
        n = len(iq_samples)
        t = np.arange(n) / self.sample_rate
        results = []

        for i, freq in enumerate(self.channel_freqs):
            # Frequency shift: move channel to baseband
            offset = freq - self.center_freq
            mixer = np.exp(-2j * np.pi * offset * t).astype(np.complex64)
            shifted = iq_samples * mixer

            # Apply channel filter (lowpass) — I and Q separately
            real_filt, zi_r = lfilter(
                self._channel_filter, 1.0, np.real(shifted),
                zi=self._filter_states[i][:50] if len(self._filter_states[i]) >= 100 else np.zeros(100)
            )
            imag_filt, zi_i = lfilter(
                self._channel_filter, 1.0, np.imag(shifted),
                zi=self._filter_states[i][50:] if len(self._filter_states[i]) >= 100 else np.zeros(100)
            )

            # Update filter state for cross-block continuity
            self._filter_states[i] = np.concatenate([zi_r, zi_i])

            channel_iq = (real_filt + 1j * imag_filt).astype(np.complex64)
            results.append(channel_iq)

        return results
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_channelizer.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: All tests pass

**Step 6: Commit**

```bash
git add src/vtms_sdr/channelizer.py tests/test_channelizer.py
git commit -m "feat: add DDC channelizer for wide-IQ multi-channel extraction"
```

---

## Summary

| Task | Component | New Files | Modified Files |
|------|-----------|-----------|----------------|
| 1 | DCS decoder | `dcs.py`, `test_dcs.py` | — |
| 2 | FM demod tap | — | `demod.py`, `test_demod.py` |
| 3 | Recorder DCS | — | `recorder.py`, `session.py`, tests |
| 4 | Preset dcs_code | — | `presets.py`, `test_presets.py` |
| 5 | CLI --dcs | — | `cli.py`, `test_cli.py` |
| 6 | ChannelConfig | `channel.py`, `test_channel.py` | — |
| 7 | Channelizer | `channelizer.py`, `test_channelizer.py` | — |

Tasks 1-5 deliver DCS squelch support end-to-end. Tasks 6-7 lay the foundation for multi-frequency monitoring. A follow-up plan would wire the channelizer and ChannelConfig into a `MultiChannelSession` and add multi-`--freq` CLI support.
