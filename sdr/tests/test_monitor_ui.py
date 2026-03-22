"""Tests for the MonitorUI curses-based display."""

import threading
import time
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest


class TestMonitorUIInit:
    """Test MonitorUI construction."""

    def test_stores_frequency(self):
        """MonitorUI stores the frequency for display."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui.freq == 146520000

    def test_stores_modulation(self):
        """MonitorUI stores the modulation type."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui.mod == "fm"

    def test_stores_output_path(self):
        """MonitorUI stores the output path."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui.output_path == "/tmp/test.wav"

    def test_stores_squelch(self):
        """MonitorUI stores the squelch threshold."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui.squelch_db == -40.0


class TestMonitorUIState:
    """Test thread-safe state updates."""

    def test_update_progress(self):
        """update_progress stores elapsed and audio duration."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        ui.update_progress(elapsed=65.3, samples_written=48000 * 30, sample_rate=48000)

        assert ui._state["elapsed"] == 65.3
        assert ui._state["audio_duration"] == 30.0

    def test_update_squelch(self):
        """update_squelch stores squelch open state and power level."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        ui.update_squelch(is_open=True, power_db=-32.1)

        assert ui._state["squelch_open"] is True
        assert ui._state["power_db"] == -32.1

    def test_add_transcription(self):
        """add_transcription appends to the log."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        ui.add_transcription("00:05:12", "Spotter", "Box box, pit entry")

        assert len(ui._state["transcriptions"]) == 1
        assert ui._state["transcriptions"][0] == (
            "00:05:12",
            "Spotter",
            "Box box, pit entry",
        )

    def test_add_multiple_transcriptions(self):
        """Multiple transcriptions are accumulated in order."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        ui.add_transcription("00:05:12", "Spotter", "Box box")
        ui.add_transcription("00:05:30", "Driver", "Copy")

        assert len(ui._state["transcriptions"]) == 2
        assert ui._state["transcriptions"][1][2] == "Copy"

    def test_transcription_limit(self):
        """Transcription log should be bounded to prevent memory growth."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        # Add more than the limit
        for i in range(200):
            ui.add_transcription(f"00:{i:02d}:00", "Test", f"Message {i}")

        assert len(ui._state["transcriptions"]) <= ui.MAX_TRANSCRIPTION_LINES

    def test_initial_state(self):
        """Initial state should have sensible defaults."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui._state["elapsed"] == 0.0
        assert ui._state["audio_duration"] == 0.0
        assert ui._state["squelch_open"] is False
        assert ui._state["power_db"] == -100.0
        assert ui._state["transcriptions"] == []


class TestMonitorUIKeyHandling:
    """Test keyboard input handling."""

    def test_volume_up(self):
        """'+' key increases monitor volume by 5%."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        ui._handle_key(ord("+"))

        assert monitor.volume == pytest.approx(0.55)

    def test_volume_down(self):
        """'-' key decreases monitor volume by 5%."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        ui._handle_key(ord("-"))

        assert monitor.volume == pytest.approx(0.45)

    def test_volume_up_clamps_at_max(self):
        """Volume should not exceed 1.0."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.98
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        ui._handle_key(ord("+"))

        assert monitor.volume == 1.0

    def test_volume_down_clamps_at_min(self):
        """Volume should not go below 0.0."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.02
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        ui._handle_key(ord("-"))

        assert monitor.volume == 0.0

    def test_q_sets_stopped(self):
        """'q' key sets the stopped flag."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        ui._handle_key(ord("q"))

        assert ui.stopped is True

    def test_Q_sets_stopped(self):
        """'Q' key also sets the stopped flag."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        ui._handle_key(ord("Q"))

        assert ui.stopped is True

    def test_unknown_key_ignored(self):
        """Unknown keys should not change state."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        ui._handle_key(ord("x"))

        assert monitor.volume == 0.5
        assert ui.stopped is False

    def test_equals_key_increases_volume(self):
        """'=' key (unshifted +) should also increase volume."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        ui._handle_key(ord("="))

        assert monitor.volume == pytest.approx(0.55)


class TestMonitorUIFormatting:
    """Test display formatting helpers."""

    def test_format_frequency_mhz(self):
        """Frequency should be formatted in MHz."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui._format_freq() == "146.520 MHz"

    def test_format_frequency_ghz(self):
        """Frequency above 1 GHz should still show MHz."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=1296000000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui._format_freq() == "1296.000 MHz"

    def test_format_volume_bar(self):
        """Volume bar should show filled/empty blocks proportionally."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        bar = ui._format_volume_bar(width=20)
        # Should be about half filled
        filled = bar.count("\u2588")  # Full block character
        assert 9 <= filled <= 11  # Allow rounding

    def test_format_elapsed(self):
        """Elapsed time should be formatted as HH:MM:SS."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        ui.update_progress(elapsed=3661.5, samples_written=0, sample_rate=48000)
        assert ui._format_elapsed() == "01:01:01"


class TestMonitorUIThreadSafety:
    """Test that state updates are thread-safe."""

    def test_concurrent_updates_dont_crash(self):
        """Multiple threads updating state simultaneously should not crash."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )

        errors = []

        def update_progress():
            try:
                for i in range(100):
                    ui.update_progress(
                        elapsed=float(i), samples_written=i * 48000, sample_rate=48000
                    )
            except Exception as e:
                errors.append(e)

        def update_squelch():
            try:
                for i in range(100):
                    ui.update_squelch(is_open=(i % 2 == 0), power_db=-30.0 + i * 0.1)
            except Exception as e:
                errors.append(e)

        def add_transcripts():
            try:
                for i in range(100):
                    ui.add_transcription(f"00:{i:02d}:00", "Test", f"Msg {i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=update_progress),
            threading.Thread(target=update_squelch),
            threading.Thread(target=add_transcripts),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert errors == [], f"Thread-safety errors: {errors}"


class TestMonitorUILaunch:
    """Test MonitorUI.launch() curses.wrapper integration."""

    @patch("vtms_sdr.monitor.curses")
    def test_launch_calls_curses_wrapper(self, mock_curses):
        """launch() should invoke curses.wrapper."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )

        expected_stats = {"audio_duration_sec": 1.0}
        mock_curses.wrapper.return_value = expected_stats

        record_func = MagicMock(return_value=expected_stats)
        result = ui.launch(record_func)

        mock_curses.wrapper.assert_called_once()
        assert result == expected_stats

    @patch("vtms_sdr.monitor.curses")
    def test_launch_passes_record_func_to_run(self, mock_curses):
        """launch() should pass record_func through to curses.wrapper."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )

        mock_curses.wrapper.return_value = {"stats": True}

        record_func = MagicMock()
        ui.launch(record_func)

        # The wrapper was called with a callable and record_func
        args = mock_curses.wrapper.call_args[0]
        assert callable(args[0])
        assert args[1] == record_func


class TestMonitorUIExtendedInit:
    """Test MonitorUI extended constructor params for TUI enhancements."""

    def test_default_model_size_is_none(self):
        """model_size defaults to None when not provided."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui.model_size is None

    def test_stores_model_size(self):
        """MonitorUI stores model_size when provided."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            model_size="medium",
        )
        assert ui.model_size == "medium"

    def test_default_gain_is_none(self):
        """gain defaults to None when not provided."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui.gain is None

    def test_stores_gain(self):
        """MonitorUI stores gain when provided."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            gain=20.0,
        )
        assert ui.gain == 20.0

    def test_stores_gain_auto(self):
        """MonitorUI stores 'auto' gain."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            gain="auto",
        )
        assert ui.gain == "auto"

    def test_default_ppm_is_none(self):
        """ppm defaults to None when not provided."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui.ppm is None

    def test_stores_ppm(self):
        """MonitorUI stores ppm when provided."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            ppm=5,
        )
        assert ui.ppm == 5

    def test_default_sdr_device_is_none(self):
        """sdr_device defaults to None."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui.sdr_device is None

    def test_stores_sdr_device(self):
        """MonitorUI stores sdr_device when provided."""
        from vtms_sdr.monitor import MonitorUI

        sdr = MagicMock()
        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            sdr_device=sdr,
        )
        assert ui.sdr_device is sdr

    def test_default_recorder_is_none(self):
        """recorder defaults to None."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui.recorder is None

    def test_stores_recorder(self):
        """MonitorUI stores recorder when provided."""
        from vtms_sdr.monitor import MonitorUI

        recorder = MagicMock()
        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            recorder=recorder,
        )
        assert ui.recorder is recorder

    def test_existing_tests_still_pass_without_new_params(self):
        """All existing constructor calls with 5 positional args still work."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui.freq == 146520000
        assert ui.stopped is False


class TestMonitorUILiveAdjustKeys:
    """Test squelch/gain/PPM key handlers."""

    # --- Squelch keys (s/S) ---

    def test_s_decreases_squelch_by_1(self):
        """'s' key decreases squelch_db by 1 and updates recorder."""
        from vtms_sdr.monitor import MonitorUI

        recorder = MagicMock()
        recorder.squelch_db = -30.0
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=monitor,
            recorder=recorder,
        )
        ui._handle_key(ord("s"))
        assert ui.squelch_db == -31.0
        assert recorder.squelch_db == -31.0

    def test_S_increases_squelch_by_1(self):
        """'S' key increases squelch_db by 1 and updates recorder."""
        from vtms_sdr.monitor import MonitorUI

        recorder = MagicMock()
        recorder.squelch_db = -30.0
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=monitor,
            recorder=recorder,
        )
        ui._handle_key(ord("S"))
        assert ui.squelch_db == -29.0
        assert recorder.squelch_db == -29.0

    def test_squelch_no_recorder_still_updates_ui(self):
        """Squelch keys update UI squelch_db even without recorder."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=monitor,
        )
        ui._handle_key(ord("s"))
        assert ui.squelch_db == -31.0

    # --- Gain keys (g/G) ---

    def test_g_decreases_gain_by_1(self):
        """'g' key decreases gain by 1 and calls sdr_device.set_gain()."""
        from vtms_sdr.monitor import MonitorUI

        sdr = MagicMock()
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=monitor,
            gain=20.0,
            sdr_device=sdr,
        )
        ui._handle_key(ord("g"))
        assert ui.gain == 19.0
        sdr.set_gain.assert_called_once_with(19.0)

    def test_G_increases_gain_by_1(self):
        """'G' key increases gain by 1 and calls sdr_device.set_gain()."""
        from vtms_sdr.monitor import MonitorUI

        sdr = MagicMock()
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=monitor,
            gain=20.0,
            sdr_device=sdr,
        )
        ui._handle_key(ord("G"))
        assert ui.gain == 21.0
        sdr.set_gain.assert_called_once_with(21.0)

    def test_gain_auto_converts_to_20_on_first_adjustment(self):
        """If gain is 'auto', first key press converts to 20.0 then adjusts."""
        from vtms_sdr.monitor import MonitorUI

        sdr = MagicMock()
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=monitor,
            gain="auto",
            sdr_device=sdr,
        )
        ui._handle_key(ord("g"))
        assert ui.gain == 19.0
        sdr.set_gain.assert_called_once_with(19.0)

    def test_gain_clamps_at_0(self):
        """Gain should not go below 0."""
        from vtms_sdr.monitor import MonitorUI

        sdr = MagicMock()
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=monitor,
            gain=0.5,
            sdr_device=sdr,
        )
        ui._handle_key(ord("g"))
        assert ui.gain == 0.0
        sdr.set_gain.assert_called_once_with(0.0)

    def test_gain_clamps_at_50(self):
        """Gain should not exceed 50."""
        from vtms_sdr.monitor import MonitorUI

        sdr = MagicMock()
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=monitor,
            gain=49.5,
            sdr_device=sdr,
        )
        ui._handle_key(ord("G"))
        assert ui.gain == 50.0
        sdr.set_gain.assert_called_once_with(50.0)

    def test_gain_no_sdr_still_updates_ui(self):
        """Gain keys update UI gain even without sdr_device."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=monitor,
            gain=20.0,
        )
        ui._handle_key(ord("g"))
        assert ui.gain == 19.0

    def test_gain_none_ignores_keys(self):
        """If gain is None (not provided), gain keys are ignored."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=monitor,
        )
        ui._handle_key(ord("g"))
        assert ui.gain is None

    # --- PPM keys (p/P) ---

    def test_p_decreases_ppm_by_1(self):
        """'p' key decreases ppm by 1 and calls sdr_device.set_ppm()."""
        from vtms_sdr.monitor import MonitorUI

        sdr = MagicMock()
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=monitor,
            ppm=5,
            sdr_device=sdr,
        )
        ui._handle_key(ord("p"))
        assert ui.ppm == 4
        sdr.set_ppm.assert_called_once_with(4)

    def test_P_increases_ppm_by_1(self):
        """'P' key increases ppm by 1 and calls sdr_device.set_ppm()."""
        from vtms_sdr.monitor import MonitorUI

        sdr = MagicMock()
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=monitor,
            ppm=5,
            sdr_device=sdr,
        )
        ui._handle_key(ord("P"))
        assert ui.ppm == 6
        sdr.set_ppm.assert_called_once_with(6)

    def test_ppm_no_sdr_still_updates_ui(self):
        """PPM keys update UI ppm even without sdr_device."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=monitor,
            ppm=5,
        )
        ui._handle_key(ord("p"))
        assert ui.ppm == 4

    def test_ppm_none_ignores_keys(self):
        """If ppm is None (not provided), ppm keys are ignored."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=monitor,
        )
        ui._handle_key(ord("p"))
        assert ui.ppm is None


class TestMonitorUIDrawEnhancements:
    """Test the enhanced _draw() display rows."""

    def _make_ui(self, **kwargs):
        """Helper to create MonitorUI with common defaults."""
        from vtms_sdr.monitor import MonitorUI

        defaults = dict(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=MagicMock(volume=0.5),
        )
        defaults.update(kwargs)
        return MonitorUI(**defaults)

    def test_draw_shows_model_size(self):
        """_draw() includes 'Model: medium' when model_size is set."""
        ui = self._make_ui(model_size="medium")
        stdscr = MagicMock()
        stdscr.getmaxyx.return_value = (40, 100)
        ui._draw(stdscr)

        drawn = " ".join(
            str(call.args[2])
            for call in stdscr.addstr.call_args_list
            if len(call.args) >= 3
        )
        assert "Model: medium" in drawn

    def test_draw_no_model_row_when_none(self):
        """_draw() does not show model row when model_size is None."""
        ui = self._make_ui()
        stdscr = MagicMock()
        stdscr.getmaxyx.return_value = (40, 100)
        ui._draw(stdscr)

        drawn = " ".join(
            str(call.args[2])
            for call in stdscr.addstr.call_args_list
            if len(call.args) >= 3
        )
        assert "Model:" not in drawn

    def test_draw_shows_gain(self):
        """_draw() includes gain value when gain is set."""
        ui = self._make_ui(gain=20.0)
        stdscr = MagicMock()
        stdscr.getmaxyx.return_value = (40, 100)
        ui._draw(stdscr)

        drawn = " ".join(
            str(call.args[2])
            for call in stdscr.addstr.call_args_list
            if len(call.args) >= 3
        )
        assert "Gain:" in drawn
        assert "20.0" in drawn

    def test_draw_shows_gain_auto(self):
        """_draw() shows 'auto' for gain when set to auto."""
        ui = self._make_ui(gain="auto")
        stdscr = MagicMock()
        stdscr.getmaxyx.return_value = (40, 100)
        ui._draw(stdscr)

        drawn = " ".join(
            str(call.args[2])
            for call in stdscr.addstr.call_args_list
            if len(call.args) >= 3
        )
        assert "Gain:" in drawn
        assert "auto" in drawn

    def test_draw_shows_ppm(self):
        """_draw() includes PPM value when ppm is set."""
        ui = self._make_ui(ppm=5)
        stdscr = MagicMock()
        stdscr.getmaxyx.return_value = (40, 100)
        ui._draw(stdscr)

        drawn = " ".join(
            str(call.args[2])
            for call in stdscr.addstr.call_args_list
            if len(call.args) >= 3
        )
        assert "PPM:" in drawn
        assert "5" in drawn

    def test_draw_footer_shows_key_hints(self):
        """Footer includes key hints for new controls."""
        ui = self._make_ui(gain=20.0, ppm=5)
        stdscr = MagicMock()
        stdscr.getmaxyx.return_value = (40, 100)
        ui._draw(stdscr)

        drawn = " ".join(
            str(call.args[2])
            for call in stdscr.addstr.call_args_list
            if len(call.args) >= 3
        )
        assert "s/S" in drawn
        assert "g/G" in drawn
        assert "p/P" in drawn


class TestMonitorUIQuitWiresRecorder:
    """Test that pressing 'q'/'Q' wires through to recorder._stopped."""

    def test_q_sets_recorder_stopped_event(self):
        """Pressing 'q' sets the recorder's _stopped threading.Event."""
        from vtms_sdr.monitor import MonitorUI
        from vtms_sdr.recorder import AudioRecorder

        monitor = MagicMock()
        monitor.volume = 0.5
        recorder = AudioRecorder("/dev/null", squelch_db=-100)
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            recorder=recorder,
        )
        ui._handle_key(ord("q"))

        assert recorder._stopped.is_set() is True

    def test_Q_sets_recorder_stopped_event(self):
        """Pressing 'Q' sets the recorder's _stopped threading.Event."""
        from vtms_sdr.monitor import MonitorUI
        from vtms_sdr.recorder import AudioRecorder

        monitor = MagicMock()
        monitor.volume = 0.5
        recorder = AudioRecorder("/dev/null", squelch_db=-100)
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            recorder=recorder,
        )
        ui._handle_key(ord("Q"))

        assert recorder._stopped.is_set() is True

    def test_q_without_recorder_does_not_crash(self):
        """Pressing 'q' with no recorder (None) does not raise."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            recorder=None,
        )
        # Should not raise
        ui._handle_key(ord("q"))

        assert ui.stopped is True

    def test_q_still_sets_stopped_flag(self):
        """Pressing 'q' with a recorder still sets ui.stopped = True."""
        from vtms_sdr.monitor import MonitorUI
        from vtms_sdr.recorder import AudioRecorder

        monitor = MagicMock()
        monitor.volume = 0.5
        recorder = AudioRecorder("/dev/null", squelch_db=-100)
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            recorder=recorder,
        )
        ui._handle_key(ord("q"))

        assert ui.stopped is True


class TestMonitorUISigintHandler:
    """Test SIGINT handling for graceful Ctrl+C shutdown in curses mode."""

    def test_handle_sigint_sets_stopped(self):
        """_handle_sigint() sets ui.stopped = True."""
        from vtms_sdr.monitor import MonitorUI
        from vtms_sdr.recorder import AudioRecorder

        monitor = MagicMock()
        monitor.volume = 0.5
        recorder = AudioRecorder("/dev/null", squelch_db=-100)
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            recorder=recorder,
        )
        assert ui.stopped is False

        ui._handle_sigint()

        assert ui.stopped is True

    def test_handle_sigint_sets_recorder_stopped_event(self):
        """_handle_sigint() sets recorder._stopped event when recorder exists."""
        from vtms_sdr.monitor import MonitorUI
        from vtms_sdr.recorder import AudioRecorder

        monitor = MagicMock()
        monitor.volume = 0.5
        recorder = AudioRecorder("/dev/null", squelch_db=-100)
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            recorder=recorder,
        )
        assert not recorder._stopped.is_set()

        ui._handle_sigint()

        assert recorder._stopped.is_set()

    def test_handle_sigint_without_recorder_does_not_crash(self):
        """_handle_sigint() with no recorder (None) does not raise."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            recorder=None,
        )

        # Should not raise
        ui._handle_sigint()

        assert ui.stopped is True

    @patch("vtms_sdr.monitor.curses")
    def test_sigint_handler_restored_after_run(self, mock_curses):
        """Original SIGINT handler is restored after run() completes."""
        import signal
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )

        original_handler = signal.getsignal(signal.SIGINT)

        # Mock stdscr so curses calls work
        mock_stdscr = MagicMock()
        mock_stdscr.getch.return_value = -1
        mock_stdscr.getmaxyx.return_value = (40, 100)

        # record_func that completes immediately (setting stopped via thread)
        def quick_record():
            return {"audio_duration_sec": 0.0}

        ui.run(mock_stdscr, quick_record)

        # After run() returns, original handler should be restored
        restored_handler = signal.getsignal(signal.SIGINT)
        assert restored_handler is original_handler


class TestMonitorUIColors:
    """Test curses color support with graceful fallback."""

    def _make_ui(self, **kwargs):
        """Helper to create MonitorUI with common defaults."""
        from vtms_sdr.monitor import MonitorUI

        defaults = dict(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=MagicMock(volume=0.5),
        )
        defaults.update(kwargs)
        return MonitorUI(**defaults)

    def test_has_colors_defaults_false(self):
        """_has_colors is False after construction (no curses init)."""
        ui = self._make_ui()
        assert ui._has_colors is False

    @patch("vtms_sdr.monitor.curses")
    def test_init_colors_sets_has_colors_true(self, mock_curses):
        """_init_colors() sets _has_colors=True when curses color init succeeds."""
        ui = self._make_ui()
        # All curses color calls succeed (default mock behavior)
        ui._init_colors()
        assert ui._has_colors is True

    @patch("vtms_sdr.monitor.curses")
    def test_init_colors_graceful_fallback(self, mock_curses):
        """_init_colors() sets _has_colors=False when curses.start_color() raises."""
        import curses as real_curses

        ui = self._make_ui()
        mock_curses.error = real_curses.error
        mock_curses.start_color.side_effect = real_curses.error("no color support")
        ui._init_colors()
        assert ui._has_colors is False

    @patch("vtms_sdr.monitor.curses")
    def test_draw_uses_color_pair_when_colors_available(self, mock_curses):
        """When _has_colors is True, _draw() passes color attributes to addstr."""
        import curses as real_curses

        ui = self._make_ui()
        ui._has_colors = True

        # Make curses.color_pair return distinct nonzero values
        mock_curses.color_pair = lambda n: n * 256
        mock_curses.A_BOLD = real_curses.A_BOLD
        mock_curses.error = real_curses.error

        stdscr = MagicMock()
        stdscr.getmaxyx.return_value = (40, 100)

        ui._draw(stdscr)

        # At least one addstr call should have 4 arguments (row, col, text, attr)
        has_color_arg = any(
            len(c.args) >= 4 and c.args[3] != 0 for c in stdscr.addstr.call_args_list
        )
        assert has_color_arg, (
            "Expected at least one addstr call with a color attribute, "
            f"but got: {[(c.args[:4] if len(c.args) >= 4 else c.args) for c in stdscr.addstr.call_args_list]}"
        )
        assert has_color_arg, (
            "Expected at least one addstr call with a color attribute, "
            f"but got: {[(c.args[:4] if len(c.args) >= 4 else c.args) for c in stdscr.addstr.call_args_list]}"
        )

    def test_draw_works_without_colors(self):
        """When _has_colors is False, _draw() uses no color attributes (3-arg addstr or attr=0)."""
        ui = self._make_ui()
        ui._has_colors = False

        stdscr = MagicMock()
        stdscr.getmaxyx.return_value = (40, 100)

        ui._draw(stdscr)

        # All addstr calls should have at most 3 positional args, or if 4, attr must be 0
        for c in stdscr.addstr.call_args_list:
            if len(c.args) >= 4:
                assert c.args[3] == 0, (
                    f"Expected no color attribute (attr=0) when _has_colors=False, "
                    f"but got addstr({c.args})"
                )


class TestMonitorUIPowerMeter:
    """Tests for the signal power meter bar feature."""

    def _make_ui(self, **kwargs):
        from vtms_sdr.monitor import MonitorUI

        defaults = dict(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-30.0,
            audio_monitor=MagicMock(volume=0.5),
        )
        defaults.update(kwargs)
        return MonitorUI(**defaults)

    def test_format_power_bar_full_signal(self):
        """Power at 0 dB produces all filled blocks."""
        ui = self._make_ui()
        bar = ui._format_power_bar(0.0, width=20)
        assert bar == "\u2588" * 20

    def test_format_power_bar_no_signal(self):
        """Power at -80 dB produces all empty blocks."""
        ui = self._make_ui()
        bar = ui._format_power_bar(-80.0, width=20)
        assert bar == "\u2591" * 20

    def test_format_power_bar_half_signal(self):
        """Power at -40 dB produces approximately half filled."""
        ui = self._make_ui()
        bar = ui._format_power_bar(-40.0, width=20)
        filled = bar.count("\u2588")
        empty = bar.count("\u2591")
        assert filled == 10
        assert empty == 10

    def test_format_power_bar_width(self):
        """Returned string length equals requested width."""
        ui = self._make_ui()
        for w in [10, 20, 30, 50]:
            bar = ui._format_power_bar(-40.0, width=w)
            assert len(bar) == w, f"Expected length {w}, got {len(bar)}"

    def test_format_power_bar_clamps_above_zero(self):
        """Power at +10 dB clamps to all filled (no overflow)."""
        ui = self._make_ui()
        bar = ui._format_power_bar(10.0, width=20)
        assert bar == "\u2588" * 20
        assert len(bar) == 20

    def test_format_power_bar_clamps_below_minus_80(self):
        """Power at -100 dB clamps to all empty."""
        ui = self._make_ui()
        bar = ui._format_power_bar(-100.0, width=20)
        assert bar == "\u2591" * 20
        assert len(bar) == 20

    def test_draw_shows_power_bar(self):
        """_draw() output contains a 'Signal:' line with block characters (power bar)."""
        ui = self._make_ui()
        ui.update_squelch(True, -20.0)

        stdscr = MagicMock()
        stdscr.getmaxyx.return_value = (40, 100)
        ui._draw(stdscr)

        # Find lines containing "Signal:" and check they have block chars
        signal_lines = [
            str(call.args[2])
            for call in stdscr.addstr.call_args_list
            if len(call.args) >= 3 and "Signal:" in str(call.args[2])
        ]
        assert len(signal_lines) >= 1, (
            "Expected at least one line containing 'Signal:' in drawn output"
        )
        signal_text = " ".join(signal_lines)
        assert "\u2588" in signal_text or "\u2591" in signal_text, (
            f"Expected block characters in Signal line, got: {signal_text}"
        )

    def test_draw_shows_squelch_status_text(self):
        """_draw() still shows OPEN or CLOSED squelch status text."""
        ui = self._make_ui()

        # Test OPEN
        ui.update_squelch(True, -20.0)
        stdscr = MagicMock()
        stdscr.getmaxyx.return_value = (40, 100)
        ui._draw(stdscr)
        drawn_open = " ".join(
            str(call.args[2])
            for call in stdscr.addstr.call_args_list
            if len(call.args) >= 3
        )
        assert "OPEN" in drawn_open

        # Test CLOSED
        ui.update_squelch(False, -50.0)
        stdscr2 = MagicMock()
        stdscr2.getmaxyx.return_value = (40, 100)
        ui._draw(stdscr2)
        drawn_closed = " ".join(
            str(call.args[2])
            for call in stdscr2.addstr.call_args_list
            if len(call.args) >= 3
        )
        assert "CLOSED" in drawn_closed
