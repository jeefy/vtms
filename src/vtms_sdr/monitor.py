"""Live audio monitoring via sounddevice for real-time playback during recording."""

from __future__ import annotations

import curses
import queue
import signal
import threading
import time
from pathlib import Path

import numpy as np

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .sdr import SDRDevice
    from .recorder import AudioRecorder

try:
    import sounddevice as sd
except OSError:
    # PortAudio not available - create a stub so module can be imported
    sd = None  # type: ignore[assignment]

__all__ = [
    "AudioMonitor",
    "MonitorUI",
]


class AudioMonitor:
    """Manages real-time audio playback through speakers/headphones.

    Uses sounddevice OutputStream with a queue-based callback model.
    Audio blocks are fed in from the recorder and played back in real-time.
    """

    MAX_QUEUE_SIZE = 50  # ~5s of audio at ~100ms blocks

    def __init__(
        self, sample_rate: int = 48000, volume: float = 0.5, device: int | None = None
    ) -> None:
        self.sample_rate = sample_rate
        self._volume = max(0.0, min(1.0, volume))
        self._device = device
        self._stream = None
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=self.MAX_QUEUE_SIZE)
        self._remainder: np.ndarray | None = None

    @property
    def volume(self) -> float:
        """Current playback volume (0.0 to 1.0)."""
        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        """Set playback volume, clamped to [0.0, 1.0]."""
        self._volume = max(0.0, min(1.0, value))

    def feed(self, audio: np.ndarray) -> None:
        """Queue an audio block for playback.

        Makes a copy of the audio to avoid mutation issues.
        Drops the block silently if the queue is full (prevents memory growth).
        """
        try:
            self._queue.put_nowait(audio.copy())
        except queue.Full:
            # Drop the block - better than unbounded memory growth
            pass

    def _audio_callback(
        self, outdata: np.ndarray, frames: int, time_info, status
    ) -> None:
        """Sounddevice output callback - fills output buffer from queue.

        Called from PortAudio's audio thread. Must not block.
        """
        filled = 0
        vol = self._volume

        # Use any leftover audio from previous callback
        if self._remainder is not None:
            n = min(len(self._remainder), frames)
            outdata[:n, 0] = self._remainder[:n] * vol
            filled = n
            if n < len(self._remainder):
                self._remainder = self._remainder[n:]
            else:
                self._remainder = None

        # Pull blocks from queue until output buffer is full
        while filled < frames:
            try:
                block = self._queue.get_nowait()
            except queue.Empty:
                break

            needed = frames - filled
            n = min(len(block), needed)
            outdata[filled : filled + n, 0] = block[:n] * vol
            filled += n

            if n < len(block):
                self._remainder = block[n:]

        # Fill any remaining space with silence
        if filled < frames:
            outdata[filled:, 0] = 0.0

    def start(self) -> None:
        """Open and start the audio output stream."""
        if sd is None:
            raise OSError(
                "PortAudio library not found. Install portaudio "
                "(e.g. 'sudo apt install libportaudio2' or 'brew install portaudio')"
            )
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=self._audio_callback,
            device=self._device,
        )
        self._stream.start()

    def stop(self) -> None:
        """Stop and close the audio output stream."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def __enter__(self):
        """Context manager entry - starts the stream."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - stops the stream."""
        self.stop()
        return False


class MonitorUI:
    """Curses-based terminal UI for live monitoring during recording.

    Displays: frequency, elapsed time, squelch status, volume control,
    and live transcription output. Handles keyboard input for volume
    adjustment and quit.

    Thread-safe: update methods can be called from any thread.
    """

    MAX_TRANSCRIPTION_LINES = 100
    VOLUME_STEP = 0.05
    SQUELCH_STEP = 1.0
    GAIN_STEP = 1.0
    GAIN_DEFAULT = 20.0
    GAIN_MIN = 0.0
    GAIN_MAX = 50.0
    PPM_STEP = 1
    AUTOTUNE_STATUS_DURATION = 5.0  # seconds to show auto-tune result

    # Color pair constants
    COLOR_TITLE = 1
    COLOR_SQUELCH_OPEN = 2
    COLOR_SQUELCH_CLOSED = 3
    COLOR_VOLUME = 4
    COLOR_FOOTER = 5
    COLOR_TRANSCRIPTION = 6
    COLOR_AUTOTUNE = 7

    def __init__(
        self,
        freq: int,
        mod: str,
        output_path: str | Path,
        squelch_db: float,
        audio_monitor: AudioMonitor,
        *,
        model_size: str | None = None,
        gain: str | float | None = None,
        ppm: int | None = None,
        sdr_device: SDRDevice | None = None,
        recorder: AudioRecorder | None = None,
    ) -> None:
        self.freq = freq
        self.mod = mod
        self.output_path = str(output_path)
        self.squelch_db = squelch_db
        self._audio_monitor = audio_monitor
        self.model_size = model_size
        self.gain = gain
        self.ppm = ppm
        self.sdr_device = sdr_device
        self.recorder = recorder
        self.stopped = False
        self._has_colors = False
        self._autotune_requested = False
        self._autotune_status: str | None = None
        self._autotune_status_time: float = 0.0

        self._lock = threading.Lock()
        self._state: dict = {
            "elapsed": 0.0,
            "audio_duration": 0.0,
            "squelch_open": False,
            "power_db": -100.0,
            "transcriptions": [],
        }

    def update_progress(
        self, elapsed: float, samples_written: int, sample_rate: int
    ) -> None:
        """Update recording progress (thread-safe)."""
        audio_duration = samples_written / sample_rate if sample_rate > 0 else 0.0
        with self._lock:
            self._state["elapsed"] = elapsed
            self._state["audio_duration"] = audio_duration

    def update_squelch(self, is_open: bool, power_db: float) -> None:
        """Update squelch state (thread-safe)."""
        with self._lock:
            self._state["squelch_open"] = is_open
            self._state["power_db"] = power_db

    def add_transcription(self, timestamp: str, label: str, text: str) -> None:
        """Add a transcription line to the log (thread-safe)."""
        with self._lock:
            self._state["transcriptions"].append((timestamp, label, text))
            # Trim to max size
            if len(self._state["transcriptions"]) > self.MAX_TRANSCRIPTION_LINES:
                self._state["transcriptions"] = self._state["transcriptions"][
                    -self.MAX_TRANSCRIPTION_LINES :
                ]

    def set_autotune_status(self, status: str) -> None:
        """Set the auto-tune status message (thread-safe).

        The status line auto-clears after AUTOTUNE_STATUS_DURATION seconds.
        """
        self._autotune_status = status
        self._autotune_status_time = time.time()

    def _init_colors(self) -> None:
        """Initialize curses color pairs if the terminal supports colors.

        Sets self._has_colors to True on success, False on any curses error.
        """
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(self.COLOR_TITLE, curses.COLOR_CYAN, -1)
            curses.init_pair(self.COLOR_SQUELCH_OPEN, curses.COLOR_GREEN, -1)
            curses.init_pair(self.COLOR_SQUELCH_CLOSED, curses.COLOR_RED, -1)
            curses.init_pair(self.COLOR_VOLUME, curses.COLOR_YELLOW, -1)
            curses.init_pair(self.COLOR_FOOTER, curses.COLOR_CYAN, -1)
            curses.init_pair(self.COLOR_TRANSCRIPTION, curses.COLOR_WHITE, -1)
            curses.init_pair(self.COLOR_AUTOTUNE, curses.COLOR_MAGENTA, -1)
            self._has_colors = True
        except curses.error:
            self._has_colors = False

    def _handle_sigint(self) -> None:
        """Handle SIGINT (Ctrl+C) for graceful shutdown.

        Sets the stopped flag and signals the recorder to stop if present.
        """
        self.stopped = True
        if self.recorder is not None:
            self.recorder._stopped.set()

    def _handle_key(self, key: int) -> None:
        """Handle a keyboard input character."""
        if key == ord("+") or key == ord("="):
            self._audio_monitor.volume = min(
                1.0, self._audio_monitor.volume + self.VOLUME_STEP
            )
        elif key == ord("-"):
            self._audio_monitor.volume = max(
                0.0, self._audio_monitor.volume - self.VOLUME_STEP
            )
        elif key == ord("s"):
            self.squelch_db -= self.SQUELCH_STEP
            if self.recorder is not None:
                self.recorder.squelch_db = self.squelch_db
        elif key == ord("S"):
            self.squelch_db += self.SQUELCH_STEP
            if self.recorder is not None:
                self.recorder.squelch_db = self.squelch_db
        elif key == ord("g"):
            if self.gain is not None:
                if self.gain == "auto":
                    self.gain = self.GAIN_DEFAULT
                self.gain = max(self.GAIN_MIN, self.gain - self.GAIN_STEP)
                if self.sdr_device is not None:
                    self.sdr_device.set_gain(self.gain)
        elif key == ord("G"):
            if self.gain is not None:
                if self.gain == "auto":
                    self.gain = self.GAIN_DEFAULT
                self.gain = min(self.GAIN_MAX, self.gain + self.GAIN_STEP)
                if self.sdr_device is not None:
                    self.sdr_device.set_gain(self.gain)
        elif key == ord("p"):
            if self.ppm is not None:
                self.ppm -= self.PPM_STEP
                if self.sdr_device is not None:
                    self.sdr_device.set_ppm(self.ppm)
        elif key == ord("P"):
            if self.ppm is not None:
                self.ppm += self.PPM_STEP
                if self.sdr_device is not None:
                    self.sdr_device.set_ppm(self.ppm)
        elif key == ord("a") or key == ord("A"):
            self._autotune_requested = True
        elif key == ord("q") or key == ord("Q"):
            self.stopped = True
            if self.recorder is not None:
                self.recorder._stopped.set()

    def _format_freq(self) -> str:
        """Format frequency in MHz."""
        mhz = self.freq / 1_000_000
        return f"{mhz:.3f} MHz"

    def _format_volume_bar(self, width: int = 20) -> str:
        """Format a volume bar with filled/empty blocks."""
        vol = self._audio_monitor.volume
        filled = round(vol * width)
        empty = width - filled
        return "\u2588" * filled + "\u2591" * empty

    def _format_power_bar(self, power_db: float, width: int = 30) -> str:
        """Format a signal power meter bar with filled/empty blocks.

        Maps the power_db range [-80, 0] to bar width.
        Values outside the range are clamped.

        Args:
            power_db: Signal power in dB (typically -80 to 0).
            width: Total bar width in characters.

        Returns:
            A string of exactly ``width`` characters using filled (█)
            and empty (░) block characters.
        """
        filled = max(0, min(width, round((power_db + 80) / 80 * width)))
        empty = width - filled
        return "\u2588" * filled + "\u2591" * empty

    def _format_elapsed(self) -> str:
        """Format elapsed time as HH:MM:SS."""
        with self._lock:
            elapsed = self._state["elapsed"]
        return time.strftime("%H:%M:%S", time.gmtime(elapsed))

    def _get_state_snapshot(self) -> dict:
        """Get a thread-safe copy of the current state."""
        with self._lock:
            return {
                "elapsed": self._state["elapsed"],
                "audio_duration": self._state["audio_duration"],
                "squelch_open": self._state["squelch_open"],
                "power_db": self._state["power_db"],
                "transcriptions": list(self._state["transcriptions"]),
            }

    def _draw(self, stdscr) -> None:
        """Draw the monitoring UI to the curses screen."""
        state = self._get_state_snapshot()
        height, width = stdscr.getmaxyx()

        # Resolve color attributes (0 when colors unavailable)
        if self._has_colors:
            attr_title = curses.color_pair(self.COLOR_TITLE) | curses.A_BOLD
            attr_squelch_open = (
                curses.color_pair(self.COLOR_SQUELCH_OPEN) | curses.A_BOLD
            )
            attr_squelch_closed = curses.color_pair(self.COLOR_SQUELCH_CLOSED)
            attr_volume = curses.color_pair(self.COLOR_VOLUME)
            attr_footer = curses.color_pair(self.COLOR_FOOTER)
            attr_transcription = curses.color_pair(self.COLOR_TRANSCRIPTION)
            attr_autotune = curses.color_pair(self.COLOR_AUTOTUNE) | curses.A_BOLD
        else:
            attr_title = 0
            attr_squelch_open = 0
            attr_squelch_closed = 0
            attr_volume = 0
            attr_footer = 0
            attr_transcription = 0
            attr_autotune = 0

        stdscr.erase()

        row = 0
        # Title
        title = " vtms-sdr Monitor "
        if width >= len(title) + 4:
            stdscr.addstr(
                row,
                0,
                f"\u250c\u2500{title}" + "\u2500" * (width - len(title) - 4) + "\u2510",
                attr_title,
            )
        row += 1

        # Frequency and modulation
        freq_line = (
            f"  Frequency: {self._format_freq()}   Modulation: {self.mod.upper()}"
        )
        stdscr.addstr(row, 0, freq_line[: width - 1], attr_title)
        row += 1

        # Recording duration and file
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(state["elapsed"]))
        audio_str = time.strftime("%H:%M:%S", time.gmtime(state["audio_duration"]))
        out_name = Path(self.output_path).name
        if len(out_name) > width - 40:
            out_name = out_name[: width - 43] + "..."
        rec_line = f"  Recording: {elapsed_str}   Audio: {audio_str}   File: {out_name}"
        stdscr.addstr(row, 0, rec_line[: width - 1], attr_title)
        row += 1

        # Signal power meter and squelch status (two lines)
        squelch_status = "OPEN" if state["squelch_open"] else "CLOSED"
        power_bar = self._format_power_bar(state["power_db"], width=30)
        signal_line = f"  Signal: [{power_bar}] {squelch_status}   [s/S \u00b11 dB]"
        power_line = (
            f"  Power: {state['power_db']:.1f} dB  Squelch: {self.squelch_db:.1f} dB"
        )
        if state["squelch_open"]:
            attr_squelch = attr_squelch_open
        else:
            attr_squelch = attr_squelch_closed
        stdscr.addstr(row, 0, signal_line[: width - 1], attr_squelch)
        row += 1
        stdscr.addstr(row, 0, power_line[: width - 1], attr_squelch)
        row += 1

        # Gain and PPM row (only if provided)
        settings_parts = []
        if self.gain is not None:
            gain_str = "auto" if self.gain == "auto" else f"{self.gain:.1f} dB"
            settings_parts.append(f"Gain: {gain_str} [g/G \u00b11]")
        if self.ppm is not None:
            settings_parts.append(f"PPM: {self.ppm} [p/P \u00b11]")
        if settings_parts:
            settings_line = "  " + "   ".join(settings_parts)
            stdscr.addstr(row, 0, settings_line[: width - 1], attr_title)
            row += 1

        # Whisper model (only if provided)
        if self.model_size is not None:
            model_line = f"  Model: {self.model_size}"
            stdscr.addstr(row, 0, model_line[: width - 1], attr_title)
            row += 1

        # Auto-tune status (shown briefly after auto-tune completes)
        if self._autotune_status is not None:
            elapsed_since = time.time() - self._autotune_status_time
            if elapsed_since < self.AUTOTUNE_STATUS_DURATION:
                autotune_line = f"  {self._autotune_status}"
                stdscr.addstr(row, 0, autotune_line[: width - 1], attr_autotune)
                row += 1
            else:
                self._autotune_status = None

        # Volume
        vol_pct = int(self._audio_monitor.volume * 100)
        vol_bar = self._format_volume_bar(width=min(20, width - 30))
        vol_line = f"  Volume:  {vol_bar} {vol_pct}%   (+/- to adjust)"
        stdscr.addstr(row, 0, vol_line[: width - 1], attr_volume)
        row += 2

        # Transcription log header
        if row < height - 2:
            header = "  --- Transcription Log ---"
            stdscr.addstr(row, 0, header[: width - 1], attr_title)
            row += 1

        # Transcription lines (show as many as fit)
        available_rows = height - row - 2  # Leave room for footer
        transcriptions = state["transcriptions"]
        if available_rows > 0:
            visible = transcriptions[-available_rows:]
            for ts, label, text in visible:
                if row >= height - 2:
                    break
                if label:
                    line = f"  [{ts}] [{label}] {text}"
                else:
                    line = f"  [{ts}] {text}"
                stdscr.addstr(row, 0, line[: width - 1], attr_transcription)
                row += 1

        # Footer (updated with all key hints)
        footer_row = height - 1
        footer = "  q quit | +/- vol | s/S squelch | g/G gain | p/P ppm | a auto-tune"
        try:
            stdscr.addstr(footer_row, 0, footer[: width - 1], attr_footer)
        except curses.error:
            pass  # Terminal too small

        stdscr.refresh()

    def launch(self, record_func) -> dict:
        """Launch the curses TUI for monitoring.

        Wraps curses.wrapper to handle terminal setup/teardown, then
        runs the monitor UI with the recording function in a background thread.

        Args:
            record_func: Callable that performs the recording.

        Returns:
            The result dict from record_func.
        """
        return curses.wrapper(self.run, record_func)

    def run(self, stdscr, record_func) -> dict:
        """Run the monitor UI with curses.

        Args:
            stdscr: Curses window (from curses.wrapper).
            record_func: Callable that performs the recording.
                         Will be called in a background thread.
                         Should accept a 'progress_callback' kwarg.

        Returns:
            The result from record_func.
        """
        curses.curs_set(0)  # Hide cursor
        stdscr.nodelay(True)  # Non-blocking input
        stdscr.timeout(100)  # Refresh at ~10Hz
        self._init_colors()

        result = [None]
        error = [None]

        def recording_thread():
            try:
                result[0] = record_func()
            except Exception as e:
                error[0] = e
            finally:
                self.stopped = True

        thread = threading.Thread(target=recording_thread, daemon=True)
        thread.start()

        # Install SIGINT handler for graceful Ctrl+C shutdown
        original_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, lambda signum, frame: self._handle_sigint())

        try:
            while not self.stopped:
                # Handle input
                try:
                    key = stdscr.getch()
                    if key != -1:
                        self._handle_key(key)
                except curses.error:
                    pass

                # Draw
                try:
                    self._draw(stdscr)
                except curses.error:
                    pass
        finally:
            signal.signal(signal.SIGINT, original_sigint)
            thread.join(timeout=5)

        if error[0] is not None:
            raise error[0]

        return result[0]
