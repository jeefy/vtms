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
        num_taps = 101
        self._channel_filter = firwin(num_taps, cutoff)

        # Per-channel filter state: real and imag each need (num_taps - 1) elements
        self._num_zi = num_taps - 1
        self._filter_states: list[tuple[np.ndarray, np.ndarray]] = [
            (np.zeros(self._num_zi), np.zeros(self._num_zi)) for _ in self.channel_freqs
        ]

    @property
    def num_channels(self) -> int:
        return len(self.channel_freqs)

    def extract(self, iq_samples: np.ndarray) -> list[np.ndarray]:
        """Extract all channels from a block of wide-IQ samples.

        Args:
            iq_samples: Complex64 wideband IQ samples.

        Returns:
            List of complex64 arrays, one per channel, at the original
            sample rate (no decimation -- demodulator handles that).
        """
        n = len(iq_samples)
        t = np.arange(n) / self.sample_rate
        results: list[np.ndarray] = []

        for i, freq in enumerate(self.channel_freqs):
            # Frequency shift: move channel to baseband
            offset = freq - self.center_freq
            mixer = np.exp(-2j * np.pi * offset * t).astype(np.complex64)
            shifted = iq_samples * mixer

            # Apply channel filter (lowpass) -- I and Q separately
            zi_r, zi_i = self._filter_states[i]
            real_filt, new_zi_r = lfilter(
                self._channel_filter,
                1.0,
                np.real(shifted),
                zi=zi_r,
            )
            imag_filt, new_zi_i = lfilter(
                self._channel_filter,
                1.0,
                np.imag(shifted),
                zi=zi_i,
            )

            # Update filter state for cross-block continuity
            self._filter_states[i] = (new_zi_r, new_zi_i)

            channel_iq = (real_filt + 1j * imag_filt).astype(np.complex64)
            results.append(channel_iq)

        return results
