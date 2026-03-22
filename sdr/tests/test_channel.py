"""Tests for vtms_sdr.channel -- per-channel configuration."""

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

    def test_defaults(self):
        ch = ChannelConfig(freq=462_562_500, mod="fm", output_path=Path("ch1.wav"))
        assert ch.audio_format == "wav"
        assert ch.squelch_db == -30.0
        assert ch.dcs_code is None
        assert ch.label is None

    def test_output_path_preserved(self):
        p = Path("/tmp/recording/ch2.wav")
        ch = ChannelConfig(freq=462_612_500, mod="fm", output_path=p)
        assert ch.output_path == p
