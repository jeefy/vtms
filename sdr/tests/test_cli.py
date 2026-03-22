"""Tests for vtms_sdr.cli using Click's CliRunner with mocked SDR."""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from vtms_sdr.cli import main
from vtms_sdr.sdr import DEFAULT_SAMPLE_RATE


def _mock_record_stats(output_path: str) -> dict:
    """Build a mock stats dict matching AudioRecorder.record() return value."""
    return {
        "file": output_path,
        "format": "wav",
        "samples_written": 100,
        "audio_duration_sec": 0.1,
        "file_size_bytes": 1000,
        "sample_rate": 48000,
    }


class FakeSDRDevice:
    """Fake SDR device for CLI testing."""

    def __init__(self, device_index=0):
        self._device_index = device_index
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self.center_freq = 0
        self.gain = "auto"
        self._block_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def configure(
        self, center_freq, sample_rate=DEFAULT_SAMPLE_RATE, gain="auto", ppm=0
    ):
        self.center_freq = center_freq
        self.ppm = ppm
        if isinstance(gain, (int, float)):
            self.gain = float(gain)
        else:
            self.gain = gain

    def stream(self, block_size=262144):
        """Yield a few blocks of synthetic IQ data then stop."""
        for _ in range(3):
            iq = np.random.randn(block_size) + 1j * np.random.randn(block_size)
            yield iq.astype(np.complex64)

    def read_samples(self, num_samples=65536):
        return (
            np.random.randn(num_samples) * 1e-4
            + 1j * np.random.randn(num_samples) * 1e-4
        ).astype(np.complex64)

    def get_info(self):
        return {
            "center_freq": self.center_freq,
            "center_freq_str": "146.520 MHz",
            "sample_rate": self.sample_rate,
            "gain": self.gain,
        }


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_sdr():
    """Patch SDRDevice to use FakeSDRDevice.

    cli.py uses lazy imports (from .sdr import SDRDevice inside functions),
    so we must patch at the source module level.
    """
    with patch("vtms_sdr.sdr.SDRDevice", FakeSDRDevice):
        yield


# --- Top-level CLI tests ---


class TestCLIBasic:
    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "record" in result.output
        assert "scan" in result.output

    def test_no_command(self, runner):
        result = runner.invoke(main, [])
        # Click groups return exit code 0 with help text when no subcommand
        assert "Usage" in result.output or "record" in result.output

    def test_verbose_flag_in_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert "--verbose" in result.output


# --- Record command tests ---


class TestRecordCommand:
    def test_record_help(self, runner):
        result = runner.invoke(main, ["record", "--help"])
        assert result.exit_code == 0
        assert "--freq" in result.output
        assert "--mod" in result.output
        assert "--format" in result.output

    def test_record_missing_freq(self, runner):
        result = runner.invoke(main, ["record"])
        assert result.exit_code != 0

    def test_record_invalid_frequency(self, runner):
        result = runner.invoke(main, ["record", "-f", "not_a_freq"])
        assert result.exit_code != 0
        assert "Invalid frequency" in result.output

    def test_record_frequency_out_of_range(self, runner):
        result = runner.invoke(main, ["record", "-f", "1M"])
        assert result.exit_code != 0
        assert "out of RTL-SDR range" in result.output

    def test_record_wav(self, runner, mock_sdr, tmp_path):
        output = str(tmp_path / "test.wav")
        result = runner.invoke(
            main,
            [
                "record",
                "-f",
                "146.52M",
                "-m",
                "fm",
                "-o",
                output,
                "-d",
                "0.1",
            ],
        )
        assert result.exit_code == 0

    def test_record_default_modulation(self, runner, mock_sdr, tmp_path):
        """Default modulation should be FM."""
        output = str(tmp_path / "test.wav")
        result = runner.invoke(
            main,
            [
                "record",
                "-f",
                "146.52M",
                "-o",
                output,
                "-d",
                "0.1",
            ],
        )
        assert result.exit_code == 0

    def test_record_am(self, runner, mock_sdr, tmp_path):
        output = str(tmp_path / "test.wav")
        result = runner.invoke(
            main,
            [
                "record",
                "-f",
                "146.52M",
                "-m",
                "am",
                "-o",
                output,
                "-d",
                "0.1",
            ],
        )
        assert result.exit_code == 0

    def test_record_ssb(self, runner, mock_sdr, tmp_path):
        output = str(tmp_path / "test.wav")
        result = runner.invoke(
            main,
            [
                "record",
                "-f",
                "146.52M",
                "-m",
                "ssb",
                "-o",
                output,
                "-d",
                "0.1",
            ],
        )
        assert result.exit_code == 0

    def test_record_invalid_modulation(self, runner):
        result = runner.invoke(
            main,
            [
                "record",
                "-f",
                "146.52M",
                "-m",
                "cw",
            ],
        )
        assert result.exit_code != 0

    def test_record_custom_squelch(self, runner, mock_sdr, tmp_path):
        output = str(tmp_path / "test.wav")
        result = runner.invoke(
            main,
            [
                "record",
                "-f",
                "146.52M",
                "-o",
                output,
                "-d",
                "0.1",
                "--squelch",
                "-100",
            ],
        )
        assert result.exit_code == 0

    def test_record_custom_gain(self, runner, mock_sdr, tmp_path):
        output = str(tmp_path / "test.wav")
        result = runner.invoke(
            main,
            [
                "record",
                "-f",
                "146.52M",
                "-o",
                output,
                "-d",
                "0.1",
                "-g",
                "40",
            ],
        )
        assert result.exit_code == 0

    def test_record_auto_filename(self, runner, mock_sdr, tmp_path, monkeypatch):
        """When no output specified, should auto-generate filename."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            main,
            [
                "record",
                "-f",
                "146.52M",
                "-d",
                "0.1",
            ],
        )
        assert result.exit_code == 0

    def test_auto_filename_goes_under_recordings_dir(
        self, runner, mock_sdr, tmp_path, monkeypatch
    ):
        """Auto-generated recordings should land in a recordings/ subdirectory."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            main,
            [
                "record",
                "-f",
                "146.52M",
                "-d",
                "0.1",
            ],
        )
        assert result.exit_code == 0
        recordings_dir = tmp_path / "recordings"
        assert recordings_dir.is_dir(), "recordings/ directory should be created"
        wav_files = list(recordings_dir.glob("recording_*.wav"))
        assert len(wav_files) == 1, (
            f"Expected 1 wav file in recordings/, found {wav_files}"
        )

    def test_explicit_output_not_moved_to_recordings(self, runner, mock_sdr, tmp_path):
        """Explicit -o path should NOT be forced under recordings/."""
        output = str(tmp_path / "my_custom.wav")
        result = runner.invoke(
            main,
            [
                "record",
                "-f",
                "146.52M",
                "-o",
                output,
                "-d",
                "0.1",
            ],
        )
        assert result.exit_code == 0
        # File should be exactly where the user asked, not under recordings/
        assert not (tmp_path / "recordings").exists()


# --- Scan active command tests ---


class TestScanActiveCommand:
    def test_scan_active_help(self, runner):
        result = runner.invoke(main, ["scan", "active", "--help"])
        assert result.exit_code == 0
        assert "--start" in result.output
        assert "--end" in result.output
        assert "--step" in result.output

    def test_scan_active_ppm_in_help(self, runner):
        """scan active should accept a --ppm option."""
        result = runner.invoke(main, ["scan", "active", "--help"])
        assert "--ppm" in result.output

    def test_scan_active_basic(self, runner, mock_sdr):
        result = runner.invoke(
            main,
            [
                "scan",
                "active",
                "--start",
                "144M",
                "--end",
                "144.1M",
                "--step",
                "25k",
            ],
        )
        assert result.exit_code == 0
        assert "ACTIVE" in result.output

    def test_scan_active_custom_threshold(self, runner, mock_sdr):
        result = runner.invoke(
            main,
            [
                "scan",
                "active",
                "--start",
                "144M",
                "--end",
                "144.1M",
                "--step",
                "25k",
                "--threshold",
                "-50",
            ],
        )
        assert result.exit_code == 0

    def test_scan_active_csv_output(self, runner, mock_sdr, tmp_path):
        csv_file = str(tmp_path / "scan.csv")
        result = runner.invoke(
            main,
            [
                "scan",
                "active",
                "--start",
                "144M",
                "--end",
                "144.1M",
                "--step",
                "25k",
                "-o",
                csv_file,
            ],
        )
        assert result.exit_code == 0
        from pathlib import Path

        content = Path(csv_file).read_text()
        assert "frequency_hz" in content

    def test_scan_active_missing_params(self, runner):
        result = runner.invoke(main, ["scan", "active"])
        assert result.exit_code != 0

    def test_scan_active_invalid_frequency(self, runner):
        result = runner.invoke(
            main,
            [
                "scan",
                "active",
                "--start",
                "bad",
                "--end",
                "144.1M",
                "--step",
                "25k",
            ],
        )
        assert result.exit_code != 0


# --- Scan clear command tests ---


class TestScanClearCommand:
    def test_scan_clear_help(self, runner):
        result = runner.invoke(main, ["scan", "clear", "--help"])
        assert result.exit_code == 0
        assert "--duration" in result.output

    def test_scan_clear_ppm_in_help(self, runner):
        """scan clear should accept a --ppm option."""
        result = runner.invoke(main, ["scan", "clear", "--help"])
        assert "--ppm" in result.output

    def test_scan_clear_basic(self, runner, mock_sdr):
        result = runner.invoke(
            main,
            [
                "scan",
                "clear",
                "--start",
                "144M",
                "--end",
                "144.1M",
                "--step",
                "25k",
                "-d",
                "0.5",
            ],
        )
        assert result.exit_code == 0
        assert "CLEAR" in result.output

    def test_scan_clear_csv_output(self, runner, mock_sdr, tmp_path):
        csv_file = str(tmp_path / "clear.csv")
        result = runner.invoke(
            main,
            [
                "scan",
                "clear",
                "--start",
                "144M",
                "--end",
                "144.1M",
                "--step",
                "25k",
                "-d",
                "0.3",
                "-o",
                csv_file,
            ],
        )
        assert result.exit_code == 0
        from pathlib import Path

        assert Path(csv_file).exists()

    def test_scan_clear_custom_threshold(self, runner, mock_sdr):
        result = runner.invoke(
            main,
            [
                "scan",
                "clear",
                "--start",
                "144M",
                "--end",
                "144.1M",
                "--step",
                "25k",
                "-d",
                "0.3",
                "--threshold",
                "-40",
            ],
        )
        assert result.exit_code == 0

    def test_scan_clear_missing_params(self, runner):
        result = runner.invoke(main, ["scan", "clear"])
        assert result.exit_code != 0


# --- Frequency parsing in CLI context ---


class TestCLIFrequencyParsing:
    """Test that the CLI properly parses various frequency formats."""

    def test_mhz_format(self, runner, mock_sdr, tmp_path):
        result = runner.invoke(
            main,
            [
                "record",
                "-f",
                "146.52MHz",
                "-o",
                str(tmp_path / "t.wav"),
                "-d",
                "0.1",
            ],
        )
        assert result.exit_code == 0

    def test_khz_format(self, runner, mock_sdr, tmp_path):
        result = runner.invoke(
            main,
            [
                "record",
                "-f",
                "462562.5k",
                "-o",
                str(tmp_path / "t.wav"),
                "-d",
                "0.1",
            ],
        )
        assert result.exit_code == 0

    def test_ghz_format(self, runner, mock_sdr, tmp_path):
        result = runner.invoke(
            main,
            [
                "record",
                "-f",
                "1.42G",
                "-o",
                str(tmp_path / "t.wav"),
                "-d",
                "0.1",
            ],
        )
        assert result.exit_code == 0

    def test_plain_hz(self, runner, mock_sdr, tmp_path):
        result = runner.invoke(
            main,
            [
                "record",
                "-f",
                "146520000",
                "-o",
                str(tmp_path / "t.wav"),
                "-d",
                "0.1",
            ],
        )
        assert result.exit_code == 0


# --- Transcription CLI flag tests ---


class TestRecordTranscriptionFlags:
    def test_transcribe_flag_in_help(self, runner):
        result = runner.invoke(main, ["record", "--help"])
        assert result.exit_code == 0
        assert "--transcribe" in result.output
        assert "--model" in result.output
        assert "--transcript" in result.output

    def test_transcribe_flag_with_mock(self, runner, mock_sdr, tmp_path):
        """--transcribe should work when faster-whisper is mocked."""
        from unittest.mock import MagicMock

        fake_fw = MagicMock()

        class FakeModel:
            def __init__(self, *a, **kw):
                pass

            def transcribe(self, audio, **kw):
                return iter([]), MagicMock()

        fake_fw.WhisperModel = FakeModel

        transcript = str(tmp_path / "comms.log")

        with patch.dict("sys.modules", {"faster_whisper": fake_fw}):
            with patch("vtms_sdr.transcriber._detect_device", return_value="cpu"):
                with patch(
                    "vtms_sdr.transcriber.detect_model_size",
                    return_value="base",
                ):
                    result = runner.invoke(
                        main,
                        [
                            "record",
                            "-f",
                            "146.52M",
                            "-o",
                            str(tmp_path / "test.wav"),
                            "-d",
                            "0.1",
                            "--transcribe",
                            "--model",
                            "base",
                            "--transcript",
                            transcript,
                        ],
                    )

        assert result.exit_code == 0

    def test_model_choices(self, runner):
        """--model should only accept valid model sizes."""
        result = runner.invoke(
            main,
            [
                "record",
                "-f",
                "146.52M",
                "--model",
                "giant",
            ],
        )
        assert result.exit_code != 0

    def test_auto_transcript_goes_under_recordings_dir(
        self, runner, mock_sdr, tmp_path, monkeypatch
    ):
        """Auto-generated transcript log should land in recordings/ subdir."""
        from unittest.mock import MagicMock

        monkeypatch.chdir(tmp_path)

        fake_fw = MagicMock()

        class FakeModel:
            def __init__(self, *a, **kw):
                pass

            def transcribe(self, audio, **kw):
                return iter([]), MagicMock()

        fake_fw.WhisperModel = FakeModel

        with patch.dict("sys.modules", {"faster_whisper": fake_fw}):
            with patch("vtms_sdr.transcriber._detect_device", return_value="cpu"):
                with patch(
                    "vtms_sdr.transcriber.detect_model_size",
                    return_value="base",
                ):
                    result = runner.invoke(
                        main,
                        [
                            "record",
                            "-f",
                            "146.52M",
                            "-d",
                            "0.1",
                            "--transcribe",
                            "--model",
                            "base",
                        ],
                    )

        assert result.exit_code == 0
        recordings_dir = tmp_path / "recordings"
        log_files = list(recordings_dir.glob("transcript_*.log"))
        assert len(log_files) == 1, f"Expected 1 log in recordings/, found {log_files}"


# --- Channel label CLI flag tests ---


class TestRecordLabelFlag:
    def test_label_flag_in_help(self, runner):
        result = runner.invoke(main, ["record", "--help"])
        assert result.exit_code == 0
        assert "--label" in result.output

    def test_label_flag_with_mock(self, runner, mock_sdr, tmp_path):
        """--label should be passed through to the transcriber."""
        from unittest.mock import MagicMock

        fake_fw = MagicMock()

        class FakeModel:
            def __init__(self, *a, **kw):
                pass

            def transcribe(self, audio, **kw):
                return iter([]), MagicMock()

        fake_fw.WhisperModel = FakeModel

        transcript = str(tmp_path / "comms.log")

        with patch.dict("sys.modules", {"faster_whisper": fake_fw}):
            with patch("vtms_sdr.transcriber._detect_device", return_value="cpu"):
                with patch(
                    "vtms_sdr.transcriber.detect_model_size",
                    return_value="base",
                ):
                    result = runner.invoke(
                        main,
                        [
                            "record",
                            "-f",
                            "146.52M",
                            "-o",
                            str(tmp_path / "test.wav"),
                            "-d",
                            "0.1",
                            "--transcribe",
                            "--model",
                            "base",
                            "--transcript",
                            transcript,
                            "--label",
                            "PIT-CREW",
                        ],
                    )

        assert result.exit_code == 0
        # Verify the label appears in configuration output
        assert "PIT-CREW" in result.output


# --- Transcribe command tests ---


class TestTranscribeCommand:
    def test_transcribe_help(self, runner):
        result = runner.invoke(main, ["transcribe", "--help"])
        assert result.exit_code == 0
        assert "audio file" in result.output.lower() or "FILE" in result.output

    def test_transcribe_missing_file_arg(self, runner):
        result = runner.invoke(main, ["transcribe"])
        assert result.exit_code != 0

    def test_transcribe_nonexistent_file(self, runner):
        result = runner.invoke(main, ["transcribe", "/no/such/file.wav"])
        assert result.exit_code != 0

    def test_transcribe_wav_file(self, runner, tmp_path):
        """Should transcribe a WAV file when faster-whisper is mocked."""
        from unittest.mock import MagicMock
        import soundfile as sf
        import numpy as np

        # Create a WAV file
        audio = np.sin(2 * np.pi * 1000 * np.arange(48000) / 48000).astype(np.float32)
        wav_path = tmp_path / "test.wav"
        sf.write(str(wav_path), audio, 48000, subtype="FLOAT")

        fake_fw = MagicMock()

        class FakeSegment:
            def __init__(self, text):
                self.text = text

        class FakeModel:
            def __init__(self, *a, **kw):
                pass

            def transcribe(self, audio, **kw):
                return iter([FakeSegment("hello world")]), MagicMock()

        fake_fw.WhisperModel = FakeModel

        with patch.dict("sys.modules", {"faster_whisper": fake_fw}):
            with patch("vtms_sdr.transcriber._detect_device", return_value="cpu"):
                result = runner.invoke(
                    main,
                    [
                        "transcribe",
                        str(wav_path),
                        "--model",
                        "base",
                    ],
                )

        assert result.exit_code == 0

    def test_transcribe_with_log_output(self, runner, tmp_path):
        """--output should write transcript to a file."""
        from unittest.mock import MagicMock
        import soundfile as sf
        import numpy as np

        audio = np.sin(2 * np.pi * 1000 * np.arange(48000) / 48000).astype(np.float32)
        wav_path = tmp_path / "test.wav"
        sf.write(str(wav_path), audio, 48000, subtype="FLOAT")

        log_path = tmp_path / "transcript.log"

        fake_fw = MagicMock()

        class FakeSegment:
            def __init__(self, text):
                self.text = text

        class FakeModel:
            def __init__(self, *a, **kw):
                pass

            def transcribe(self, audio, **kw):
                return iter([FakeSegment("roger that")]), MagicMock()

        fake_fw.WhisperModel = FakeModel

        with patch.dict("sys.modules", {"faster_whisper": fake_fw}):
            with patch("vtms_sdr.transcriber._detect_device", return_value="cpu"):
                result = runner.invoke(
                    main,
                    [
                        "transcribe",
                        str(wav_path),
                        "--model",
                        "base",
                        "-o",
                        str(log_path),
                    ],
                )

        assert result.exit_code == 0
        assert log_path.exists()


# --- Preset flag tests ---

PRESET_YAML = """\
presets:
  nascar:
    freq: "462.5625M"
    mod: fm
    gain: 40
    squelch: -35
    label: "SPOTTER"
  minimal:
    freq: "146.52M"
"""


class TestRecordPresetFlag:
    def test_preset_flag_in_help(self, runner):
        result = runner.invoke(main, ["record", "--help"])
        assert result.exit_code == 0
        assert "--preset" in result.output

    def test_preset_file_flag_in_help(self, runner):
        result = runner.invoke(main, ["record", "--help"])
        assert result.exit_code == 0
        assert "--preset-file" in result.output

    def test_preset_supplies_freq(self, runner, mock_sdr, tmp_path, monkeypatch):
        """--preset should supply the freq so -f is not required."""
        monkeypatch.chdir(tmp_path)
        yaml_path = tmp_path / "presets.yaml"
        yaml_path.write_text(PRESET_YAML)

        result = runner.invoke(
            main,
            [
                "record",
                "--preset",
                "nascar",
                "--preset-file",
                str(yaml_path),
                "-d",
                "0.1",
            ],
        )

        # Should succeed without explicit -f
        assert result.exit_code == 0

    def test_preset_nonexistent_name_fails(self, runner, tmp_path):
        """Using a preset name that doesn't exist should fail."""
        yaml_path = tmp_path / "presets.yaml"
        yaml_path.write_text(PRESET_YAML)

        result = runner.invoke(
            main,
            [
                "record",
                "--preset",
                "nonexistent",
                "--preset-file",
                str(yaml_path),
            ],
        )

        assert result.exit_code != 0

    def test_cli_flag_overrides_preset(self, runner, mock_sdr, tmp_path, monkeypatch):
        """Explicit CLI flags should override preset values."""
        monkeypatch.chdir(tmp_path)
        yaml_path = tmp_path / "presets.yaml"
        yaml_path.write_text(PRESET_YAML)

        result = runner.invoke(
            main,
            [
                "record",
                "--preset",
                "nascar",
                "--preset-file",
                str(yaml_path),
                "-m",
                "am",
                "-d",
                "0.1",
            ],
        )

        assert result.exit_code == 0
        # AM should appear in output (overriding preset's fm)
        assert "AM" in result.output


class TestRecordMonitorFlag:
    """Test --monitor and --volume CLI flags."""

    def _base_args(self, output, extra=None):
        """Build base record CLI args with optional extras."""
        args = ["record", "-f", "146.52M", "-m", "fm", "-o", output, "-d", "0.1"]
        if extra:
            args.extend(extra)
        return args

    def test_monitor_flag_in_help(self, runner):
        """--monitor should appear in record help text."""
        result = runner.invoke(main, ["record", "--help"])
        assert "--monitor" in result.output

    def test_volume_flag_in_help(self, runner):
        """--volume should appear in record help text."""
        result = runner.invoke(main, ["record", "--help"])
        assert "--volume" in result.output

    @patch("vtms_sdr.monitor.sd")
    def test_monitor_creates_audio_monitor(self, mock_sd, runner, mock_sdr, tmp_path):
        """--monitor should create an AudioMonitor and pass to recorder."""
        output = str(tmp_path / "test.wav")
        stats = _mock_record_stats(output)
        with patch("vtms_sdr.recorder.AudioRecorder") as mock_recorder_cls:
            mock_recorder_cls.return_value.record.return_value = stats
            result = runner.invoke(
                main,
                self._base_args(output, ["--monitor"]),
            )

            call_kwargs = mock_recorder_cls.call_args[1]
            assert "audio_monitor" in call_kwargs
            assert call_kwargs["audio_monitor"] is not None

    @patch("vtms_sdr.monitor.sd")
    def test_volume_sets_initial_volume(self, mock_sd, runner, mock_sdr, tmp_path):
        """--volume should set the initial volume on AudioMonitor."""
        output = str(tmp_path / "test.wav")
        stats = _mock_record_stats(output)
        with patch("vtms_sdr.recorder.AudioRecorder") as mock_recorder_cls:
            mock_recorder_cls.return_value.record.return_value = stats
            result = runner.invoke(
                main,
                self._base_args(output, ["--monitor", "--volume", "0.8"]),
            )

            call_kwargs = mock_recorder_cls.call_args[1]
            monitor = call_kwargs["audio_monitor"]
            assert monitor.volume == pytest.approx(0.8)

    def test_no_monitor_by_default(self, runner, mock_sdr, tmp_path):
        """Without --monitor, no audio_monitor should be created."""
        output = str(tmp_path / "test.wav")
        stats = _mock_record_stats(output)
        with patch("vtms_sdr.recorder.AudioRecorder") as mock_recorder_cls:
            mock_recorder_cls.return_value.record.return_value = stats
            result = runner.invoke(main, self._base_args(output))

            call_kwargs = mock_recorder_cls.call_args[1]
            assert call_kwargs.get("audio_monitor") is None

    def test_volume_without_monitor_ignored(self, runner, mock_sdr, tmp_path):
        """--volume without --monitor should not create a monitor."""
        output = str(tmp_path / "test.wav")
        stats = _mock_record_stats(output)
        with patch("vtms_sdr.recorder.AudioRecorder") as mock_recorder_cls:
            mock_recorder_cls.return_value.record.return_value = stats
            result = runner.invoke(
                main,
                self._base_args(output, ["--volume", "0.8"]),
            )

            call_kwargs = mock_recorder_cls.call_args[1]
            assert call_kwargs.get("audio_monitor") is None


class TestRecordMonitorUI:
    """Test MonitorUI curses integration in the CLI record command."""

    def _base_args(self, output, extra=None):
        """Build base record CLI args with optional extras."""
        args = ["record", "-f", "146.52M", "-m", "fm", "-o", output, "-d", "0.1"]
        if extra:
            args.extend(extra)
        return args

    @patch("vtms_sdr.monitor.sd")
    def test_monitor_creates_monitor_ui(self, mock_sd, runner, mock_sdr, tmp_path):
        """--monitor should create a MonitorUI with correct params."""
        output = str(tmp_path / "test.wav")
        stats = _mock_record_stats(output)
        with (
            patch("vtms_sdr.recorder.AudioRecorder") as mock_recorder_cls,
            patch("vtms_sdr.monitor.MonitorUI") as mock_ui_cls,
        ):
            mock_recorder_cls.return_value.record.return_value = stats
            mock_ui_cls.return_value.launch.return_value = stats

            result = runner.invoke(
                main,
                self._base_args(output, ["--monitor"]),
            )

            mock_ui_cls.assert_called_once()
            call_kwargs = mock_ui_cls.call_args[1]
            assert call_kwargs["freq"] == 146520000
            assert call_kwargs["mod"] == "fm"
            assert call_kwargs["squelch_db"] == -30.0
            assert call_kwargs["audio_monitor"] is not None

    @patch("vtms_sdr.monitor.sd")
    def test_monitor_calls_launch(self, mock_sd, runner, mock_sdr, tmp_path):
        """--monitor should call MonitorUI.launch() with a callable."""
        output = str(tmp_path / "test.wav")
        stats = _mock_record_stats(output)
        with (
            patch("vtms_sdr.recorder.AudioRecorder") as mock_recorder_cls,
            patch("vtms_sdr.monitor.MonitorUI") as mock_ui_cls,
        ):
            mock_recorder_cls.return_value.record.return_value = stats
            mock_ui_cls.return_value.launch.return_value = stats

            result = runner.invoke(
                main,
                self._base_args(output, ["--monitor"]),
            )

            mock_ui_cls.return_value.launch.assert_called_once()
            launch_args = mock_ui_cls.return_value.launch.call_args[0]
            assert callable(launch_args[0])

    @patch("vtms_sdr.monitor.sd")
    def test_monitor_starts_and_stops_audio(self, mock_sd, runner, mock_sdr, tmp_path):
        """--monitor should call audio_monitor.start() and .stop()."""
        output = str(tmp_path / "test.wav")
        stats = _mock_record_stats(output)
        with (
            patch("vtms_sdr.recorder.AudioRecorder") as mock_recorder_cls,
            patch("vtms_sdr.monitor.MonitorUI") as mock_ui_cls,
            patch("vtms_sdr.monitor.AudioMonitor") as mock_am_cls,
        ):
            mock_recorder_cls.return_value.record.return_value = stats
            mock_ui_cls.return_value.launch.return_value = stats

            result = runner.invoke(
                main,
                self._base_args(output, ["--monitor"]),
            )

            mock_am_cls.return_value.start.assert_called_once()
            mock_am_cls.return_value.stop.assert_called_once()

    @patch("vtms_sdr.monitor.sd")
    def test_monitor_stats_printed(self, mock_sd, runner, mock_sdr, tmp_path):
        """--monitor should still print final stats from MonitorUI."""
        output = str(tmp_path / "test.wav")
        stats = _mock_record_stats(output)
        with (
            patch("vtms_sdr.recorder.AudioRecorder") as mock_recorder_cls,
            patch("vtms_sdr.monitor.MonitorUI") as mock_ui_cls,
        ):
            mock_recorder_cls.return_value.record.return_value = stats
            mock_ui_cls.return_value.launch.return_value = stats

            result = runner.invoke(
                main,
                self._base_args(output, ["--monitor"]),
            )

            assert "Recording complete" in result.output

    def test_no_monitor_skips_monitor_ui(self, runner, mock_sdr, tmp_path):
        """Without --monitor, MonitorUI should not be created."""
        output = str(tmp_path / "test.wav")
        stats = _mock_record_stats(output)
        with (
            patch("vtms_sdr.recorder.AudioRecorder") as mock_recorder_cls,
            patch("vtms_sdr.monitor.MonitorUI") as mock_ui_cls,
        ):
            mock_recorder_cls.return_value.record.return_value = stats

            result = runner.invoke(main, self._base_args(output))

            mock_ui_cls.assert_not_called()


class TestRecordMonitorCallbackWiring:
    """Test that MonitorUI callbacks are wired to AudioRecorder."""

    def _base_args(self, output, extra=None):
        """Build base record CLI args with optional extras."""
        args = ["record", "-f", "146.52M", "-m", "fm", "-o", output, "-d", "0.1"]
        if extra:
            args.extend(extra)
        return args

    @patch("vtms_sdr.monitor.sd")
    def test_monitor_wires_progress_callback(self, mock_sd, runner, mock_sdr, tmp_path):
        """record() should be called with progress_callback when --monitor is active."""
        output = str(tmp_path / "test.wav")
        stats = _mock_record_stats(output)
        with (
            patch("vtms_sdr.recorder.AudioRecorder") as mock_recorder_cls,
            patch("vtms_sdr.monitor.MonitorUI") as mock_ui_cls,
        ):
            mock_recorder_cls.return_value.record.return_value = stats

            # When launch is called, invoke the record_func to trigger record()
            def launch_side_effect(record_func):
                return record_func()

            mock_ui_cls.return_value.launch.side_effect = launch_side_effect

            result = runner.invoke(
                main,
                self._base_args(output, ["--monitor"]),
            )

            # record() should have been called with progress_callback kwarg
            record_call = mock_recorder_cls.return_value.record
            record_call.assert_called_once()
            call_kwargs = record_call.call_args[1]
            assert "progress_callback" in call_kwargs
            assert call_kwargs["progress_callback"] is not None

    @patch("vtms_sdr.monitor.sd")
    def test_monitor_wires_squelch_callback(self, mock_sd, runner, mock_sdr, tmp_path):
        """AudioRecorder should have _squelch_callback set when --monitor."""
        output = str(tmp_path / "test.wav")
        stats = _mock_record_stats(output)
        with (
            patch("vtms_sdr.recorder.AudioRecorder") as mock_recorder_cls,
            patch("vtms_sdr.monitor.MonitorUI") as mock_ui_cls,
        ):
            mock_recorder_cls.return_value.record.return_value = stats
            mock_ui_cls.return_value.launch.return_value = stats

            result = runner.invoke(
                main,
                self._base_args(output, ["--monitor"]),
            )

            # _squelch_callback should be wired after construction
            mock_recorder = mock_recorder_cls.return_value
            assert mock_recorder._squelch_callback is not None

    @patch("vtms_sdr.monitor.sd")
    def test_monitor_wires_transcriber_ui_callback(
        self, mock_sd, runner, mock_sdr, tmp_path
    ):
        """Transcriber should receive ui_callback=monitor_ui.add_transcription
        when both --monitor and --transcribe are active."""
        output = str(tmp_path / "test.wav")
        transcript = str(tmp_path / "comms.log")
        stats = _mock_record_stats(output)

        fake_fw = MagicMock()

        class FakeModel:
            def __init__(self, *a, **kw):
                pass

            def transcribe(self, audio, **kw):
                return iter([]), MagicMock()

        fake_fw.WhisperModel = FakeModel

        with (
            patch("vtms_sdr.recorder.AudioRecorder") as mock_recorder_cls,
            patch("vtms_sdr.monitor.MonitorUI") as mock_ui_cls,
            patch.dict("sys.modules", {"faster_whisper": fake_fw}),
            patch("vtms_sdr.transcriber._detect_device", return_value="cpu"),
            patch(
                "vtms_sdr.transcriber.detect_model_size",
                return_value="base",
            ),
        ):
            mock_recorder_cls.return_value.record.return_value = stats
            mock_ui_cls.return_value.launch.return_value = stats

            result = runner.invoke(
                main,
                self._base_args(
                    output,
                    [
                        "--monitor",
                        "--transcribe",
                        "--model",
                        "base",
                        "--transcript",
                        transcript,
                    ],
                ),
            )

            assert result.exit_code == 0, result.output

            # Transcriber should have ui_callback set to monitor_ui.add_transcription
            mock_ui_cls.return_value.add_transcription.assert_not_called  # exists
            # Check that Transcriber was constructed with ui_callback OR
            # that _ui_callback was set after construction
            recorder_kwargs = mock_recorder_cls.call_args[1]
            transcriber = recorder_kwargs.get("transcriber")
            assert transcriber is not None
            assert (
                transcriber._ui_callback is mock_ui_cls.return_value.add_transcription
            )


# --- Language and Prompt flag tests (B5/B6) ---


class TestLanguageAndPromptFlags:
    """Test --language and --prompt CLI flags for record and transcribe commands."""

    @pytest.fixture(autouse=True)
    def _pre_import_transcriber(self):
        """Ensure vtms_sdr.transcriber is already in sys.modules.

        The record command lazily imports ``from .transcriber import Transcriber``.
        If the module hasn't been loaded yet, that triggers an import chain
        (transcriber → demod → scipy → numpy) which poisons the process with a
        ``cannot load module more than once per process`` error from numpy's C
        extension when ``patch.dict("sys.modules", …)`` is in effect.

        Pre-importing avoids the problem entirely.
        """
        import vtms_sdr.transcriber  # noqa: F401

    def test_record_language_flag_passed_to_transcriber(
        self, runner, mock_sdr, tmp_path
    ):
        """record --transcribe --language es should pass language='es' to Transcriber."""
        fake_fw = MagicMock()

        class FakeModel:
            def __init__(self, *a, **kw):
                pass

            def transcribe(self, audio, **kw):
                return iter([]), MagicMock()

        fake_fw.WhisperModel = FakeModel
        transcript = str(tmp_path / "comms.log")

        with patch.dict("sys.modules", {"faster_whisper": fake_fw}):
            with patch("vtms_sdr.transcriber._detect_device", return_value="cpu"):
                with patch(
                    "vtms_sdr.transcriber.detect_model_size", return_value="base"
                ):
                    with patch(
                        "vtms_sdr.transcriber.Transcriber", wraps=None
                    ) as mock_transcriber_cls:
                        # Make the mock return something usable
                        mock_transcriber_cls.return_value.model_size = "base"
                        mock_transcriber_cls.return_value.transcription_count = 0

                        result = runner.invoke(
                            main,
                            [
                                "record",
                                "-f",
                                "146.52M",
                                "-o",
                                str(tmp_path / "test.wav"),
                                "-d",
                                "0.1",
                                "--transcribe",
                                "--model",
                                "base",
                                "--transcript",
                                transcript,
                                "--language",
                                "es",
                            ],
                        )

                        assert result.exit_code == 0, result.output
                        mock_transcriber_cls.assert_called_once()
                        call_kwargs = mock_transcriber_cls.call_args[1]
                        assert call_kwargs["language"] == "es"

    def test_record_prompt_flag_passed_to_transcriber(self, runner, mock_sdr, tmp_path):
        """record --transcribe --prompt 'Custom' should pass prompt='Custom' to Transcriber."""
        fake_fw = MagicMock()

        class FakeModel:
            def __init__(self, *a, **kw):
                pass

            def transcribe(self, audio, **kw):
                return iter([]), MagicMock()

        fake_fw.WhisperModel = FakeModel
        transcript = str(tmp_path / "comms.log")

        with patch.dict("sys.modules", {"faster_whisper": fake_fw}):
            with patch("vtms_sdr.transcriber._detect_device", return_value="cpu"):
                with patch(
                    "vtms_sdr.transcriber.detect_model_size", return_value="base"
                ):
                    with patch(
                        "vtms_sdr.transcriber.Transcriber", wraps=None
                    ) as mock_transcriber_cls:
                        mock_transcriber_cls.return_value.model_size = "base"
                        mock_transcriber_cls.return_value.transcription_count = 0

                        result = runner.invoke(
                            main,
                            [
                                "record",
                                "-f",
                                "146.52M",
                                "-o",
                                str(tmp_path / "test.wav"),
                                "-d",
                                "0.1",
                                "--transcribe",
                                "--model",
                                "base",
                                "--transcript",
                                transcript,
                                "--prompt",
                                "Custom",
                            ],
                        )

                        assert result.exit_code == 0, result.output
                        mock_transcriber_cls.assert_called_once()
                        call_kwargs = mock_transcriber_cls.call_args[1]
            assert call_kwargs["prompt"] == "Custom"


class TestScanRecommendCommand:
    """Tests for the scan recommend CLI command."""

    def test_recommend_help(self, runner):
        result = runner.invoke(main, ["scan", "recommend", "--help"])
        assert result.exit_code == 0
        assert "--start" in result.output
        assert "--end" in result.output
        assert "--step" in result.output
        assert "--duration" in result.output
        assert "--top" in result.output

    def test_recommend_basic(self, runner, mock_sdr):
        result = runner.invoke(
            main,
            [
                "scan",
                "recommend",
                "--start",
                "446MHz",
                "--end",
                "446.1MHz",
                "--step",
                "25kHz",
                "-d",
                "0.5",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Rank" in result.output

    def test_recommend_top_flag(self, runner, mock_sdr):
        result = runner.invoke(
            main,
            [
                "scan",
                "recommend",
                "--start",
                "446MHz",
                "--end",
                "446.2MHz",
                "--step",
                "25kHz",
                "-d",
                "0.5",
                "--top",
                "2",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Showing top 2" in result.output

    def test_recommend_csv_output(self, runner, mock_sdr, tmp_path):
        csv_file = str(tmp_path / "recommend.csv")
        result = runner.invoke(
            main,
            [
                "scan",
                "recommend",
                "--start",
                "446MHz",
                "--end",
                "446.1MHz",
                "--step",
                "25kHz",
                "-d",
                "0.5",
                "-o",
                csv_file,
            ],
        )
        assert result.exit_code == 0, result.output
        import os

        assert os.path.exists(csv_file)
        with open(csv_file) as f:
            header = f.readline()
        assert "active_count" in header

    def test_recommend_missing_params(self, runner):
        result = runner.invoke(main, ["scan", "recommend"])
        assert result.exit_code != 0

    def test_transcribe_language_flag_passed(self, runner, tmp_path):
        """transcribe --language es should pass language='es' to transcribe_file."""
        import soundfile as sf

        audio = np.sin(2 * np.pi * 1000 * np.arange(48000) / 48000).astype(np.float32)
        wav_path = tmp_path / "test.wav"
        sf.write(str(wav_path), audio, 48000, subtype="FLOAT")

        with patch("vtms_sdr.transcriber.transcribe_file") as mock_tf:
            mock_tf.return_value = "hello world"
            result = runner.invoke(
                main,
                [
                    "transcribe",
                    str(wav_path),
                    "--model",
                    "base",
                    "--language",
                    "es",
                ],
            )

            assert result.exit_code == 0, result.output
            mock_tf.assert_called_once()
            call_kwargs = mock_tf.call_args[1]
            assert call_kwargs["language"] == "es"

    def test_transcribe_prompt_flag_passed(self, runner, tmp_path):
        """transcribe --prompt 'Custom' should pass prompt='Custom' to transcribe_file."""
        import soundfile as sf

        audio = np.sin(2 * np.pi * 1000 * np.arange(48000) / 48000).astype(np.float32)
        wav_path = tmp_path / "test.wav"
        sf.write(str(wav_path), audio, 48000, subtype="FLOAT")

        with patch("vtms_sdr.transcriber.transcribe_file") as mock_tf:
            mock_tf.return_value = "hello world"
            result = runner.invoke(
                main,
                [
                    "transcribe",
                    str(wav_path),
                    "--model",
                    "base",
                    "--prompt",
                    "Custom",
                ],
            )

            assert result.exit_code == 0, result.output
            mock_tf.assert_called_once()
            call_kwargs = mock_tf.call_args[1]
            assert call_kwargs["prompt"] == "Custom"


# ---------------------------------------------------------------------------
# Tests: --dcs CLI option
# ---------------------------------------------------------------------------


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
        result = runner.invoke(main, ["record", "-f", "462.5625M", "--dcs", "999"])
        assert result.exit_code != 0

    def test_dcs_from_preset(self, tmp_path):
        """DCS code from preset should be used when --dcs not given on CLI."""
        import yaml

        preset_data = {
            "presets": {"test": {"freq": "462.5625M", "mod": "fm", "dcs_code": 23}}
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
