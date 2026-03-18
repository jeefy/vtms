"""Tests for vtms_sdr.recorder with real file I/O."""

import numpy as np
import pytest
import tempfile
from pathlib import Path

from vtms_sdr.recorder import AudioRecorder
from vtms_sdr.demod import AUDIO_SAMPLE_RATE


def make_audio_generator(
    num_blocks=5, block_size=4800, amplitude=0.5, iq_power_db=-10.0
):
    """Generate synthetic audio blocks (1kHz sine wave) with IQ power."""
    sample_rate = AUDIO_SAMPLE_RATE
    t_offset = 0
    for _ in range(num_blocks):
        t = np.arange(t_offset, t_offset + block_size) / sample_rate
        audio = (amplitude * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
        t_offset += block_size
        yield (iq_power_db, audio)


def make_silent_generator(num_blocks=5, block_size=4800):
    """Generate silent (near-zero) audio blocks with low IQ power."""
    for _ in range(num_blocks):
        audio = (np.random.randn(block_size) * 1e-8).astype(np.float32)
        yield (-50.0, audio)


def make_mixed_generator(loud_blocks=3, quiet_blocks=3, block_size=4800):
    """Generate alternating loud and quiet blocks."""
    sample_rate = AUDIO_SAMPLE_RATE
    t_offset = 0

    for i in range(loud_blocks + quiet_blocks):
        t = np.arange(t_offset, t_offset + block_size) / sample_rate
        if i < loud_blocks:
            audio = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
            yield (-10.0, audio)
        else:
            audio = (np.random.randn(block_size) * 1e-8).astype(np.float32)
            yield (-50.0, audio)
        t_offset += block_size


class TestAudioRecorderWav:
    def test_records_wav_file(self, tmp_path):
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, audio_format="wav", squelch_db=-100)
        stats = recorder.record(make_audio_generator())

        assert output.exists()
        assert stats["format"] == "wav"
        assert stats["samples_written"] > 0
        assert stats["file_size_bytes"] > 0
        assert stats["audio_duration_sec"] > 0

    def test_wav_file_is_valid(self, tmp_path):
        """Verify the WAV file can be read back."""
        import soundfile as sf

        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, audio_format="wav", squelch_db=-100)
        recorder.record(make_audio_generator(num_blocks=3, block_size=4800))

        data, sample_rate = sf.read(str(output))
        assert sample_rate == AUDIO_SAMPLE_RATE
        assert len(data) == 3 * 4800
        assert data.dtype == np.float64 or data.dtype == np.float32

    def test_adds_wav_extension(self, tmp_path):
        output = tmp_path / "test"
        recorder = AudioRecorder(output, audio_format="wav", squelch_db=-100)
        stats = recorder.record(make_audio_generator(num_blocks=1))

        assert Path(stats["file"]).suffix == ".wav"

    def test_duration_limit(self, tmp_path):
        """Recording should stop after duration limit."""
        import time

        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, audio_format="wav", squelch_db=-100)

        def slow_generator():
            """Yield blocks with a small delay to simulate real-time."""
            for block in make_audio_generator(num_blocks=100, block_size=4800):
                time.sleep(0.02)  # 20ms per block
                yield block

        stats = recorder.record(slow_generator(), duration=0.1)

        # Should have stopped well before all 100 blocks
        assert stats["audio_duration_sec"] < 2.0
        assert stats["samples_written"] < 100 * 4800

    def test_sample_rate_in_stats(self, tmp_path):
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, audio_format="wav", squelch_db=-100)
        stats = recorder.record(make_audio_generator(num_blocks=1))
        assert stats["sample_rate"] == AUDIO_SAMPLE_RATE


class TestAudioRecorderSquelch:
    def test_squelch_blocks_silence(self, tmp_path):
        """Silent audio should not be written when squelch is active."""
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, audio_format="wav", squelch_db=-20)
        stats = recorder.record(make_silent_generator())

        assert stats["samples_written"] == 0

    def test_squelch_passes_loud_signal(self, tmp_path):
        """Loud audio should pass through squelch."""
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, audio_format="wav", squelch_db=-40)
        stats = recorder.record(make_audio_generator(amplitude=0.5))

        assert stats["samples_written"] > 0

    def test_squelch_disabled(self, tmp_path):
        """With squelch at -100, everything should be recorded."""
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, audio_format="wav", squelch_db=-100)
        stats = recorder.record(make_silent_generator(num_blocks=3, block_size=4800))

        assert stats["samples_written"] == 3 * 4800

    def test_squelch_mixed_signal(self, tmp_path):
        """Only loud blocks should be recorded with squelch active."""
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, audio_format="wav", squelch_db=-20)
        stats = recorder.record(make_mixed_generator(loud_blocks=3, quiet_blocks=3))

        # Should have recorded roughly 3 blocks worth
        expected_samples = 3 * 4800
        assert stats["samples_written"] == expected_samples


class TestAudioRecorderValidation:
    def test_invalid_format_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported format"):
            AudioRecorder(tmp_path / "test.ogg", audio_format="ogg")

    def test_mp3_format_raises(self, tmp_path):
        """MP3 is no longer supported."""
        with pytest.raises(ValueError, match="Unsupported format"):
            AudioRecorder(tmp_path / "test.mp3", audio_format="mp3")

    def test_empty_recording(self, tmp_path):
        """Recording with zero blocks should create a valid but empty file."""
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, audio_format="wav", squelch_db=-100)

        def empty_gen():
            return
            yield  # Make it a generator

        stats = recorder.record(empty_gen())
        assert stats["samples_written"] == 0


class TestAudioRecorderIsAboveSquelch:
    def test_strong_signal_above_squelch(self):
        recorder = AudioRecorder("/dev/null", squelch_db=-20)
        assert recorder._is_above_squelch(-10.0) is True

    def test_weak_signal_below_squelch(self):
        recorder = AudioRecorder("/dev/null", squelch_db=-20)
        assert recorder._is_above_squelch(-30.0) is False

    def test_squelch_disabled_always_true(self):
        recorder = AudioRecorder("/dev/null", squelch_db=-100)
        assert recorder._is_above_squelch(-50.0) is True


class TestAudioRecorderProgressCallback:
    """Test progress_callback parameter on record()."""

    def test_accepts_progress_callback(self, tmp_path):
        """record() should accept a progress_callback kwarg."""
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, audio_format="wav", squelch_db=-100)
        calls = []
        stats = recorder.record(
            make_audio_generator(num_blocks=3, block_size=4800),
            progress_callback=lambda e, s, r: calls.append((e, s, r)),
        )
        assert len(calls) > 0

    def test_progress_callback_receives_data(self, tmp_path):
        """progress_callback should receive (elapsed, samples_written, sample_rate)."""
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, audio_format="wav", squelch_db=-100)
        calls = []
        stats = recorder.record(
            make_audio_generator(num_blocks=3, block_size=4800),
            progress_callback=lambda e, s, r: calls.append((e, s, r)),
        )
        elapsed, samples, rate = calls[-1]
        assert elapsed > 0
        assert samples > 0
        assert rate == AUDIO_SAMPLE_RATE

    def test_no_stderr_when_callback_provided(self, tmp_path, capsys):
        """_print_progress should not write to stderr when callback provided."""
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, audio_format="wav", squelch_db=-100)
        recorder.record(
            make_audio_generator(num_blocks=2, block_size=4800),
            progress_callback=lambda e, s, r: None,
        )
        captured = capsys.readouterr()
        assert "Recording:" not in captured.err


class TestAudioRecorderSquelchCallback:
    """Test squelch_callback parameter."""

    def test_accepts_squelch_callback(self, tmp_path):
        """Constructor should accept squelch_callback."""
        output = tmp_path / "test.wav"
        calls = []
        recorder = AudioRecorder(
            output,
            audio_format="wav",
            squelch_callback=lambda is_open, power: calls.append((is_open, power)),
        )
        assert recorder is not None

    def test_squelch_callback_receives_state(self, tmp_path):
        """squelch_callback should be called with (is_open, power_db)."""
        output = tmp_path / "test.wav"
        calls = []
        recorder = AudioRecorder(
            output,
            audio_format="wav",
            squelch_db=-30.0,
            squelch_callback=lambda is_open, power: calls.append((is_open, power)),
        )
        recorder.record(make_audio_generator(num_blocks=3, iq_power_db=-10.0))
        assert len(calls) > 0
        is_open, power_db = calls[-1]
        assert isinstance(is_open, bool)
        assert isinstance(power_db, float)

    def test_squelch_callback_reflects_signal_state(self, tmp_path):
        """Loud signal should produce squelch_open=True, quiet should produce False."""
        output = tmp_path / "test.wav"
        calls = []
        recorder = AudioRecorder(
            output,
            audio_format="wav",
            squelch_db=-30.0,
            squelch_callback=lambda is_open, power: calls.append((is_open, power)),
        )
        recorder.record(make_mixed_generator(loud_blocks=3, quiet_blocks=3))
        opens = [c for c in calls if c[0] is True]
        closes = [c for c in calls if c[0] is False]
        assert len(opens) > 0
        assert len(closes) > 0


class TestAudioRecorderMonitor:
    """Test audio_monitor integration in AudioRecorder."""

    def test_accepts_audio_monitor_param(self, tmp_path):
        """AudioRecorder should accept an audio_monitor parameter."""
        from unittest.mock import MagicMock

        monitor = MagicMock()
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(
            output, audio_format="wav", squelch_db=-100, audio_monitor=monitor
        )
        assert recorder._audio_monitor is monitor

    def test_monitor_none_by_default(self, tmp_path):
        """audio_monitor should default to None."""
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, audio_format="wav")
        assert recorder._audio_monitor is None

    def test_monitor_receives_audio_above_squelch(self, tmp_path):
        """Monitor should receive audio blocks that pass squelch."""
        from unittest.mock import MagicMock

        monitor = MagicMock()
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(
            output, audio_format="wav", squelch_db=-100, audio_monitor=monitor
        )
        recorder.record(make_audio_generator(num_blocks=3, block_size=4800))

        assert monitor.feed.call_count == 3

    def test_monitor_not_called_below_squelch(self, tmp_path):
        """Monitor should NOT receive audio blocks below squelch."""
        from unittest.mock import MagicMock

        monitor = MagicMock()
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(
            output, audio_format="wav", squelch_db=-20, audio_monitor=monitor
        )
        recorder.record(make_silent_generator(num_blocks=3))

        monitor.feed.assert_not_called()

    def test_monitor_only_receives_loud_blocks(self, tmp_path):
        """With mixed audio, monitor should only get blocks above squelch."""
        from unittest.mock import MagicMock

        monitor = MagicMock()
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(
            output, audio_format="wav", squelch_db=-20, audio_monitor=monitor
        )
        recorder.record(make_mixed_generator(loud_blocks=3, quiet_blocks=3))

        assert monitor.feed.call_count == 3

    def test_monitor_receives_same_audio_as_file(self, tmp_path):
        """Monitor should receive the same audio blocks written to file."""
        from unittest.mock import MagicMock
        import soundfile as sf

        monitor = MagicMock()
        output = tmp_path / "test.wav"
        recorder = AudioRecorder(
            output, audio_format="wav", squelch_db=-100, audio_monitor=monitor
        )
        recorder.record(make_audio_generator(num_blocks=2, block_size=4800))

        # Reconstruct audio from monitor.feed calls
        fed_blocks = [call.args[0] for call in monitor.feed.call_args_list]
        fed_audio = np.concatenate(fed_blocks)

        # Read back from file
        file_audio, _ = sf.read(str(output))

        np.testing.assert_array_almost_equal(fed_audio, file_audio, decimal=5)


class TestRecorderStoppedEvent:
    """Verify _stopped is a threading.Event for thread-safe shutdown signaling."""

    def test_stopped_is_threading_event(self, tmp_path):
        """_stopped should be a threading.Event instance, not a bool."""
        import threading

        recorder = AudioRecorder(tmp_path / "test.wav", squelch_db=-100)
        assert isinstance(recorder._stopped, threading.Event)

    def test_stopped_initially_not_set(self, tmp_path):
        """_stopped should not be set after construction."""
        recorder = AudioRecorder(tmp_path / "test.wav", squelch_db=-100)
        assert not recorder._stopped.is_set()

    def test_stopped_cleared_on_record_start(self, tmp_path):
        """_stopped should be cleared when record() begins."""
        import threading

        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, squelch_db=-100)

        # Pre-set the event to simulate a previous stop
        recorder._stopped.set()
        assert recorder._stopped.is_set()

        # Record with a tiny generator — _stopped should be cleared at entry
        recorder.record(make_audio_generator(num_blocks=1, block_size=480))
        # After record returns, _stopped was cleared at entry (we can't
        # observe mid-call easily, but we verify by checking it wasn't
        # still set during recording — the generator would have been
        # consumed, which only happens if _stopped was cleared).
        # The file should have audio written (proof the loop ran).
        import soundfile as sf

        info = sf.info(str(output))
        assert info.frames > 0

    def test_stopped_set_stops_recording(self, tmp_path):
        """Calling _stopped.set() mid-recording should stop the loop."""
        import threading

        output = tmp_path / "test.wav"
        recorder = AudioRecorder(output, squelch_db=-100)

        blocks_yielded = 0

        def stopping_generator():
            nonlocal blocks_yielded
            for iq_power, audio_block in make_audio_generator(
                num_blocks=100, block_size=4800
            ):
                blocks_yielded += 1
                yield (iq_power, audio_block)
                # After yielding 3 blocks, signal stop
                if blocks_yielded >= 3:
                    recorder._stopped.set()

        recorder.record(stopping_generator())
        # Should have stopped well before 100 blocks
        assert blocks_yielded <= 5  # 3 yielded + at most a couple more

    def test_sigint_handler_sets_stopped_event(self, tmp_path):
        """The SIGINT handler installed by _install_signal_handler should call _stopped.set()."""
        import signal
        import threading

        recorder = AudioRecorder(tmp_path / "test.wav", squelch_db=-100)

        # Only works from main thread — skip otherwise
        if threading.current_thread() is not threading.main_thread():
            pytest.skip("Must run from main thread")

        original = signal.getsignal(signal.SIGINT)
        try:
            recorder._install_signal_handler()
            handler = signal.getsignal(signal.SIGINT)

            # The handler should set the _stopped event
            assert not recorder._stopped.is_set()
            handler(signal.SIGINT, None)
            assert recorder._stopped.is_set()
        finally:
            signal.signal(signal.SIGINT, original)
