"""Tests for vtms_sdr.transcriber with mocked faster-whisper."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from vtms_sdr.demod import AUDIO_SAMPLE_RATE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeSegment:
    """Mimics a faster-whisper Segment namedtuple."""

    def __init__(self, text: str):
        self.text = text


class FakeWhisperModel:
    """Mock WhisperModel that returns canned transcription results."""

    def __init__(
        self,
        model_size_or_path: str,
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.model_size = model_size_or_path
        self.device = device
        self.compute_type = compute_type
        # Configurable response for tests
        self._segments: list[FakeSegment] = [FakeSegment("copy that")]
        self._info = MagicMock(language="en", language_probability=0.98)

    def transcribe(self, audio, language=None, **kwargs):
        return iter(self._segments), self._info


def _make_audio(duration_sec: float = 1.0, amplitude: float = 0.5) -> np.ndarray:
    """Create a synthetic audio block at AUDIO_SAMPLE_RATE."""
    n = int(AUDIO_SAMPLE_RATE * duration_sec)
    t = np.arange(n) / AUDIO_SAMPLE_RATE
    return (amplitude * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)


@pytest.fixture
def mock_faster_whisper():
    """Patch faster-whisper so Transcriber can be imported without it installed."""
    fake_module = MagicMock()
    fake_module.WhisperModel = FakeWhisperModel
    with patch.dict("sys.modules", {"faster_whisper": fake_module}):
        yield fake_module


@pytest.fixture
def mock_scipy():
    """Ensure scipy.signal.resample is available (already a real dep)."""
    # scipy is a real dependency, so this is just a safety net
    pass


# ---------------------------------------------------------------------------
# Tests: detect_model_size / _detect_device
# ---------------------------------------------------------------------------


class TestHardwareDetection:
    def test_detect_model_size_cpu_fallback(self, mock_faster_whisper):
        """Without CUDA, should return 'base'."""
        from vtms_sdr.transcriber import detect_model_size

        with patch.dict("sys.modules", {"torch": None}):
            with patch.dict("sys.modules", {"ctranslate2": None}):
                result = detect_model_size()
                assert result == "base"

    def test_detect_device_cpu_fallback(self, mock_faster_whisper):
        from vtms_sdr.transcriber import _detect_device

        with patch.dict("sys.modules", {"torch": None}):
            with patch.dict("sys.modules", {"ctranslate2": None}):
                result = _detect_device()
                assert result == "cpu"


# ---------------------------------------------------------------------------
# Tests: Transcriber lifecycle
# ---------------------------------------------------------------------------


class TestTranscriberInit:
    def test_creates_with_defaults(self, mock_faster_whisper, tmp_path):
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path)

        assert t.model_size == "base"
        assert t.language == "en"
        assert t.transcription_count == 0
        t.close()

    def test_auto_model_size(self, mock_faster_whisper, tmp_path):
        """model_size='auto' should call detect_model_size."""
        from vtms_sdr.transcriber import Transcriber

        with patch(
            "vtms_sdr.transcriber.detect_model_size", return_value="base"
        ) as mock_detect:
            t = Transcriber(model_size="auto", log_path=tmp_path / "t.log")
            mock_detect.assert_called_once()
            assert t.model_size == "base"
            t.close()

    def test_missing_faster_whisper_raises(self):
        """Should raise RuntimeError with install instructions."""
        from vtms_sdr.transcriber import _check_faster_whisper

        with patch.dict("sys.modules", {"faster_whisper": None}):
            with pytest.raises(RuntimeError, match="faster-whisper"):
                _check_faster_whisper()

    def test_close_writes_remaining_buffer(self, mock_faster_whisper, tmp_path):
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path)

        # Simulate an open squelch with buffered audio
        t.on_squelch_open(time.time())
        t.on_audio_chunk(_make_audio(1.0))
        # Close without on_squelch_close - close() should flush
        t.close()

        content = log_path.read_text()
        assert "copy that" in content
        assert t.transcription_count == 1


# ---------------------------------------------------------------------------
# Tests: Squelch callback flow
# ---------------------------------------------------------------------------


class TestSquelchCallbacks:
    def test_basic_transmission(self, mock_faster_whisper, tmp_path):
        """Open -> audio -> close should produce one transcription."""
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path)

        now = time.time()
        t.on_squelch_open(now)
        t.on_audio_chunk(_make_audio(1.0))
        t.on_squelch_close(now + 1.0)

        assert t.transcription_count == 1

        content = log_path.read_text()
        assert "copy that" in content
        t.close()

    def test_multiple_transmissions(self, mock_faster_whisper, tmp_path):
        """Multiple open/close cycles should produce multiple transcriptions."""
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path)

        now = time.time()
        for i in range(3):
            t.on_squelch_open(now + i * 2)
            t.on_audio_chunk(_make_audio(0.5))
            t.on_squelch_close(now + i * 2 + 1)

        assert t.transcription_count == 3
        t.close()

    def test_short_transmission_skipped(self, mock_faster_whisper, tmp_path):
        """Transmissions < 0.3s should be skipped as squelch noise."""
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path)

        now = time.time()
        t.on_squelch_open(now)
        t.on_audio_chunk(_make_audio(0.1))  # Only 100ms
        t.on_squelch_close(now + 0.1)

        assert t.transcription_count == 0
        t.close()

    def test_audio_chunk_ignored_when_squelch_closed(
        self, mock_faster_whisper, tmp_path
    ):
        """Audio chunks received when squelch is closed should be ignored."""
        from vtms_sdr.transcriber import Transcriber

        t = Transcriber(model_size="base", log_path=tmp_path / "t.log")

        # Send audio without opening squelch
        t.on_audio_chunk(_make_audio(1.0))
        t.on_squelch_close(time.time())

        assert t.transcription_count == 0
        t.close()

    def test_double_squelch_close_no_crash(self, mock_faster_whisper, tmp_path):
        """Calling on_squelch_close twice should not crash."""
        from vtms_sdr.transcriber import Transcriber

        t = Transcriber(model_size="base", log_path=tmp_path / "t.log")

        now = time.time()
        t.on_squelch_open(now)
        t.on_audio_chunk(_make_audio(1.0))
        t.on_squelch_close(now + 1)
        t.on_squelch_close(now + 2)  # Should be a no-op

        assert t.transcription_count == 1
        t.close()


# ---------------------------------------------------------------------------
# Tests: Buffer management
# ---------------------------------------------------------------------------


class TestBufferManagement:
    def test_max_buffer_flush(self, mock_faster_whisper, tmp_path):
        """Buffer exceeding MAX_BUFFER_DURATION should be flushed mid-transmission."""
        from vtms_sdr.transcriber import Transcriber, MAX_BUFFER_DURATION

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path)

        now = time.time()
        t.on_squelch_open(now)

        # Feed enough audio to exceed MAX_BUFFER_DURATION
        chunk_duration = 5.0
        chunks_needed = int(MAX_BUFFER_DURATION / chunk_duration) + 1
        for _ in range(chunks_needed):
            t.on_audio_chunk(_make_audio(chunk_duration))

        # Should have flushed at least once (partial)
        assert t.transcription_count >= 1

        # Verify partial marker in log
        content = log_path.read_text()
        assert "..." in content

        t.on_squelch_close(now + MAX_BUFFER_DURATION + chunk_duration)
        t.close()


# ---------------------------------------------------------------------------
# Tests: Transcription output
# ---------------------------------------------------------------------------


class TestTranscriptionOutput:
    def test_unintelligible_when_empty(self, mock_faster_whisper, tmp_path):
        """When model returns no text, should log (unintelligible)."""
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path)

        # Override the model to return empty segments
        t._model._segments = []

        now = time.time()
        t.on_squelch_open(now)
        t.on_audio_chunk(_make_audio(1.0))
        t.on_squelch_close(now + 1)

        content = log_path.read_text()
        assert "(unintelligible)" in content
        assert t.transcription_count == 1
        t.close()

    def test_timestamp_format(self, mock_faster_whisper, tmp_path):
        """Log lines should be formatted as [HH:MM:SS] text."""
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path)

        now = time.time()
        t.on_squelch_open(now)
        t.on_audio_chunk(_make_audio(1.0))
        t.on_squelch_close(now + 1)

        content = log_path.read_text()
        # Should have [HH:MM:SS] format
        import re

        assert re.search(r"\[\d{2}:\d{2}:\d{2}\]", content)
        t.close()

    def test_log_header(self, mock_faster_whisper, tmp_path):
        """write_log_header should write frequency and modulation info."""
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path)
        t.write_log_header("146.520 MHz", "fm")

        content = log_path.read_text()
        assert "146.520 MHz" in content
        assert "FM" in content
        assert "vtms-sdr" in content
        t.close()

    def test_stdout_only_when_no_log_path(self, mock_faster_whisper, caplog):
        """When log_path is None, should log transcription output."""
        from vtms_sdr.transcriber import Transcriber

        t = Transcriber(model_size="base", log_path=None)

        now = time.time()
        with caplog.at_level("INFO", logger="vtms_sdr.transcriber"):
            t.on_squelch_open(now)
            t.on_audio_chunk(_make_audio(1.0))
            t.on_squelch_close(now + 1)

        assert "copy that" in caplog.text
        assert t.transcription_count == 1
        t.close()

    def test_multiple_segments_joined(self, mock_faster_whisper, tmp_path):
        """Multiple segments from whisper should be space-joined."""
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path)

        # Set model to return multiple segments
        t._model._segments = [
            FakeSegment("box box"),
            FakeSegment("go go go"),
        ]

        now = time.time()
        t.on_squelch_open(now)
        t.on_audio_chunk(_make_audio(2.0))
        t.on_squelch_close(now + 2)

        content = log_path.read_text()
        assert "box box go go go" in content
        t.close()


# ---------------------------------------------------------------------------
# Tests: Recorder integration (transcriber callbacks via AudioRecorder)
# ---------------------------------------------------------------------------


class TestRecorderTranscriberIntegration:
    """Test that AudioRecorder correctly fires transcriber callbacks."""

    def test_recorder_fires_squelch_callbacks(self, mock_faster_whisper, tmp_path):
        """AudioRecorder should call on_squelch_open/close during recording."""
        from vtms_sdr.transcriber import Transcriber
        from vtms_sdr.recorder import AudioRecorder

        log_path = tmp_path / "transcript.log"
        t = Transcriber(model_size="base", log_path=log_path)
        output = tmp_path / "test.wav"

        recorder = AudioRecorder(
            output,
            audio_format="wav",
            squelch_db=-20,
            transcriber=t,
        )

        # Alternate loud and quiet blocks
        def mixed_gen():
            for i in range(6):
                if i < 3:
                    yield (-10.0, _make_audio(0.5, amplitude=0.5))  # Above squelch
                else:
                    yield (-50.0, _make_audio(0.5, amplitude=1e-8))  # Below squelch

        recorder.record(mixed_gen())

        # The 3 loud blocks form one transmission, then squelch closes
        assert t.transcription_count >= 1

        content = log_path.read_text()
        assert "copy that" in content
        t.close()

    def test_recorder_no_transcriber(self, tmp_path):
        """Recording without transcriber should work as before."""
        from vtms_sdr.recorder import AudioRecorder

        output = tmp_path / "test.wav"
        recorder = AudioRecorder(
            output,
            audio_format="wav",
            squelch_db=-100,
        )

        def gen():
            for _ in range(3):
                yield (-10.0, _make_audio(0.2))

        stats = recorder.record(gen())
        assert stats["samples_written"] > 0

    def test_recorder_flushes_on_stop(self, mock_faster_whisper, tmp_path):
        """If recording stops while squelch is open, transcriber should flush."""
        from vtms_sdr.transcriber import Transcriber
        from vtms_sdr.recorder import AudioRecorder

        log_path = tmp_path / "transcript.log"
        t = Transcriber(model_size="base", log_path=log_path)
        output = tmp_path / "test.wav"

        recorder = AudioRecorder(
            output,
            audio_format="wav",
            squelch_db=-100,
            transcriber=t,
        )

        # All blocks are loud, then generator ends (simulates Ctrl+C)
        def gen():
            for _ in range(5):
                yield (-10.0, _make_audio(0.5, amplitude=0.5))

        recorder.record(gen())

        # Should have flushed the remaining buffer
        assert t.transcription_count >= 1
        t.close()


# ---------------------------------------------------------------------------
# Tests: Transcriber resilience (whisper failure recovery)
# ---------------------------------------------------------------------------


class CrashingWhisperModel:
    """Fake WhisperModel that raises on transcribe() calls."""

    def __init__(
        self,
        model_size_or_path: str,
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.model_size = model_size_or_path
        self.call_count = 0
        self.fail_until = 999  # Fail all calls by default

    def transcribe(self, audio, language=None, **kwargs):
        self.call_count += 1
        if self.call_count <= self.fail_until:
            raise RuntimeError("CUDA out of memory")
        return iter([FakeSegment("recovered")]), MagicMock()


class TestTranscriberResilience:
    """Transcription failures must not kill the recording."""

    def test_whisper_exception_does_not_crash(self, mock_faster_whisper, tmp_path):
        """A RuntimeError from whisper should be caught, not propagated."""
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path)

        # Replace model with one that always crashes
        t._model = CrashingWhisperModel("base")

        now = time.time()
        # This should NOT raise
        t.on_squelch_open(now)
        t.on_audio_chunk(_make_audio(1.0))
        t.on_squelch_close(now + 1)

        # Recording survived — transcription count may be 0 or 1
        # depending on whether we count failed attempts
        t.close()

    def test_whisper_exception_logged_as_error(
        self, mock_faster_whisper, tmp_path, caplog
    ):
        """When whisper crashes, an error message should appear in logs."""
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path)
        t._model = CrashingWhisperModel("base")

        now = time.time()
        with caplog.at_level("ERROR", logger="vtms_sdr.transcriber"):
            t.on_squelch_open(now)
            t.on_audio_chunk(_make_audio(1.0))
            t.on_squelch_close(now + 1)

        assert "error" in caplog.text.lower() or "failed" in caplog.text.lower()
        t.close()

    def test_whisper_recovers_after_failure(self, mock_faster_whisper, tmp_path):
        """After a failed transcription, the next one should still work."""
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path)

        # Fail on first call, succeed on second
        crashing_model = CrashingWhisperModel("base")
        crashing_model.fail_until = 1  # Only first call fails
        t._model = crashing_model

        now = time.time()

        # First transmission — whisper fails
        t.on_squelch_open(now)
        t.on_audio_chunk(_make_audio(1.0))
        t.on_squelch_close(now + 1)

        # Second transmission — whisper should succeed
        t.on_squelch_open(now + 2)
        t.on_audio_chunk(_make_audio(1.0))
        t.on_squelch_close(now + 3)

        content = log_path.read_text()
        assert "recovered" in content
        assert t.transcription_count >= 1
        t.close()

    def test_resample_error_does_not_crash(self, mock_faster_whisper, tmp_path):
        """An error during resampling should also be caught."""
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path)

        now = time.time()
        t.on_squelch_open(now)
        # Feed an empty array that might cause resample issues
        t.on_audio_chunk(np.zeros(0, dtype=np.float32))
        # Also add some real audio so it's not skipped for being too short
        t.on_audio_chunk(_make_audio(0.5))
        t.on_squelch_close(now + 1)

        # Should not have crashed
        t.close()

    def test_transcription_count_excludes_failures(self, mock_faster_whisper, tmp_path):
        """Failed transcriptions should not increment transcription_count."""
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path)
        t._model = CrashingWhisperModel("base")  # Always fails

        now = time.time()
        t.on_squelch_open(now)
        t.on_audio_chunk(_make_audio(1.0))
        t.on_squelch_close(now + 1)

        assert t.transcription_count == 0
        t.close()


# ---------------------------------------------------------------------------
# Tests: Channel labels in transcript output
# ---------------------------------------------------------------------------


class TestChannelLabels:
    """Channel labels should appear in transcript log lines."""

    def test_label_in_log_output(self, mock_faster_whisper, tmp_path):
        """A label should appear in log lines as [LABEL]."""
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path, label="PIT-CREW")

        now = time.time()
        t.on_squelch_open(now)
        t.on_audio_chunk(_make_audio(1.0))
        t.on_squelch_close(now + 1)

        content = log_path.read_text()
        assert "[PIT-CREW]" in content
        assert "copy that" in content
        t.close()

    def test_label_in_stderr_output(self, mock_faster_whisper, caplog):
        """Label should appear in log output."""
        from vtms_sdr.transcriber import Transcriber

        t = Transcriber(model_size="base", log_path=None, label="SPOTTER")

        now = time.time()
        with caplog.at_level("INFO", logger="vtms_sdr.transcriber"):
            t.on_squelch_open(now)
            t.on_audio_chunk(_make_audio(1.0))
            t.on_squelch_close(now + 1)

        assert "[SPOTTER]" in caplog.text
        t.close()

    def test_no_label_no_brackets(self, mock_faster_whisper, tmp_path):
        """Without a label, output should not have empty brackets."""
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path)

        now = time.time()
        t.on_squelch_open(now)
        t.on_audio_chunk(_make_audio(1.0))
        t.on_squelch_close(now + 1)

        content = log_path.read_text()
        # Should NOT have double brackets like [HH:MM:SS] [] text
        assert "[] " not in content
        assert "copy that" in content
        t.close()

    def test_label_in_log_header(self, mock_faster_whisper, tmp_path):
        """write_log_header should include the channel label."""
        from vtms_sdr.transcriber import Transcriber

        log_path = tmp_path / "test.log"
        t = Transcriber(model_size="base", log_path=log_path, label="CAR-48")
        t.write_log_header("460.000 MHz", "fm")

        content = log_path.read_text()
        assert "CAR-48" in content
        t.close()

    def test_label_property(self, mock_faster_whisper, tmp_path):
        """Transcriber should expose the label as a read-only property."""
        from vtms_sdr.transcriber import Transcriber

        t = Transcriber(model_size="base", log_path=None, label="TEST")
        assert t.label == "TEST"
        t.close()

    def test_label_default_none(self, mock_faster_whisper, tmp_path):
        """Label should default to None."""
        from vtms_sdr.transcriber import Transcriber

        t = Transcriber(model_size="base", log_path=None)
        assert t.label is None
        t.close()


class TestTranscriberUICallback:
    """Test ui_callback parameter for forwarding transcriptions."""

    def test_accepts_ui_callback(self, mock_faster_whisper):
        """Transcriber should accept a ui_callback parameter."""
        from vtms_sdr.transcriber import Transcriber

        t = Transcriber(model_size="tiny", ui_callback=lambda ts, lbl, txt: None)
        assert t is not None
        t.close()

    def test_ui_callback_called_on_transcription(self, mock_faster_whisper):
        """ui_callback should be called with (timestamp, label, text)."""
        from vtms_sdr.transcriber import Transcriber

        calls = []
        t = Transcriber(
            model_size="tiny",
            label="PIT",
            ui_callback=lambda ts, lbl, txt: calls.append((ts, lbl, txt)),
        )
        t.on_squelch_open(0.0)
        t.on_audio_chunk(_make_audio(duration_sec=2.0))
        t.on_squelch_close(2.0)
        assert len(calls) == 1
        ts, label, text = calls[0]
        assert label == "PIT"
        assert isinstance(ts, str)
        assert isinstance(text, str)
        t.close()

    def test_ui_callback_not_called_without_text(self, mock_faster_whisper):
        """ui_callback should not be called for very short transmissions."""
        from vtms_sdr.transcriber import Transcriber

        calls = []
        t = Transcriber(
            model_size="tiny",
            ui_callback=lambda ts, lbl, txt: calls.append((ts, lbl, txt)),
        )
        # Very short audio - below 0.3s threshold
        t.on_squelch_open(0.0)
        t.on_audio_chunk(_make_audio(duration_sec=0.1))
        t.on_squelch_close(0.1)
        assert len(calls) == 0
        t.close()


# ---------------------------------------------------------------------------
# Tests: Post-recording transcription (transcribe_file)
# ---------------------------------------------------------------------------


def _make_wav_file(path: Path, duration_sec: float = 2.0) -> Path:
    """Create a valid WAV file with a sine tone for testing."""
    import soundfile as sf

    audio = _make_audio(duration_sec, amplitude=0.5)
    sf.write(str(path), audio, AUDIO_SAMPLE_RATE, subtype="FLOAT")
    return path


class TestTranscribeFile:
    """Tests for the transcribe_file() standalone function."""

    def test_transcribe_wav_file(self, mock_faster_whisper, tmp_path):
        """Should transcribe a WAV file and return text."""
        from vtms_sdr.transcriber import transcribe_file

        wav_path = _make_wav_file(tmp_path / "test.wav")
        result = transcribe_file(wav_path, model_size="base", language="en")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_transcribe_file_writes_log(self, mock_faster_whisper, tmp_path):
        """Should write transcription to a log file when log_path given."""
        from vtms_sdr.transcriber import transcribe_file

        wav_path = _make_wav_file(tmp_path / "test.wav")
        log_path = tmp_path / "transcript.log"

        transcribe_file(wav_path, model_size="base", log_path=log_path)

        assert log_path.exists()
        content = log_path.read_text()
        assert "copy that" in content

    def test_transcribe_file_returns_text(self, mock_faster_whisper, tmp_path):
        """Should return the transcribed text."""
        from vtms_sdr.transcriber import transcribe_file

        wav_path = _make_wav_file(tmp_path / "test.wav")
        result = transcribe_file(wav_path, model_size="base")

        assert "copy that" in result

    def test_transcribe_file_not_found_raises(self, mock_faster_whisper, tmp_path):
        """Should raise FileNotFoundError for missing files."""
        from vtms_sdr.transcriber import transcribe_file

        with pytest.raises(FileNotFoundError):
            transcribe_file(tmp_path / "nonexistent.wav", model_size="base")

    def test_transcribe_file_with_label(self, mock_faster_whisper, tmp_path):
        """Should include label in log output."""
        from vtms_sdr.transcriber import transcribe_file

        wav_path = _make_wav_file(tmp_path / "test.wav")
        log_path = tmp_path / "transcript.log"

        transcribe_file(wav_path, model_size="base", log_path=log_path, label="CH-1")

        content = log_path.read_text()
        assert "CH-1" in content


# ---------------------------------------------------------------------------
# Task 3.1: Model caching for transcribe_file()
# ---------------------------------------------------------------------------


class TestRunWhisper:
    """Tests for the _run_whisper helper that deduplicates transcription logic."""

    def test_run_whisper_returns_segment_texts(self):
        """_run_whisper should call model.transcribe with standard params and return texts."""
        from vtms_sdr.transcriber import _run_whisper

        model = FakeWhisperModel("tiny")
        model._segments = [FakeSegment("hello world"), FakeSegment("copy that")]
        audio = _make_audio(1.0)

        texts = _run_whisper(model, audio, language="en")

        assert texts == ["hello world", "copy that"]

    def test_run_whisper_strips_whitespace(self):
        """_run_whisper should strip leading/trailing whitespace from segment text."""
        from vtms_sdr.transcriber import _run_whisper

        model = FakeWhisperModel("tiny")
        model._segments = [FakeSegment("  padded  "), FakeSegment("")]
        audio = _make_audio(1.0)

        texts = _run_whisper(model, audio, language="en")

        assert texts == ["padded"]

    def test_run_whisper_empty_segments(self):
        """_run_whisper should return empty list when no segments have text."""
        from vtms_sdr.transcriber import _run_whisper

        model = FakeWhisperModel("tiny")
        model._segments = [FakeSegment(""), FakeSegment("   ")]
        audio = _make_audio(1.0)

        texts = _run_whisper(model, audio, language=None)

        assert texts == []

    def test_run_whisper_passes_standard_params(self):
        """_run_whisper should pass beam_size=5, vad_filter=True, temperature tuple, standard vad_parameters."""
        from vtms_sdr.transcriber import _run_whisper

        model = FakeWhisperModel("tiny")
        # Replace transcribe with a spy
        call_kwargs = {}
        original_transcribe = model.transcribe

        def spy_transcribe(audio, **kwargs):
            call_kwargs.update(kwargs)
            return original_transcribe(audio, **kwargs)

        model.transcribe = spy_transcribe
        audio = _make_audio(1.0)

        _run_whisper(model, audio, language="en")

        assert call_kwargs["beam_size"] == 5
        assert call_kwargs["vad_filter"] is True
        assert call_kwargs["vad_parameters"]["min_silence_duration_ms"] == 300
        assert call_kwargs["vad_parameters"]["speech_pad_ms"] == 100
        assert call_kwargs["language"] == "en"
        assert call_kwargs["temperature"] == (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
        assert call_kwargs["initial_prompt"] is None


class TestModelCache:
    """Test Whisper model caching in transcribe_file()."""

    def test_second_call_reuses_model(self, mock_faster_whisper, tmp_path):
        """Calling transcribe_file twice with same model should reuse cached model."""
        from vtms_sdr.transcriber import transcribe_file, _MODEL_CACHE

        _MODEL_CACHE.clear()
        wav = _make_wav_file(tmp_path / "test.wav")
        transcribe_file(wav, model_size="tiny")
        transcribe_file(wav, model_size="tiny")
        assert "tiny" in _MODEL_CACHE

    def test_different_model_creates_new_entry(self, mock_faster_whisper, tmp_path):
        """Different model sizes should get separate cache entries."""
        from vtms_sdr.transcriber import transcribe_file, _MODEL_CACHE

        _MODEL_CACHE.clear()
        wav = _make_wav_file(tmp_path / "test.wav")
        transcribe_file(wav, model_size="tiny")
        transcribe_file(wav, model_size="base")
        assert "tiny" in _MODEL_CACHE
        assert "base" in _MODEL_CACHE

    def test_clear_model_cache(self, mock_faster_whisper, tmp_path):
        """clear_model_cache() should empty the cache."""
        from vtms_sdr.transcriber import (
            transcribe_file,
            clear_model_cache,
            _MODEL_CACHE,
        )

        wav = _make_wav_file(tmp_path / "test.wav")
        transcribe_file(wav, model_size="tiny")
        assert len(_MODEL_CACHE) > 0
        clear_model_cache()
        assert len(_MODEL_CACHE) == 0


# ---------------------------------------------------------------------------
# Tests: _run_whisper updated params (B3)
# ---------------------------------------------------------------------------


class TestRunWhisperUpdated:
    """Tests for updated _run_whisper with initial_prompt, beam_size=5, temperature."""

    def test_run_whisper_passes_beam_size_5(self):
        """_run_whisper should pass beam_size=5 to model.transcribe."""
        from vtms_sdr.transcriber import _run_whisper

        model = FakeWhisperModel("tiny")
        call_kwargs = {}
        original_transcribe = model.transcribe

        def spy_transcribe(audio, **kwargs):
            call_kwargs.update(kwargs)
            return original_transcribe(audio, **kwargs)

        model.transcribe = spy_transcribe
        _run_whisper(model, _make_audio(1.0), language="en")

        assert call_kwargs["beam_size"] == 5

    def test_run_whisper_passes_temperature_tuple(self):
        """_run_whisper should pass temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0)."""
        from vtms_sdr.transcriber import _run_whisper

        model = FakeWhisperModel("tiny")
        call_kwargs = {}
        original_transcribe = model.transcribe

        def spy_transcribe(audio, **kwargs):
            call_kwargs.update(kwargs)
            return original_transcribe(audio, **kwargs)

        model.transcribe = spy_transcribe
        _run_whisper(model, _make_audio(1.0), language="en")

        assert call_kwargs["temperature"] == (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)

    def test_run_whisper_passes_initial_prompt(self):
        """_run_whisper should forward initial_prompt to model.transcribe."""
        from vtms_sdr.transcriber import _run_whisper

        model = FakeWhisperModel("tiny")
        call_kwargs = {}
        original_transcribe = model.transcribe

        def spy_transcribe(audio, **kwargs):
            call_kwargs.update(kwargs)
            return original_transcribe(audio, **kwargs)

        model.transcribe = spy_transcribe
        _run_whisper(
            model, _make_audio(1.0), language="en", initial_prompt="test prompt"
        )

        assert call_kwargs["initial_prompt"] == "test prompt"

    def test_run_whisper_default_prompt_none(self):
        """When no prompt given, initial_prompt should be None."""
        from vtms_sdr.transcriber import _run_whisper

        model = FakeWhisperModel("tiny")
        call_kwargs = {}
        original_transcribe = model.transcribe

        def spy_transcribe(audio, **kwargs):
            call_kwargs.update(kwargs)
            return original_transcribe(audio, **kwargs)

        model.transcribe = spy_transcribe
        _run_whisper(model, _make_audio(1.0), language="en")

        assert call_kwargs["initial_prompt"] is None


# ---------------------------------------------------------------------------
# Tests: MOTORSPORT_PROMPT constant (B4)
# ---------------------------------------------------------------------------


class TestMotorsportPrompt:
    """Tests for MOTORSPORT_PROMPT constant and its wiring."""

    def test_motorsport_prompt_constant_exists(self):
        """MOTORSPORT_PROMPT should exist and contain key motorsport terms."""
        from vtms_sdr.transcriber import MOTORSPORT_PROMPT

        assert isinstance(MOTORSPORT_PROMPT, str)
        assert "box box" in MOTORSPORT_PROMPT
        assert "pit" in MOTORSPORT_PROMPT
        assert "caution" in MOTORSPORT_PROMPT
        assert "DRS" in MOTORSPORT_PROMPT

    def test_motorsport_prompt_in_all(self):
        """MOTORSPORT_PROMPT should be exported in __all__."""
        from vtms_sdr import transcriber

        assert "MOTORSPORT_PROMPT" in transcriber.__all__

    def test_transcriber_uses_motorsport_prompt(self, mock_faster_whisper):
        """Transcriber._transcribe() should pass MOTORSPORT_PROMPT to _run_whisper."""
        from vtms_sdr.transcriber import Transcriber, MOTORSPORT_PROMPT

        t = Transcriber(model_size="base")

        call_kwargs = {}
        original_transcribe = t._model.transcribe

        def spy_transcribe(audio, **kwargs):
            call_kwargs.update(kwargs)
            return original_transcribe(audio, **kwargs)

        t._model.transcribe = spy_transcribe

        t.on_squelch_open(0.0)
        t.on_audio_chunk(_make_audio(1.0))
        t.on_squelch_close(1.0)

        assert call_kwargs.get("initial_prompt") == MOTORSPORT_PROMPT
        t.close()

    def test_transcribe_file_uses_motorsport_prompt(
        self, mock_faster_whisper, tmp_path
    ):
        """transcribe_file() should pass MOTORSPORT_PROMPT to _run_whisper."""
        from vtms_sdr.transcriber import (
            transcribe_file,
            MOTORSPORT_PROMPT,
            _MODEL_CACHE,
        )

        _MODEL_CACHE.clear()

        wav_path = _make_wav_file(tmp_path / "test.wav")

        call_kwargs = {}

        # We need to spy on the model that gets created
        original_fake_transcribe = FakeWhisperModel.transcribe

        def spy_transcribe(self_model, audio, **kwargs):
            call_kwargs.update(kwargs)
            return original_fake_transcribe(self_model, audio, **kwargs)

        with patch.object(FakeWhisperModel, "transcribe", spy_transcribe):
            transcribe_file(wav_path, model_size="base")

        assert call_kwargs.get("initial_prompt") == MOTORSPORT_PROMPT


# ---------------------------------------------------------------------------
# Tests: Custom prompt override (B5)
# ---------------------------------------------------------------------------


class TestCustomPrompt:
    """Tests for --prompt flag support in Transcriber and transcribe_file."""

    def test_transcriber_uses_custom_prompt(self, mock_faster_whisper):
        """Transcriber with prompt='Custom prompt' should pass it to _run_whisper."""
        from vtms_sdr.transcriber import Transcriber, MOTORSPORT_PROMPT

        t = Transcriber(model_size="base", prompt="Custom prompt")

        call_kwargs = {}
        original_transcribe = t._model.transcribe

        def spy_transcribe(audio, **kwargs):
            call_kwargs.update(kwargs)
            return original_transcribe(audio, **kwargs)

        t._model.transcribe = spy_transcribe

        t.on_squelch_open(0.0)
        t.on_audio_chunk(_make_audio(1.0))
        t.on_squelch_close(1.0)

        assert call_kwargs.get("initial_prompt") == "Custom prompt"
        t.close()

    def test_transcriber_uses_motorsport_prompt_by_default(self, mock_faster_whisper):
        """Transcriber without prompt param should use MOTORSPORT_PROMPT."""
        from vtms_sdr.transcriber import Transcriber, MOTORSPORT_PROMPT

        t = Transcriber(model_size="base")

        call_kwargs = {}
        original_transcribe = t._model.transcribe

        def spy_transcribe(audio, **kwargs):
            call_kwargs.update(kwargs)
            return original_transcribe(audio, **kwargs)

        t._model.transcribe = spy_transcribe

        t.on_squelch_open(0.0)
        t.on_audio_chunk(_make_audio(1.0))
        t.on_squelch_close(1.0)

        assert call_kwargs.get("initial_prompt") == MOTORSPORT_PROMPT
        t.close()

    def test_transcribe_file_uses_custom_prompt(self, mock_faster_whisper, tmp_path):
        """transcribe_file() with prompt='Custom' should pass it to _run_whisper."""
        from vtms_sdr.transcriber import (
            transcribe_file,
            MOTORSPORT_PROMPT,
            _MODEL_CACHE,
        )

        _MODEL_CACHE.clear()
        wav_path = _make_wav_file(tmp_path / "test.wav")

        call_kwargs = {}
        original_fake_transcribe = FakeWhisperModel.transcribe

        def spy_transcribe(self_model, audio, **kwargs):
            call_kwargs.update(kwargs)
            return original_fake_transcribe(self_model, audio, **kwargs)

        with patch.object(FakeWhisperModel, "transcribe", spy_transcribe):
            transcribe_file(wav_path, model_size="base", prompt="Custom")

        assert call_kwargs.get("initial_prompt") == "Custom"

    def test_transcribe_file_uses_motorsport_prompt_by_default(
        self, mock_faster_whisper, tmp_path
    ):
        """transcribe_file() without prompt should use MOTORSPORT_PROMPT."""
        from vtms_sdr.transcriber import (
            transcribe_file,
            MOTORSPORT_PROMPT,
            _MODEL_CACHE,
        )

        _MODEL_CACHE.clear()
        wav_path = _make_wav_file(tmp_path / "test.wav")

        call_kwargs = {}
        original_fake_transcribe = FakeWhisperModel.transcribe

        def spy_transcribe(self_model, audio, **kwargs):
            call_kwargs.update(kwargs)
            return original_fake_transcribe(self_model, audio, **kwargs)

        with patch.object(FakeWhisperModel, "transcribe", spy_transcribe):
            transcribe_file(wav_path, model_size="base")

        assert call_kwargs.get("initial_prompt") == MOTORSPORT_PROMPT


# ---------------------------------------------------------------------------
# Tests: _preprocess_for_whisper (B2)
# ---------------------------------------------------------------------------


class TestPreprocessForWhisper:
    """Tests for the _preprocess_for_whisper audio preprocessing pipeline."""

    def test_preprocess_returns_16khz(self):
        """Output length should match 16kHz for given input duration."""
        from vtms_sdr.transcriber import _preprocess_for_whisper

        duration = 1.0
        audio = _make_audio(duration)
        result = _preprocess_for_whisper(audio, AUDIO_SAMPLE_RATE)

        # Expected samples at 16kHz for the given duration
        expected_samples = int(duration * 16000)
        # Allow small tolerance for resampling rounding
        assert abs(len(result) - expected_samples) <= 2

    def test_preprocess_returns_float32(self):
        """Output dtype must be float32."""
        from vtms_sdr.transcriber import _preprocess_for_whisper

        audio = _make_audio(1.0)
        result = _preprocess_for_whisper(audio, AUDIO_SAMPLE_RATE)

        assert result.dtype == np.float32

    def test_preprocess_normalizes_peak(self):
        """Max absolute value of output should be ~1.0 for non-silent input."""
        from vtms_sdr.transcriber import _preprocess_for_whisper

        # Use low amplitude input to verify normalization scales it up
        audio = _make_audio(1.0, amplitude=0.1)
        result = _preprocess_for_whisper(audio, AUDIO_SAMPLE_RATE)

        peak = np.max(np.abs(result))
        # Resampling can cause slight overshoot, allow small tolerance
        assert 0.9 <= peak <= 1.05

    def test_preprocess_handles_silence(self):
        """All-zeros input should not crash (no divide-by-zero)."""
        from vtms_sdr.transcriber import _preprocess_for_whisper

        silence = np.zeros(48000, dtype=np.float32)
        result = _preprocess_for_whisper(silence, AUDIO_SAMPLE_RATE)

        # Should return all zeros, not NaN or Inf
        assert not np.any(np.isnan(result))
        assert not np.any(np.isinf(result))
        assert np.max(np.abs(result)) == 0.0

    def test_preprocess_bandpass_removes_dc(self):
        """DC offset (constant signal) should be removed by bandpass filter."""
        from vtms_sdr.transcriber import _preprocess_for_whisper

        # Create audio with a DC offset (constant value) — long signal
        # so the filter transient is a tiny fraction of total
        dc_signal = np.ones(48000 * 3, dtype=np.float32) * 0.5
        result = _preprocess_for_whisper(dc_signal, AUDIO_SAMPLE_RATE)

        # After bandpass filtering, DC should be gone — RMS should be very low
        # (normalization may amplify the tiny filter transient, but RMS stays low)
        rms = np.sqrt(np.mean(result**2))
        assert rms < 0.1

    def test_preprocess_noisereduce_fallback(self):
        """When noisereduce not installed, should still work (skip noise reduction)."""
        audio = _make_audio(1.0)

        # Temporarily make noisereduce unavailable
        with patch.dict("sys.modules", {"noisereduce": None}):
            # Reload module so module-level import re-runs and sees the block
            import importlib
            import vtms_sdr.transcriber as mod

            importlib.reload(mod)
            assert not mod._NOISEREDUCE_AVAILABLE
            result = mod._preprocess_for_whisper(audio, AUDIO_SAMPLE_RATE)

            assert result.dtype == np.float32
            assert len(result) > 0

        # Reload again to restore normal state
        importlib.reload(mod)
        assert mod._NOISEREDUCE_AVAILABLE


# ---------------------------------------------------------------------------
# Tests: Preprocessing integration (B2 wiring)
# ---------------------------------------------------------------------------


class TestPreprocessingIntegration:
    """Verify _preprocess_for_whisper is wired into _transcribe and transcribe_file."""

    def test_transcriber_preprocesses_audio(self, mock_faster_whisper):
        """Transcriber._transcribe() should call _preprocess_for_whisper."""
        from vtms_sdr.transcriber import Transcriber

        t = Transcriber(model_size="base")

        with patch(
            "vtms_sdr.transcriber._preprocess_for_whisper",
            wraps=__import__(
                "vtms_sdr.transcriber", fromlist=["_preprocess_for_whisper"]
            )._preprocess_for_whisper,
        ) as mock_preprocess:
            t.on_squelch_open(0.0)
            t.on_audio_chunk(_make_audio(1.0))
            t.on_squelch_close(1.0)

            mock_preprocess.assert_called_once()
            # Verify it was called with the right sample rate
            args, kwargs = mock_preprocess.call_args
            assert args[1] == AUDIO_SAMPLE_RATE

        t.close()

    def test_transcribe_file_preprocesses_audio(self, mock_faster_whisper, tmp_path):
        """transcribe_file() should call _preprocess_for_whisper."""
        from vtms_sdr.transcriber import transcribe_file, _MODEL_CACHE

        _MODEL_CACHE.clear()
        wav_path = _make_wav_file(tmp_path / "test.wav")

        with patch(
            "vtms_sdr.transcriber._preprocess_for_whisper",
            wraps=__import__(
                "vtms_sdr.transcriber", fromlist=["_preprocess_for_whisper"]
            )._preprocess_for_whisper,
        ) as mock_preprocess:
            transcribe_file(wav_path, model_size="base")

            mock_preprocess.assert_called_once()
            # Verify it was called with the file's sample rate
            args, kwargs = mock_preprocess.call_args
            assert args[1] == AUDIO_SAMPLE_RATE
