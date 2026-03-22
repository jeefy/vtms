"""Live transcription of radio communications using faster-whisper.

Integrates with the recorder's squelch detection to segment audio
by transmission and transcribe each one independently.
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)

# Eagerly check for noisereduce at import time so we fail-fast once
# instead of spamming warnings on every audio chunk.
try:
    import noisereduce as nr

    _NOISEREDUCE_AVAILABLE = True
except ImportError as _nr_err:
    nr = None  # type: ignore[assignment]
    _NOISEREDUCE_AVAILABLE = False
    logger.warning(
        "noisereduce not importable — noise reduction will be disabled. "
        "Install with: pip install 'vtms-sdr[transcribe]'  |  "
        "Cause: %s  |  Python: %s  |  sys.path: %s",
        _nr_err,
        sys.executable,
        sys.path,
        exc_info=True,
    )
    del _nr_err

from .demod import AUDIO_SAMPLE_RATE

__all__ = [
    "MAX_BUFFER_DURATION",
    "MOTORSPORT_PROMPT",
    "Transcriber",
    "WhisperModel",
    "clear_model_cache",
    "detect_model_size",
    "transcribe_file",
]


# Maximum buffer duration before forced flush (seconds).
# Prevents unbounded memory growth on very long transmissions.
MAX_BUFFER_DURATION = 30.0

MOTORSPORT_PROMPT = (
    "Motorsport radio communication. "
    "Teams, drivers, pit crew, and spotters use short, clipped phrases. "
    "Common terms: copy, box box, pit, push push, clear, caution, yellow, green, "
    "red flag, pace car, safety car, DRS, understeer, oversteer, "
    "tire deg, fuel map, pit window, undercut, overcut."
)

# Module-level cache for Whisper models keyed by model_size string.
# Avoids reloading the same model on repeated transcribe_file() calls.
# NOTE: Not thread-safe. Only use from the main thread.
_MODEL_CACHE: dict[str, object] = {}


def clear_model_cache() -> None:
    """Clear the Whisper model cache."""
    _MODEL_CACHE.clear()


def _preprocess_for_whisper(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Preprocess raw audio for Whisper transcription.

    Pipeline:
        1. Bandpass filter 400-3400 Hz (radio voice band, rejects wind noise)
        2. Adaptive noise reduction (if noisereduce is installed)
        3. Peak normalize to [-1.0, 1.0]
        4. Resample to 16 kHz

    Args:
        audio: Raw audio as a numpy array at any sample rate.
        sample_rate: The sample rate of the input audio.

    Returns:
        Float32 numpy array at 16 kHz, normalized, ready for Whisper.
    """
    from math import gcd

    from scipy.signal import butter, resample_poly, sosfilt

    # Guard against empty audio
    if len(audio) == 0:
        return np.array([], dtype=np.float32)

    # 1. Bandpass filter 400-3400 Hz (radio voice band)
    # Lower cutoff raised from 300→400 Hz to reject wind noise energy
    # that bleeds into the 300-400 Hz range while preserving radio speech
    # fundamentals (compressed radio audio sits above ~400 Hz).
    sos = butter(4, [400, 3400], btype="band", fs=sample_rate, output="sos")
    audio = sosfilt(sos, audio).astype(np.float32)

    # 2. Noise reduction (uses module-level import check)
    # Uses non-stationary mode to handle bursty noise (wind, interference)
    # rather than only constant hiss/hum.
    # Skip noise reduction on silence — noisereduce's non-stationary mode
    # produces NaN on all-zeros input (division by zero in spectral gate).
    if _NOISEREDUCE_AVAILABLE and np.max(np.abs(audio)) > 0:
        try:
            audio = nr.reduce_noise(
                y=audio,
                sr=sample_rate,
                prop_decrease=0.85,
                stationary=False,
                time_constant_s=0.5,
                freq_mask_smooth_hz=500,
                n_std_thresh_stationary=1.5,
            ).astype(np.float32)
        except Exception:
            logger.warning(
                "noise reduction failed — skipping. See traceback below.",
                exc_info=True,
            )
    else:
        logger.debug("noisereduce unavailable — skipping noise reduction")

    # 3. Peak normalize to [-1.0, 1.0], guard against silence
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak

    # 4. Resample to 16 kHz using rational resampling
    if sample_rate != 16000:
        g = gcd(16000, sample_rate)
        up = 16000 // g
        down = sample_rate // g
        audio = resample_poly(audio, up, down).astype(np.float32)

    return audio.astype(np.float32)


def _run_whisper(
    model: WhisperModel,
    audio: np.ndarray,
    language: str | None,
    initial_prompt: str | None = None,
) -> list[str]:
    """Run faster-whisper transcription with standard parameters.

    Args:
        model: A WhisperModel (or protocol-compatible) instance.
        audio: Float32 numpy array at 16 kHz.
        language: Language code or None for auto-detect.
        initial_prompt: Optional prompt to condition Whisper decoding.

    Returns:
        List of non-empty stripped segment texts.
    """
    segments, _info = model.transcribe(
        audio,
        language=language,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(
            min_silence_duration_ms=300,
            speech_pad_ms=200,
        ),
        temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
        initial_prompt=initial_prompt,
        condition_on_previous_text=False,
        no_speech_threshold=0.45,
        log_prob_threshold=-0.8,
        compression_ratio_threshold=2.0,
    )

    texts = []
    for segment in segments:
        text = segment.text.strip()
        # Filter out low-confidence segments that are likely hallucinations
        # from noisy audio. avg_logprob <= -1.0 indicates Whisper was
        # essentially guessing.
        if text and getattr(segment, "avg_logprob", 0.0) > -1.0:
            texts.append(text)
    return texts


class WhisperModel(Protocol):
    """Protocol matching the faster-whisper WhisperModel interface."""

    def transcribe(
        self,
        audio: np.ndarray,
        language: str | None = None,
        initial_prompt: str | None = None,
        **kwargs,
    ) -> tuple: ...


def _check_faster_whisper() -> None:
    """Verify faster-whisper is installed."""
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "Transcription requires faster-whisper. Install with:\n"
            "  pip install vtms-sdr[transcribe]\n"
            "or:\n"
            "  pip install faster-whisper"
        )


def detect_model_size() -> str:
    """Auto-detect the best Whisper model size for available hardware.

    Returns 'medium' if CUDA is available, 'base' otherwise.
    """
    try:
        import torch

        if torch.cuda.is_available():
            return "medium"
    except ImportError:
        pass

    # Check for ctranslate2 CUDA support directly
    try:
        import ctranslate2

        if "cuda" in ctranslate2.get_supported_compute_types("cuda"):
            return "medium"
    except (ImportError, RuntimeError):
        pass

    return "base"


def _detect_device() -> str:
    """Detect whether to use CUDA or CPU.

    Validates that CUDA is actually usable (not just installed) by
    checking driver compatibility before returning 'cuda'.
    """
    try:
        import torch

        if torch.cuda.is_available():
            # Verify CUDA actually works by attempting a small allocation
            try:
                torch.zeros(1, device="cuda")
                return "cuda"
            except RuntimeError:
                pass
    except ImportError:
        pass

    try:
        import ctranslate2

        supported = ctranslate2.get_supported_compute_types("cuda")
        if "float16" in supported or "int8" in supported:
            return "cuda"
    except (ImportError, RuntimeError):
        pass

    return "cpu"


class Transcriber:
    """Live transcription of radio audio using faster-whisper.

    Works with the recorder's squelch events to segment audio by
    transmission. Each transmission is transcribed independently
    and logged with a timestamp.

    Usage:
        transcriber = Transcriber(model_size="base", log_path="comms.log")

        # Called by the recorder on squelch state changes:
        transcriber.on_squelch_open(timestamp)
        transcriber.on_audio_chunk(audio_block)
        transcriber.on_squelch_close(timestamp)

        # Cleanup:
        transcriber.close()
    """

    def __init__(
        self,
        model_size: str = "auto",
        language: str = "en",
        log_path: str | Path | None = None,
        sample_rate: int = AUDIO_SAMPLE_RATE,
        label: str | None = None,
        ui_callback: Callable[[str, str, str], None] | None = None,
        prompt: str | None = None,
    ):
        """Initialize the transcriber.

        Args:
            model_size: Whisper model size ('tiny', 'base', 'small',
                       'medium', 'large', or 'auto' to detect).
            language: Language code for transcription.
            log_path: Path for the transcript log file. None for stdout only.
            sample_rate: Audio sample rate (must match demodulator output).
            label: Optional channel label (e.g. 'PIT-CREW') included
                   in transcript output.
            ui_callback: Optional callback receiving (timestamp, label, text)
                for forwarding transcriptions to a UI.
            prompt: Custom initial prompt for Whisper. None uses the
                default MOTORSPORT_PROMPT.
        """
        _check_faster_whisper()

        if model_size == "auto":
            model_size = detect_model_size()

        self.model_size = model_size
        self.language = language
        self.sample_rate = sample_rate
        self._label = label
        self._ui_callback = ui_callback
        self._prompt = prompt
        self._log_file = None
        self._log_path = Path(log_path) if log_path else None

        # Audio buffer for current transmission
        self._buffer: list[np.ndarray] = []
        self._buffer_samples = 0
        self._squelch_open = False
        self._transmission_start: float = 0.0
        self._transcription_count = 0

        # Load model
        self._model = self._load_model()

        # Open log file
        if self._log_path:
            self._log_file = open(self._log_path, "a", encoding="utf-8")

    def _load_model(self) -> WhisperModel:
        """Load the faster-whisper model."""
        from faster_whisper import WhisperModel as FWModel

        device = _detect_device()
        compute_type = "float16" if device == "cuda" else "int8"

        logger.info(
            "Loading Whisper model '%s' on %s (%s)...",
            self.model_size,
            device,
            compute_type,
        )

        model = FWModel(
            self.model_size,
            device=device,
            compute_type=compute_type,
        )

        logger.info("Whisper model loaded.")
        return model

    def write_log_header(self, freq_str: str, mod: str) -> None:
        """Write the header to the transcript log.

        Args:
            freq_str: Formatted frequency string.
            mod: Modulation type.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        label_part = f" | Channel: {self._label}" if self._label else ""
        header = (
            f"# vtms-sdr transcription log\n"
            f"# Frequency: {freq_str} | Modulation: {mod.upper()}"
            f"{label_part}"
            f" | Started: {now}\n\n"
        )

        if self._log_file:
            self._log_file.write(header)
            self._log_file.flush()

    def on_squelch_open(self, timestamp: float) -> None:
        """Called when squelch opens (signal detected).

        Args:
            timestamp: Wall-clock time when squelch opened.
        """
        self._squelch_open = True
        self._transmission_start = timestamp
        self._buffer.clear()
        self._buffer_samples = 0

    def on_audio_chunk(self, audio: np.ndarray) -> None:
        """Called with each audio block while squelch is open.

        If the buffer exceeds MAX_BUFFER_DURATION, it is flushed
        and transcribed as a partial transmission.

        Args:
            audio: Float32 numpy array of audio samples.
        """
        if not self._squelch_open:
            return

        self._buffer.append(audio.copy())
        self._buffer_samples += len(audio)

        # Flush if buffer is too long
        buffer_duration = self._buffer_samples / self.sample_rate
        if buffer_duration >= MAX_BUFFER_DURATION:
            self._flush_buffer(partial=True)

    def on_squelch_close(self, timestamp: float) -> None:
        """Called when squelch closes (signal lost).

        Triggers transcription of the buffered audio.

        Args:
            timestamp: Wall-clock time when squelch closed.
        """
        if not self._squelch_open:
            return

        self._squelch_open = False
        self._flush_buffer(partial=False)

    def _flush_buffer(self, partial: bool = False) -> None:
        """Transcribe the buffered audio and log the result.

        Args:
            partial: If True, this is a mid-transmission flush.
        """
        if not self._buffer:
            return

        # Concatenate buffered audio
        audio = np.concatenate(self._buffer)
        self._buffer.clear()
        self._buffer_samples = 0

        # Skip very short transmissions (< 0.3s) - likely squelch noise
        duration = len(audio) / self.sample_rate
        if duration < 0.3:
            return

        # Transcribe
        text = self._transcribe(audio)

        # If transcription failed entirely, skip logging
        if text is None:
            return

        # Format timestamp
        time_str = time.strftime("%H:%M:%S", time.localtime(self._transmission_start))

        label_prefix = f" [{self._label}]" if self._label else ""
        suffix = " ..." if partial else ""

        if text:
            log_line = f"[{time_str}]{label_prefix} {text}{suffix}"
        else:
            log_line = f"[{time_str}]{label_prefix} (unintelligible){suffix}"

        # Print to terminal
        logger.info("%s", log_line)

        # Forward to UI callback
        if self._ui_callback is not None:
            display_text = text if text else "(unintelligible)"
            if suffix:
                display_text += suffix
            self._ui_callback(time_str, self._label or "", display_text)

        # Write to log file
        if self._log_file:
            self._log_file.write(log_line + "\n")
            self._log_file.flush()

        self._transcription_count += 1

    def _transcribe(self, audio: np.ndarray) -> str | None:
        """Run faster-whisper on an audio buffer.

        Args:
            audio: Float32 numpy array at self.sample_rate Hz.

        Returns:
            Transcribed text, empty string if nothing detected,
            or None if transcription failed.
        """
        try:
            # Preprocess: bandpass, noise reduce, normalize, resample to 16kHz
            audio = _preprocess_for_whisper(audio, self.sample_rate)

            initial_prompt = (
                self._prompt if self._prompt is not None else MOTORSPORT_PROMPT
            )
            texts = _run_whisper(
                self._model, audio, self.language, initial_prompt=initial_prompt
            )
            return " ".join(texts)
        except Exception as e:
            logger.error("Transcription error: %s: %s", type(e).__name__, e)
            return None

    def close(self) -> None:
        """Flush any remaining buffer and close the log file."""
        if self._squelch_open and self._buffer:
            self._flush_buffer(partial=False)

        if self._log_file:
            self._log_file.close()
            self._log_file = None

    @property
    def transcription_count(self) -> int:
        """Number of transmissions transcribed so far."""
        return self._transcription_count

    @property
    def label(self) -> str | None:
        """Channel label, or None if not set."""
        return self._label


def transcribe_file(
    audio_path: str | Path,
    model_size: str = "auto",
    language: str = "en",
    log_path: str | Path | None = None,
    label: str | None = None,
    prompt: str | None = None,
) -> str:
    """Transcribe a pre-recorded audio file.

    Reads a WAV file, runs faster-whisper on the entire audio,
    and returns the transcription text. Optionally writes a log file.

    Args:
        audio_path: Path to the audio file (WAV).
        model_size: Whisper model size ('auto', 'tiny', 'base', etc.).
        language: Language code for transcription.
        log_path: Optional path for a transcript log file.
        label: Optional channel label for log output.
        prompt: Custom initial prompt for Whisper. None uses the
            default MOTORSPORT_PROMPT.

    Returns:
        Transcribed text as a string.

    Raises:
        FileNotFoundError: If audio_path does not exist.
        RuntimeError: If faster-whisper is not installed.
    """
    import soundfile as sf

    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    _check_faster_whisper()

    if model_size == "auto":
        model_size = detect_model_size()

    # Load audio file
    audio_data, file_sample_rate = sf.read(str(audio_path), dtype="float32")

    # Convert stereo to mono if needed
    if audio_data.ndim > 1:
        audio_data = audio_data.mean(axis=1)

    # Preprocess: bandpass, noise reduce, normalize, resample to 16kHz
    audio_data = _preprocess_for_whisper(audio_data, file_sample_rate)

    # Load model (from cache or fresh) and transcribe
    if model_size in _MODEL_CACHE:
        model = _MODEL_CACHE[model_size]
    else:
        from faster_whisper import WhisperModel as FWModel

        device = _detect_device()
        compute_type = "float16" if device == "cuda" else "int8"

        logger.info(
            "Loading Whisper model '%s' on %s (%s)...", model_size, device, compute_type
        )
        model = FWModel(model_size, device=device, compute_type=compute_type)
        _MODEL_CACHE[model_size] = model
        logger.info("Whisper model loaded.")

    try:
        initial_prompt = prompt if prompt is not None else MOTORSPORT_PROMPT
        texts = _run_whisper(model, audio_data, language, initial_prompt=initial_prompt)
        full_text = " ".join(texts) if texts else "(unintelligible)"
    except Exception as e:
        logger.error("Transcription error: %s: %s", type(e).__name__, e)
        full_text = "(transcription failed)"

    # Write log file if requested
    if log_path:
        log_path = Path(log_path)
        label_part = f" | Channel: {label}" if label else ""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = (
            f"# vtms-sdr transcription log\n"
            f"# File: {audio_path.name}{label_part} | Transcribed: {now}\n\n"
        )
        label_prefix = f" [{label}]" if label else ""
        log_line = f"[00:00:00]{label_prefix} {full_text}\n"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(header)
            f.write(log_line)

    return full_text
