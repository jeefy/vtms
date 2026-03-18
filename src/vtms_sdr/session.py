"""Recording session orchestration for vtms-sdr.

Extracts the core recording pipeline from the CLI into a reusable module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .utils import format_frequency, iq_power_db

if TYPE_CHECKING:
    from .demod import Demodulator
    from .monitor import AudioMonitor
    from .recorder import AudioRecorder
    from .sdr import SDRDevice
    from .transcriber import Transcriber

__all__ = [
    "RecordConfig",
    "RecordingSession",
]


@dataclass
class RecordConfig:
    """Resolved configuration for a recording session."""

    freq: int
    mod: str
    output_path: Path
    audio_format: str
    duration: float | None = None
    gain: str | float = "auto"
    squelch_db: float = -30.0
    device: int = 0
    ppm: int = 0
    transcriber: Transcriber | None = None
    monitor: AudioMonitor | None = None
    volume: float = 0.5
    label: str | None = None


class RecordingSession:
    """Orchestrates an SDR recording session.

    Separates the recording pipeline from CLI concerns (Click parsing,
    preset resolution, output formatting).
    """

    def __init__(self, config: RecordConfig) -> None:
        self.config = config

    def run(self) -> dict:
        """Execute the recording session.

        Returns:
            Stats dict from the recorder with keys:
            file, audio_duration_sec, file_size_bytes.
        """
        from .demod import Demodulator
        from .sdr import SDRDevice

        cfg = self.config
        try:
            with SDRDevice(device_index=cfg.device) as sdr:
                sdr.configure(center_freq=cfg.freq, gain=cfg.gain, ppm=cfg.ppm)

                demod = Demodulator.create(cfg.mod, sample_rate=sdr.sample_rate)

                if cfg.transcriber:
                    cfg.transcriber.write_log_header(
                        format_frequency(cfg.freq), cfg.mod
                    )

                def audio_stream():
                    for iq_block in sdr.stream():
                        iq_pwr = iq_power_db(iq_block)
                        yield (iq_pwr, demod.demodulate(iq_block))

                if cfg.monitor:
                    stats = self._run_with_monitor(cfg, audio_stream, sdr)
                else:
                    stats = self._run_headless(cfg, audio_stream)

            return stats

        finally:
            if cfg.transcriber:
                cfg.transcriber.close()

    def _run_headless(self, cfg: RecordConfig, audio_stream) -> dict:
        """Record without a TUI monitor."""
        from .recorder import AudioRecorder

        recorder = AudioRecorder(
            output_path=cfg.output_path,
            audio_format=cfg.audio_format,
            squelch_db=cfg.squelch_db,
            transcriber=cfg.transcriber,
            audio_monitor=cfg.monitor,
        )
        return recorder.record(audio_stream(), duration=cfg.duration)

    def _run_with_monitor(
        self, cfg: RecordConfig, audio_stream, sdr_device=None
    ) -> dict:
        """Record with the TUI monitor UI."""
        from .monitor import MonitorUI
        from .recorder import AudioRecorder

        cfg.monitor.start()
        try:
            # Extract model_size from transcriber if available
            model_size = None
            if cfg.transcriber is not None:
                model_size = getattr(cfg.transcriber, "model_size", None)

            recorder = AudioRecorder(
                output_path=cfg.output_path,
                audio_format=cfg.audio_format,
                squelch_db=cfg.squelch_db,
                transcriber=cfg.transcriber,
                audio_monitor=cfg.monitor,
            )

            monitor_ui = MonitorUI(
                freq=cfg.freq,
                mod=cfg.mod,
                output_path=cfg.output_path,
                squelch_db=cfg.squelch_db,
                audio_monitor=cfg.monitor,
                model_size=model_size,
                gain=cfg.gain,
                ppm=cfg.ppm,
                sdr_device=sdr_device,
                recorder=recorder,
            )

            # Wire callbacks after both objects are created
            recorder._squelch_callback = monitor_ui.update_squelch

            if cfg.transcriber is not None:
                cfg.transcriber._ui_callback = monitor_ui.add_transcription

            def record_func():
                return recorder.record(
                    audio_stream(),
                    duration=cfg.duration,
                    progress_callback=monitor_ui.update_progress,
                )

            return monitor_ui.launch(record_func)
        finally:
            cfg.monitor.stop()
