"""Tests for StateManager integration in session.py and CLI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


class TestRecordConfigStateManager:
    """Test state_manager field on RecordConfig."""

    def test_state_manager_default_none(self):
        """RecordConfig.state_manager should default to None."""
        from vtms_sdr.session import RecordConfig

        config = RecordConfig(
            freq=146_520_000,
            mod="fm",
            output_path=Path("test.wav"),
            audio_format="wav",
        )
        assert config.state_manager is None

    def test_state_manager_accepts_instance(self):
        """RecordConfig should accept a StateManager instance."""
        from vtms_sdr.session import RecordConfig
        from vtms_sdr.state import StateManager

        sm = StateManager()
        config = RecordConfig(
            freq=146_520_000,
            mod="fm",
            output_path=Path("test.wav"),
            audio_format="wav",
            state_manager=sm,
        )
        assert config.state_manager is sm


class TestSessionPublishesState:
    """Test that RecordingSession publishes state through StateManager."""

    def _make_config(self, **overrides):
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

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_publishes_initial_state(self, MockRecorder, MockDemod, MockSDR):
        """run() should publish initial state (freq, mod, gain, etc.)."""
        from vtms_sdr.session import RecordingSession
        from vtms_sdr.state import StateManager

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

        sm = StateManager()
        # Track all published status values to verify "recording" was set
        status_history: list[str] = []
        sm.subscribe(lambda k, v: status_history.append(v) if k == "status" else None)

        config = self._make_config(state_manager=sm)
        session = RecordingSession(config)
        session.run()

        snap = sm.snapshot()
        assert snap["freq"] == 146_520_000
        assert snap["mod"] == "fm"
        # "recording" was published during the session, then "stopped" in finally
        assert "recording" in status_history
        assert snap["status"] == "stopped"

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_publishes_signal_power(self, MockRecorder, MockDemod, MockSDR):
        """run() should publish signal_power from IQ stream."""
        from vtms_sdr.session import RecordingSession
        from vtms_sdr.state import StateManager

        iq_block = np.ones(256, dtype=np.complex64) * 0.5

        mock_sdr = MagicMock()
        mock_sdr.sample_rate = 2_048_000
        mock_sdr.center_freq = 146_520_000
        mock_sdr.get_info.return_value = {"gain": "auto"}
        mock_sdr.stream.return_value = iter([iq_block])
        MockSDR.return_value.__enter__ = MagicMock(return_value=mock_sdr)
        MockSDR.return_value.__exit__ = MagicMock(return_value=False)

        mock_demod = MagicMock()
        mock_demod.demodulate.return_value = np.zeros(128, dtype=np.float32)
        mock_demod.pre_hp_audio = None
        MockDemod.create.return_value = mock_demod

        mock_recorder = MagicMock()
        mock_recorder.record.side_effect = lambda gen, **kw: (
            [_ for _ in gen],
            {"file": "test.wav", "audio_duration_sec": 0.0, "file_size_bytes": 0},
        )[1]
        MockRecorder.return_value = mock_recorder

        sm = StateManager()
        config = self._make_config(state_manager=sm)
        session = RecordingSession(config)
        session.run()

        snap = sm.snapshot()
        assert "signal_power" in snap
        assert isinstance(snap["signal_power"], float)

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_publishes_stopped_status(self, MockRecorder, MockDemod, MockSDR):
        """run() should publish status=stopped when recording ends."""
        from vtms_sdr.session import RecordingSession
        from vtms_sdr.state import StateManager

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

        sm = StateManager()
        config = self._make_config(state_manager=sm)
        session = RecordingSession(config)
        session.run()

        assert sm.snapshot()["status"] == "stopped"

    @patch("vtms_sdr.sdr.SDRDevice")
    @patch("vtms_sdr.demod.Demodulator")
    @patch("vtms_sdr.recorder.AudioRecorder")
    def test_no_state_manager_still_works(self, MockRecorder, MockDemod, MockSDR):
        """run() should still work when no state_manager is provided."""
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

        config = self._make_config()
        session = RecordingSession(config)
        stats = session.run()  # Should not raise
        assert stats["file"] == "test.wav"


class TestCLIMqttFlags:
    """Test --mqtt-broker and --mqtt-prefix CLI options."""

    def test_mqtt_broker_in_help(self):
        from click.testing import CliRunner
        from vtms_sdr.cli import record

        runner = CliRunner()
        result = runner.invoke(record, ["--help"])
        assert "--mqtt-broker" in result.output

    def test_mqtt_prefix_in_help(self):
        from click.testing import CliRunner
        from vtms_sdr.cli import record

        runner = CliRunner()
        result = runner.invoke(record, ["--help"])
        assert "--mqtt-prefix" in result.output

    @patch("vtms_sdr.session.RecordingSession")
    @patch("vtms_sdr.mqtt_bridge.MqttBridge")
    def test_mqtt_broker_creates_bridge(self, MockBridge, MockSession):
        """--mqtt-broker should create and start a MqttBridge."""
        from click.testing import CliRunner
        from vtms_sdr.cli import main

        MockSession.return_value.run.return_value = {
            "file": "test.wav",
            "audio_duration_sec": 0.0,
            "file_size_bytes": 0,
        }

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["record", "-f", "146.52M", "--mqtt-broker", "192.168.1.10"],
        )

        # MqttBridge should have been created and started
        MockBridge.assert_called_once()
        call_kwargs = MockBridge.call_args
        assert call_kwargs.kwargs["broker"] == "192.168.1.10"
        MockBridge.return_value.start.assert_called_once()
        MockBridge.return_value.stop.assert_called_once()

    @patch("vtms_sdr.session.RecordingSession")
    @patch("vtms_sdr.mqtt_bridge.MqttBridge")
    def test_mqtt_custom_prefix(self, MockBridge, MockSession):
        """--mqtt-prefix should be passed to MqttBridge."""
        from click.testing import CliRunner
        from vtms_sdr.cli import main

        MockSession.return_value.run.return_value = {
            "file": "test.wav",
            "audio_duration_sec": 0.0,
            "file_size_bytes": 0,
        }

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "record",
                "-f",
                "146.52M",
                "--mqtt-broker",
                "localhost",
                "--mqtt-prefix",
                "myteam/",
            ],
        )

        call_kwargs = MockBridge.call_args
        assert call_kwargs.kwargs["prefix"] == "myteam/"

    @patch("vtms_sdr.session.RecordingSession")
    def test_no_mqtt_broker_no_bridge(self, MockSession):
        """Without --mqtt-broker, no MqttBridge should be created."""
        from click.testing import CliRunner
        from vtms_sdr.cli import main

        MockSession.return_value.run.return_value = {
            "file": "test.wav",
            "audio_duration_sec": 0.0,
            "file_size_bytes": 0,
        }

        runner = CliRunner()
        with patch("vtms_sdr.mqtt_bridge.MqttBridge") as MockBridge:
            result = runner.invoke(main, ["record", "-f", "146.52M"])
            MockBridge.assert_not_called()
