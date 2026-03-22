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
    23,
    25,
    26,
    31,
    32,
    36,
    43,
    47,
    51,
    53,
    54,
    65,
    71,
    72,
    73,
    74,
    114,
    115,
    116,
    122,
    125,
    131,
    132,
    134,
    143,
    145,
    152,
    155,
    156,
    162,
    165,
    172,
    174,
    205,
    212,
    223,
    225,
    226,
    243,
    244,
    245,
    246,
    251,
    252,
    255,
    261,
    263,
    265,
    266,
    271,
    274,
    306,
    311,
    315,
    325,
    331,
    332,
    343,
    346,
    351,
    356,
    364,
    365,
    371,
    411,
    412,
    413,
    423,
    431,
    432,
    445,
    446,
    452,
    454,
    455,
    462,
    464,
    465,
    466,
    503,
    506,
    516,
    523,
    526,
    532,
    546,
    565,
    606,
    612,
    624,
    627,
    631,
    632,
    654,
    662,
    664,
    703,
    712,
    723,
    731,
    732,
    734,
    743,
    754,
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

    Uses Goertzel tone detection per bit period to decide mark vs space,
    which works reliably on streaming block-based audio (no Hilbert edge
    artifacts).

    Usage:
        decoder = DCSDecoder(target_code=23)
        for audio_block in stream:
            if decoder.process(audio_block):
                print("DCS match!")
    """

    _BAUD_RATE = 134.4
    _LP_CUTOFF = 300.0  # Hz — isolate sub-audible band
    _MARK_FREQ = 134.4 + 67.2  # 201.6 Hz — bit 1
    _SPACE_FREQ = 134.4 - 67.2  # 67.2 Hz — bit 0

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
        self._spb = int(round(self._samples_per_bit))

        # Precompute Goertzel coefficients for mark and space frequencies.
        # Goertzel computes the energy at a single frequency over N samples.
        self._goertzel_mark_coeff = 2.0 * np.cos(
            2.0 * np.pi * self._MARK_FREQ / sample_rate
        )
        self._goertzel_space_coeff = 2.0 * np.cos(
            2.0 * np.pi * self._SPACE_FREQ / sample_rate
        )

        # Residual filtered samples carried between blocks (< 1 bit period)
        self._residual = np.array([], dtype=np.float64)

        # Sliding bit buffer — we push decoded bits here and scan for words
        self._bit_buffer: list[int] = []
        # Keep enough bits for 2 full words + margin for alignment
        self._max_bits = 23 * 3

        # Match tracking
        self._consecutive_matches = 0
        self._match_threshold = 2  # need >=2 word matches to declare detected

    @staticmethod
    def _goertzel_mag(samples: np.ndarray, coeff: float) -> float:
        """Compute Goertzel magnitude for a block of samples."""
        s0 = 0.0
        s1 = 0.0
        s2 = 0.0
        for x in samples:
            s0 = x + coeff * s1 - s2
            s2 = s1
            s1 = s0
        return s1 * s1 + s2 * s2 - coeff * s1 * s2

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

        # Prepend residual from previous block
        if len(self._residual) > 0:
            samples = np.concatenate([self._residual, filtered])
        else:
            samples = filtered

        # Slice into bit-period chunks and classify each via Goertzel
        spb = self._spb
        pos = 0
        new_bits: list[int] = []
        while pos + spb <= len(samples):
            chunk = samples[pos : pos + spb]
            mark_mag = self._goertzel_mag(chunk, self._goertzel_mark_coeff)
            space_mag = self._goertzel_mag(chunk, self._goertzel_space_coeff)
            new_bits.append(1 if mark_mag > space_mag else 0)
            pos += spb

        # Save leftover samples for next block
        self._residual = samples[pos:]

        # Append new bits to sliding buffer
        self._bit_buffer.extend(new_bits)

        # Trim buffer to max size (keep newest bits)
        if len(self._bit_buffer) > self._max_bits:
            self._bit_buffer = self._bit_buffer[-self._max_bits :]

        # Scan for target word matches in the bit buffer
        matches = 0
        n_bits = len(self._bit_buffer)
        if n_bits >= 23:
            for start in range(n_bits - 22):
                word = 0
                for i in range(23):
                    word |= self._bit_buffer[start + i] << i
                if word == self._target_word:
                    matches += 1
                elif (word ^ 0x7FFFFF) == self._target_word:
                    matches += 1

        matched_this_block = False
        if matches >= self._match_threshold:
            self._consecutive_matches += matches
            self._is_matched = True
            matched_this_block = True
        else:
            self._consecutive_matches = max(0, self._consecutive_matches - 1)
            if self._consecutive_matches == 0:
                self._is_matched = False

        return matched_this_block
