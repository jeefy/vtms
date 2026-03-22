"""Tests for vtms_sdr.channelizer -- DDC channel extraction."""

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

        ch = Channelizer(center_freq=center, sample_rate=sr, channel_freqs=[f1, f2])

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
