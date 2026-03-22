"""Tests for session.py: RecordConfig and RecordingSession."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest


class TestRecordConfig:
    """Test RecordConfig dataclass creation and validation."""

    def test_can_import(self):
        """RecordConfig is importable from vtms_sdr.session."""
        from vtms_sdr.session import RecordConfig

    def test_create_minimal(self):
        """RecordConfig can be created with required fields."""
        from vtms_sdr.session import RecordConfig

        config = RecordConfig(
            freq=146_520_000,
            mod="fm",
            output_path=Path("test.wav"),
            audio_format="wav",
        )
        assert config.freq == 146_520_000
        assert config.mod == "fm"
        assert config.output_path == Path("test.wav")
        assert config.audio_format == "wav"

    def test_defaults(self):
        """RecordConfig has sensible defaults for optional fields."""
        from vtms_sdr.session import RecordConfig

        config = RecordConfig(
            freq=146_520_000,
            mod="fm",
            output_path=Path("test.wav"),
            audio_format="wav",
        )
        assert config.duration is None
        assert config.gain == "auto"
        assert config.squelch_db == -30.0
        assert config.device == 0
        assert config.ppm == 0
        assert config.transcriber is None
        assert config.monitor is None
        assert config.volume == 0.5
        assert config.label is None

    def test_all_fields(self):
        """RecordConfig accepts all fields."""
        from vtms_sdr.session import RecordConfig

        mock_transcriber = MagicMock()
        mock_monitor = MagicMock()
        config = RecordConfig(
            freq=462_562_500,
            mod="fm",
            output_path=Path("gmrs.mp3"),
            audio_format="mp3",
            duration=60.0,
            gain=40.0,
            squelch_db=-20.0,
            device=1,
            ppm=5,
            transcriber=mock_transcriber,
            monitor=mock_monitor,
            volume=0.8,
            label="GMRS",
        )
        assert config.gain == 40.0
        assert config.ppm == 5
        assert config.label == "GMRS"
        assert config.monitor is mock_monitor


class TestRecordingSession:
    """Test RecordingSession orchestration."""

    def _make_config(self, **overrides):
        """Helper to create a RecordConfig with defaults."""
        from vtms_sdr.session import RecordConfig

        defaults = dict(
            freq=146_520_000,
            mod="fm",
            output_path=Path("test.wav"),
            audio_format="wav",
            gain="auto",
            squelch_db=-30.0,
            device=0,
            ppm=0,
        )
        defaults.update(overrides)
        return RecordConfig(**defaults)

    def test_can_import(self):
        """RecordingSession is importable from vtms_sdr.session."""
        from vtms_sdr.session import RecordingSession

    def test_accepts_config(self):
        """RecordingSession accepts a RecordConfig."""
        from vtms_sdr.session import RecordingSession

        config = self._make_config()
        session = RecordingSession(config)
        assert session.config is config

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_run_creates_sdr_and_configures(self, MockRecorder, MockDemod, MockSDR):
        """run() opens an SDR device and configures it."""
        from vtms_sdr.session import RecordingSession

        # Set up mock SDR
        mock_sdr = MagicMock()
        mock_sdr.center_freq = 146_520_000
        mock_sdr.sample_rate = 2_048_000
        mock_sdr.get_info.return_value = {"gain": 40.0}
        mock_sdr.stream.return_value = iter([])
        MockSDR.return_value.__enter__ = MagicMock(return_value=mock_sdr)
        MockSDR.return_value.__exit__ = MagicMock(return_value=False)

        # Mock demodulator
        MockDemod.create.return_value = MagicMock()

        # Mock recorder
        mock_recorder = MagicMock()
        mock_recorder.record.return_value = {
            "file": "test.wav",
            "audio_duration_sec": 0.0,
            "file_size_bytes": 0,
        }
        MockRecorder.return_value = mock_recorder

        config = self._make_config(gain=40.0, ppm=5)
        session = RecordingSession(config)
        session.run()

        MockSDR.assert_called_once_with(device_index=0)
        mock_sdr.configure.assert_called_once_with(
            center_freq=146_520_000, gain=40.0, ppm=5
        )

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_run_creates_demodulator(self, MockRecorder, MockDemod, MockSDR):
        """run() creates a Demodulator matching the modulation type."""
        from vtms_sdr.session import RecordingSession

        mock_sdr = MagicMock()
        mock_sdr.sample_rate = 2_048_000
        mock_sdr.center_freq = 146_520_000
        mock_sdr.get_info.return_value = {"gain": "auto"}
        mock_sdr.stream.return_value = iter([])
        MockSDR.return_value.__enter__ = MagicMock(return_value=mock_sdr)
        MockSDR.return_value.__exit__ = MagicMock(return_value=False)

        MockDemod.create.return_value = MagicMock()

        mock_recorder = MagicMock()
        mock_recorder.record.return_value = {
            "file": "test.wav",
            "audio_duration_sec": 0.0,
            "file_size_bytes": 0,
        }
        MockRecorder.return_value = mock_recorder

        config = self._make_config(mod="am")
        session = RecordingSession(config)
        session.run()

        MockDemod.create.assert_called_once_with("am", sample_rate=2_048_000)

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_run_creates_recorder_and_records(self, MockRecorder, MockDemod, MockSDR):
        """run() creates an AudioRecorder and calls record()."""
        from vtms_sdr.session import RecordingSession

        mock_sdr = MagicMock()
        mock_sdr.sample_rate = 2_048_000
        mock_sdr.center_freq = 146_520_000
        mock_sdr.get_info.return_value = {"gain": "auto"}
        mock_sdr.stream.return_value = iter([])
        MockSDR.return_value.__enter__ = MagicMock(return_value=mock_sdr)
        MockSDR.return_value.__exit__ = MagicMock(return_value=False)

        MockDemod.create.return_value = MagicMock()

        expected_stats = {
            "file": "test.wav",
            "audio_duration_sec": 10.5,
            "file_size_bytes": 1024,
        }
        mock_recorder = MagicMock()
        mock_recorder.record.return_value = expected_stats
        MockRecorder.return_value = mock_recorder

        config = self._make_config(
            output_path=Path("test.wav"),
            audio_format="wav",
            squelch_db=-25.0,
            duration=60.0,
        )
        session = RecordingSession(config)
        stats = session.run()

        MockRecorder.assert_called_once()
        call_kwargs = MockRecorder.call_args[1]
        assert call_kwargs["output_path"] == Path("test.wav")
        assert call_kwargs["audio_format"] == "wav"
        assert call_kwargs["squelch_db"] == -25.0

        mock_recorder.record.assert_called_once()
        record_kwargs = mock_recorder.record.call_args[1]
        assert record_kwargs["duration"] == 60.0

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_run_returns_stats(self, MockRecorder, MockDemod, MockSDR):
        """run() returns stats dict from the recorder."""
        from vtms_sdr.session import RecordingSession

        mock_sdr = MagicMock()
        mock_sdr.sample_rate = 2_048_000
        mock_sdr.center_freq = 146_520_000
        mock_sdr.get_info.return_value = {"gain": "auto"}
        mock_sdr.stream.return_value = iter([])
        MockSDR.return_value.__enter__ = MagicMock(return_value=mock_sdr)
        MockSDR.return_value.__exit__ = MagicMock(return_value=False)

        MockDemod.create.return_value = MagicMock()

        expected_stats = {
            "file": "test.wav",
            "audio_duration_sec": 10.5,
            "file_size_bytes": 1024,
        }
        mock_recorder = MagicMock()
        mock_recorder.record.return_value = expected_stats
        MockRecorder.return_value = mock_recorder

        config = self._make_config()
        session = RecordingSession(config)
        stats = session.run()

        assert stats == expected_stats

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_run_passes_transcriber(self, MockRecorder, MockDemod, MockSDR):
        """run() passes transcriber to AudioRecorder when configured."""
        from vtms_sdr.session import RecordingSession

        mock_sdr = MagicMock()
        mock_sdr.sample_rate = 2_048_000
        mock_sdr.center_freq = 146_520_000
        mock_sdr.get_info.return_value = {"gain": "auto"}
        mock_sdr.stream.return_value = iter([])
        MockSDR.return_value.__enter__ = MagicMock(return_value=mock_sdr)
        MockSDR.return_value.__exit__ = MagicMock(return_value=False)

        MockDemod.create.return_value = MagicMock()

        mock_recorder = MagicMock()
        mock_recorder.record.return_value = {
            "file": "test.wav",
            "audio_duration_sec": 0.0,
            "file_size_bytes": 0,
        }
        MockRecorder.return_value = mock_recorder

        mock_transcriber = MagicMock()
        config = self._make_config(transcriber=mock_transcriber)
        session = RecordingSession(config)
        session.run()

        call_kwargs = MockRecorder.call_args[1]
        assert call_kwargs["transcriber"] is mock_transcriber

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_run_writes_log_header_when_transcribing(
        self, MockRecorder, MockDemod, MockSDR
    ):
        """run() calls write_log_header on transcriber before recording."""
        from vtms_sdr.session import RecordingSession

        mock_sdr = MagicMock()
        mock_sdr.sample_rate = 2_048_000
        mock_sdr.center_freq = 146_520_000
        mock_sdr.get_info.return_value = {"gain": "auto"}
        mock_sdr.stream.return_value = iter([])
        MockSDR.return_value.__enter__ = MagicMock(return_value=mock_sdr)
        MockSDR.return_value.__exit__ = MagicMock(return_value=False)

        MockDemod.create.return_value = MagicMock()

        mock_recorder = MagicMock()
        mock_recorder.record.return_value = {
            "file": "test.wav",
            "audio_duration_sec": 0.0,
            "file_size_bytes": 0,
        }
        MockRecorder.return_value = mock_recorder

        mock_transcriber = MagicMock()
        config = self._make_config(transcriber=mock_transcriber)
        session = RecordingSession(config)
        session.run()

        mock_transcriber.write_log_header.assert_called_once()

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_run_closes_transcriber(self, MockRecorder, MockDemod, MockSDR):
        """run() closes transcriber in finally block."""
        from vtms_sdr.session import RecordingSession

        mock_sdr = MagicMock()
        mock_sdr.sample_rate = 2_048_000
        mock_sdr.center_freq = 146_520_000
        mock_sdr.get_info.return_value = {"gain": "auto"}
        mock_sdr.stream.return_value = iter([])
        MockSDR.return_value.__enter__ = MagicMock(return_value=mock_sdr)
        MockSDR.return_value.__exit__ = MagicMock(return_value=False)

        MockDemod.create.return_value = MagicMock()

        mock_recorder = MagicMock()
        mock_recorder.record.return_value = {
            "file": "test.wav",
            "audio_duration_sec": 0.0,
            "file_size_bytes": 0,
        }
        MockRecorder.return_value = mock_recorder

        mock_transcriber = MagicMock()
        config = self._make_config(transcriber=mock_transcriber)
        session = RecordingSession(config)
        session.run()

        mock_transcriber.close.assert_called_once()

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_run_demodulates_iq_stream(self, MockRecorder, MockDemod, MockSDR):
        """run() feeds IQ blocks through demodulator to recorder."""
        from vtms_sdr.session import RecordingSession

        # Create realistic IQ data
        iq_block = np.zeros(256, dtype=np.complex64)

        mock_sdr = MagicMock()
        mock_sdr.sample_rate = 2_048_000
        mock_sdr.center_freq = 146_520_000
        mock_sdr.get_info.return_value = {"gain": "auto"}
        mock_sdr.stream.return_value = iter([iq_block])
        MockSDR.return_value.__enter__ = MagicMock(return_value=mock_sdr)
        MockSDR.return_value.__exit__ = MagicMock(return_value=False)

        mock_demod = MagicMock()
        audio_out = np.zeros(128, dtype=np.float32)
        mock_demod.demodulate.return_value = audio_out
        # Explicitly set pre_hp_audio to None so audio_stream yields 2-tuples
        # (MagicMock auto-creates attributes, which would make it truthy)
        mock_demod.pre_hp_audio = None
        MockDemod.create.return_value = mock_demod

        # Capture what gets passed to recorder.record()
        recorded_audio = []

        def fake_record(audio_gen, **kwargs):
            for item in audio_gen:
                recorded_audio.append(item)
            return {
                "file": "test.wav",
                "audio_duration_sec": 0.0,
                "file_size_bytes": 0,
            }

        mock_recorder = MagicMock()
        mock_recorder.record.side_effect = fake_record
        MockRecorder.return_value = mock_recorder

        config = self._make_config()
        session = RecordingSession(config)
        session.run()

        # Demodulator should have been called with the IQ block
        mock_demod.demodulate.assert_called_once()
        # Recorder should have received (power_db, audio) tuples
        assert len(recorded_audio) == 1
        power_db, audio = recorded_audio[0]
        assert isinstance(power_db, float)
        assert audio is audio_out


class TestSessionMonitorUIWiring:
    """Test that _run_with_monitor passes new params to MonitorUI."""

    def test_passes_new_params_to_monitor_ui(self):
        """MonitorUI receives model_size, gain, ppm, sdr_device, recorder."""
        from vtms_sdr.session import RecordingSession, RecordConfig

        mock_transcriber = MagicMock()
        mock_transcriber.model_size = "medium"
        mock_monitor = MagicMock()
        mock_sdr = MagicMock()

        cfg = RecordConfig(
            freq=146520000,
            mod="fm",
            output_path=Path("/tmp/test.wav"),
            audio_format="wav",
            gain=20.0,
            ppm=5,
            squelch_db=-30.0,
            transcriber=mock_transcriber,
            monitor=mock_monitor,
        )

        session = RecordingSession(cfg)

        with (
            patch("vtms_sdr.monitor.MonitorUI") as MockMonitorUI,
            patch("vtms_sdr.recorder.AudioRecorder") as MockRecorder,
        ):
            mock_ui_instance = MockMonitorUI.return_value
            mock_ui_instance.launch.return_value = {"audio_duration_sec": 1.0}

            result = session._run_with_monitor(cfg, lambda: iter([]), mock_sdr)

            # Verify MonitorUI was constructed with new kwargs
            call_kwargs = MockMonitorUI.call_args
            # Check positional and keyword args
            assert call_kwargs.kwargs.get("model_size") == "medium"
            assert call_kwargs.kwargs.get("gain") == 20.0
            assert call_kwargs.kwargs.get("ppm") == 5
            assert call_kwargs.kwargs.get("sdr_device") is mock_sdr
            assert call_kwargs.kwargs.get("recorder") is MockRecorder.return_value

    def test_model_size_none_when_transcriber_has_no_attr(self):
        """model_size is None when transcriber doesn't have model_size attribute."""
        from vtms_sdr.session import RecordingSession, RecordConfig

        mock_transcriber = MagicMock(spec=[])  # Empty spec, no model_size
        mock_monitor = MagicMock()

        cfg = RecordConfig(
            freq=146520000,
            mod="fm",
            output_path=Path("/tmp/test.wav"),
            audio_format="wav",
            transcriber=mock_transcriber,
            monitor=mock_monitor,
        )

        session = RecordingSession(cfg)

        with (
            patch("vtms_sdr.monitor.MonitorUI") as MockMonitorUI,
            patch("vtms_sdr.recorder.AudioRecorder"),
        ):
            mock_ui = MockMonitorUI.return_value
            mock_ui.launch.return_value = {"audio_duration_sec": 1.0}

            session._run_with_monitor(cfg, lambda: iter([]))

            assert MockMonitorUI.call_args.kwargs.get("model_size") is None

    def test_model_size_none_when_no_transcriber(self):
        """model_size is None when transcriber is not configured."""
        from vtms_sdr.session import RecordingSession, RecordConfig

        mock_monitor = MagicMock()

        cfg = RecordConfig(
            freq=146520000,
            mod="fm",
            output_path=Path("/tmp/test.wav"),
            audio_format="wav",
            monitor=mock_monitor,
        )

        session = RecordingSession(cfg)

        with (
            patch("vtms_sdr.monitor.MonitorUI") as MockMonitorUI,
            patch("vtms_sdr.recorder.AudioRecorder"),
        ):
            mock_ui = MockMonitorUI.return_value
            mock_ui.launch.return_value = {"audio_duration_sec": 1.0}

            session._run_with_monitor(cfg, lambda: iter([]))

            assert MockMonitorUI.call_args.kwargs.get("model_size") is None

    def test_squelch_callback_wired_to_recorder(self):
        """recorder._squelch_callback should be set to monitor_ui.update_squelch."""
        from vtms_sdr.session import RecordingSession, RecordConfig

        mock_monitor = MagicMock()

        cfg = RecordConfig(
            freq=146520000,
            mod="fm",
            output_path=Path("/tmp/test.wav"),
            audio_format="wav",
            monitor=mock_monitor,
        )

        session = RecordingSession(cfg)

        with (
            patch("vtms_sdr.monitor.MonitorUI") as MockMonitorUI,
            patch("vtms_sdr.recorder.AudioRecorder") as MockRecorder,
        ):
            mock_ui = MockMonitorUI.return_value
            mock_ui.launch.return_value = {"audio_duration_sec": 1.0}
            mock_recorder = MockRecorder.return_value

            session._run_with_monitor(cfg, lambda: iter([]))

            # Verify squelch callback was wired
            assert mock_recorder._squelch_callback == mock_ui.update_squelch


class TestRecordConfigDCSCode:
    """Test dcs_code field on RecordConfig."""

    def test_dcs_code_default_none(self):
        """RecordConfig.dcs_code should default to None."""
        from vtms_sdr.session import RecordConfig

        config = RecordConfig(
            freq=462_562_500,
            mod="fm",
            output_path=Path("test.wav"),
            audio_format="wav",
        )
        assert config.dcs_code is None

    def test_dcs_code_accepts_int(self):
        """RecordConfig should accept a dcs_code integer."""
        from vtms_sdr.session import RecordConfig

        config = RecordConfig(
            freq=462_562_500,
            mod="fm",
            output_path=Path("test.wav"),
            audio_format="wav",
            dcs_code=23,
        )
        assert config.dcs_code == 23


class TestSessionAudioStreamPreHP:
    """Test that audio_stream yields pre_hp_audio when available."""

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_audio_stream_yields_pre_hp_when_available(
        self, MockRecorder, MockDemod, MockSDR
    ):
        """audio_stream should yield 3-tuples when demod has pre_hp_audio."""
        from vtms_sdr.session import RecordingSession

        iq_block = np.zeros(256, dtype=np.complex64)
        audio_out = np.zeros(128, dtype=np.float32)
        pre_hp_out = np.ones(128, dtype=np.float32)

        mock_sdr = MagicMock()
        mock_sdr.sample_rate = 2_048_000
        mock_sdr.center_freq = 146_520_000
        mock_sdr.get_info.return_value = {"gain": "auto"}
        mock_sdr.stream.return_value = iter([iq_block])
        MockSDR.return_value.__enter__ = MagicMock(return_value=mock_sdr)
        MockSDR.return_value.__exit__ = MagicMock(return_value=False)

        mock_demod = MagicMock()
        mock_demod.demodulate.return_value = audio_out
        mock_demod.pre_hp_audio = pre_hp_out
        MockDemod.create.return_value = mock_demod

        recorded_items = []

        def fake_record(audio_gen, **kwargs):
            for item in audio_gen:
                recorded_items.append(item)
            return {
                "file": "test.wav",
                "audio_duration_sec": 0.0,
                "file_size_bytes": 0,
            }

        mock_recorder = MagicMock()
        mock_recorder.record.side_effect = fake_record
        MockRecorder.return_value = mock_recorder

        from vtms_sdr.session import RecordConfig

        config = RecordConfig(
            freq=146_520_000,
            mod="fm",
            output_path=Path("test.wav"),
            audio_format="wav",
        )
        session = RecordingSession(config)
        session.run()

        assert len(recorded_items) == 1
        assert len(recorded_items[0]) == 3
        power_db, audio, pre_hp = recorded_items[0]
        assert isinstance(power_db, float)
        assert audio is audio_out
        assert pre_hp is pre_hp_out

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_audio_stream_yields_2tuple_when_no_pre_hp(
        self, MockRecorder, MockDemod, MockSDR
    ):
        """audio_stream should yield 2-tuples when demod has no pre_hp_audio."""
        from vtms_sdr.session import RecordingSession

        iq_block = np.zeros(256, dtype=np.complex64)
        audio_out = np.zeros(128, dtype=np.float32)

        mock_sdr = MagicMock()
        mock_sdr.sample_rate = 2_048_000
        mock_sdr.center_freq = 146_520_000
        mock_sdr.get_info.return_value = {"gain": "auto"}
        mock_sdr.stream.return_value = iter([iq_block])
        MockSDR.return_value.__enter__ = MagicMock(return_value=mock_sdr)
        MockSDR.return_value.__exit__ = MagicMock(return_value=False)

        mock_demod = MagicMock(spec=["demodulate"])  # No pre_hp_audio attribute
        mock_demod.demodulate.return_value = audio_out
        MockDemod.create.return_value = mock_demod

        recorded_items = []

        def fake_record(audio_gen, **kwargs):
            for item in audio_gen:
                recorded_items.append(item)
            return {
                "file": "test.wav",
                "audio_duration_sec": 0.0,
                "file_size_bytes": 0,
            }

        mock_recorder = MagicMock()
        mock_recorder.record.side_effect = fake_record
        MockRecorder.return_value = mock_recorder

        from vtms_sdr.session import RecordConfig

        config = RecordConfig(
            freq=146_520_000,
            mod="fm",
            output_path=Path("test.wav"),
            audio_format="wav",
        )
        session = RecordingSession(config)
        session.run()

        assert len(recorded_items) == 1
        assert len(recorded_items[0]) == 2
        power_db, audio = recorded_items[0]
        assert isinstance(power_db, float)
        assert audio is audio_out


class TestSessionDCSWiring:
    """Test that session wires DCS decoder to recorder when dcs_code is set."""

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_headless_passes_dcs_decoder_when_code_set(
        self, MockRecorder, MockDemod, MockSDR
    ):
        """_run_headless should create DCS decoder and pass to recorder when dcs_code is set."""
        from vtms_sdr.session import RecordingSession, RecordConfig

        mock_sdr = MagicMock()
        mock_sdr.sample_rate = 2_048_000
        mock_sdr.center_freq = 462_562_500
        mock_sdr.get_info.return_value = {"gain": "auto"}
        mock_sdr.stream.return_value = iter([])
        MockSDR.return_value.__enter__ = MagicMock(return_value=mock_sdr)
        MockSDR.return_value.__exit__ = MagicMock(return_value=False)

        MockDemod.create.return_value = MagicMock()

        mock_recorder = MagicMock()
        mock_recorder.record.return_value = {
            "file": "test.wav",
            "audio_duration_sec": 0.0,
            "file_size_bytes": 0,
        }
        MockRecorder.return_value = mock_recorder

        config = RecordConfig(
            freq=462_562_500,
            mod="fm",
            output_path=Path("test.wav"),
            audio_format="wav",
            dcs_code=23,
        )
        session = RecordingSession(config)
        session.run()

        call_kwargs = MockRecorder.call_args[1]
        assert call_kwargs.get("dcs_decoder") is not None

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_headless_no_dcs_decoder_when_code_not_set(
        self, MockRecorder, MockDemod, MockSDR
    ):
        """_run_headless should not pass dcs_decoder when dcs_code is None."""
        from vtms_sdr.session import RecordingSession, RecordConfig

        mock_sdr = MagicMock()
        mock_sdr.sample_rate = 2_048_000
        mock_sdr.center_freq = 462_562_500
        mock_sdr.get_info.return_value = {"gain": "auto"}
        mock_sdr.stream.return_value = iter([])
        MockSDR.return_value.__enter__ = MagicMock(return_value=mock_sdr)
        MockSDR.return_value.__exit__ = MagicMock(return_value=False)

        MockDemod.create.return_value = MagicMock()

        mock_recorder = MagicMock()
        mock_recorder.record.return_value = {
            "file": "test.wav",
            "audio_duration_sec": 0.0,
            "file_size_bytes": 0,
        }
        MockRecorder.return_value = mock_recorder

        config = RecordConfig(
            freq=462_562_500,
            mod="fm",
            output_path=Path("test.wav"),
            audio_format="wav",
        )
        session = RecordingSession(config)
        session.run()

        call_kwargs = MockRecorder.call_args[1]
        # Should either not have dcs_decoder or it should be None
        assert call_kwargs.get("dcs_decoder") is None
