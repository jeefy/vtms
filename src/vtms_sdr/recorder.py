"""Audio recording: WAV output with squelch gating."""

from __future__ import annotations

import logging
import signal
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Generator

import numpy as np
import soundfile as sf

from .demod import AUDIO_SAMPLE_RATE

logger = logging.getLogger(__name__)

__all__ = [
    "AUDIO_SAMPLE_RATE",
    "AudioRecorder",
]


if TYPE_CHECKING:
    from .monitor import AudioMonitor
    from .transcriber import Transcriber


class AudioRecorder:
    """Records demodulated audio to WAV files.

    Supports squelch gating to suppress recording during silence,
    and graceful shutdown on Ctrl+C (SIGINT).
    """

    def __init__(
        self,
        output_path: str | Path,
        audio_format: str = "wav",
        sample_rate: int = AUDIO_SAMPLE_RATE,
        squelch_db: float = -30.0,
        transcriber: Transcriber | None = None,
        audio_monitor: AudioMonitor | None = None,
        squelch_callback: Callable[[bool, float], None] | None = None,
    ):
        """Initialize the audio recorder.

        Args:
            output_path: Path to the output audio file.
            audio_format: Output format (currently only 'wav').
            sample_rate: Audio sample rate (default: 48000).
            squelch_db: Squelch threshold in dB. Audio below this
                        level is not recorded. Use -100 to disable.
            transcriber: Optional Transcriber for live speech-to-text.
            audio_monitor: Optional AudioMonitor for live audio playback.
            squelch_callback: Optional callback receiving (is_open, power_db)
                on each block for real-time squelch state reporting.
        """
        self.output_path = Path(output_path)
        self.audio_format = audio_format.lower()
        self.sample_rate = sample_rate
        self.squelch_db = squelch_db
        self._transcriber = transcriber
        self._audio_monitor = audio_monitor
        self._squelch_callback = squelch_callback

        self._stopped = threading.Event()
        self._samples_written = 0
        self._start_time: float = 0.0
        self._original_sigint = None
        self._squelch_was_open = False
        self._progress_callback: Callable[[float, int, int], None] | None = None

        if self.audio_format not in ("wav",):
            raise ValueError(f"Unsupported format '{self.audio_format}'. Use 'wav'.")

    def _install_signal_handler(self) -> None:
        """Install SIGINT handler for graceful shutdown.

        Only installs when called from the main thread. When recording
        runs in a background thread (e.g. with --monitor), the main
        thread handles signals and sets _stopped via the MonitorUI.
        """
        if threading.current_thread() is not threading.main_thread():
            return

        self._original_sigint = signal.getsignal(signal.SIGINT)

        def handler(signum, frame):
            logger.info("Stopping recording...")
            self._stopped.set()

        signal.signal(signal.SIGINT, handler)

    def _restore_signal_handler(self) -> None:
        """Restore original SIGINT handler."""
        if threading.current_thread() is not threading.main_thread():
            return

        if self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)

    def _is_above_squelch(self, iq_power: float) -> bool:
        """Check if IQ signal power is above squelch threshold.

        Args:
            iq_power: Signal power in dB measured from raw IQ samples
                      (before demodulation).
        """
        if self.squelch_db <= -100:
            return True  # Squelch disabled

        return iq_power > self.squelch_db

    def _process_squelch_and_transcribe(
        self, audio_block: np.ndarray, is_above: bool
    ) -> None:
        """Track squelch transitions and forward audio to the transcriber.

        Called once per audio block with the current squelch state.
        Fires on_squelch_open/on_audio_chunk/on_squelch_close callbacks
        on the transcriber when appropriate.
        """
        if self._transcriber is None:
            return

        now = time.time()

        if is_above and not self._squelch_was_open:
            # Squelch just opened
            self._squelch_was_open = True
            self._transcriber.on_squelch_open(now)
            self._transcriber.on_audio_chunk(audio_block)
        elif is_above and self._squelch_was_open:
            # Squelch still open - feed audio
            self._transcriber.on_audio_chunk(audio_block)
        elif not is_above and self._squelch_was_open:
            # Squelch just closed
            self._squelch_was_open = False
            self._transcriber.on_squelch_close(now)

    def record(
        self,
        audio_generator: Generator[tuple[float, np.ndarray], None, None],
        duration: float | None = None,
        progress_callback: Callable[[float, int, int], None] | None = None,
    ) -> dict:
        """Record audio from a generator to file.

        Args:
            audio_generator: Yields float32 numpy arrays of audio samples.
            duration: Maximum recording duration in seconds (None = until Ctrl+C).
            progress_callback: Optional callback receiving (elapsed, samples_written,
                sample_rate) on each block. When provided, suppresses stderr progress.

        Returns:
            Dict with recording stats: samples_written, duration, file_size.
        """
        self._stopped.clear()
        self._samples_written = 0
        self._start_time = time.time()
        self._progress_callback = progress_callback
        self._install_signal_handler()

        try:
            return self._record_wav(audio_generator, duration)
        finally:
            self._restore_signal_handler()

    def _record_wav(
        self,
        audio_generator: Generator[tuple[float, np.ndarray], None, None],
        duration: float | None,
    ) -> dict:
        """Record audio directly to WAV file."""
        wav_path = self.output_path
        if not wav_path.suffix:
            wav_path = wav_path.with_suffix(".wav")

        with sf.SoundFile(
            str(wav_path),
            mode="w",
            samplerate=self.sample_rate,
            channels=1,
            format="WAV",
            subtype="FLOAT",
        ) as wav_file:
            for iq_power, audio_block in audio_generator:
                if self._stopped.is_set():
                    break

                if duration is not None:
                    elapsed = time.time() - self._start_time
                    if elapsed >= duration:
                        break

                is_above = self._is_above_squelch(iq_power)
                self._process_squelch_and_transcribe(audio_block, is_above)

                if self._squelch_callback is not None:
                    self._squelch_callback(is_above, float(iq_power))

                if is_above:
                    wav_file.write(audio_block)
                    self._samples_written += len(audio_block)
                    if self._audio_monitor is not None:
                        self._audio_monitor.feed(audio_block)

                # Print progress
                self._print_progress()

        # Flush any remaining transcription buffer on stop
        if self._transcriber and self._squelch_was_open:
            self._transcriber.on_squelch_close(time.time())
            self._squelch_was_open = False

        sys.stderr.write("\n")  # Newline after progress
        return self._get_stats(wav_path)

    def _print_progress(self) -> None:
        """Print recording progress or invoke callback."""
        elapsed = time.time() - self._start_time

        if self._progress_callback is not None:
            self._progress_callback(elapsed, self._samples_written, self.sample_rate)
            return

        duration_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
        samples_sec = self._samples_written / self.sample_rate
        audio_str = time.strftime("%H:%M:%S", time.gmtime(samples_sec))

        sys.stderr.write(
            f"\rRecording: {duration_str} elapsed | "
            f"{audio_str} audio captured | "
            f"Squelch: {self.squelch_db:.0f} dB"
        )
        sys.stderr.flush()

    def _get_stats(self, file_path: Path) -> dict:
        """Return recording statistics."""
        file_size = file_path.stat().st_size if file_path.exists() else 0
        audio_duration = self._samples_written / self.sample_rate

        return {
            "file": str(file_path),
            "format": self.audio_format,
            "samples_written": self._samples_written,
            "audio_duration_sec": audio_duration,
            "file_size_bytes": file_size,
            "sample_rate": self.sample_rate,
        }
