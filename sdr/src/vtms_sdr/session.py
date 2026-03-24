"""Recording session orchestration for vtms-sdr.

Extracts the core recording pipeline from the CLI into a reusable module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .utils import format_frequency, iq_power_db

if TYPE_CHECKING:
    from .demod import Demodulator
    from .monitor import AudioMonitor, MonitorUI
    from .recorder import AudioRecorder
    from .sdr import SDRDevice
    from .state import StateManager
    from .transcriber import Transcriber

logger = logging.getLogger(__name__)

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
    dcs_code: int | None = None
    state_manager: StateManager | None = None


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
        sm = cfg.state_manager
        try:
            with SDRDevice(device_index=cfg.device) as sdr:
                sdr.configure(center_freq=cfg.freq, gain=cfg.gain, ppm=cfg.ppm)

                # Publish initial state through StateManager
                if sm is not None:
                    sm.update("freq", cfg.freq)
                    sm.update("mod", cfg.mod)
                    sm.update("gain", cfg.gain)
                    sm.update("squelch_db", cfg.squelch_db)
                    sm.update("status", "recording")

                demod = Demodulator.create(cfg.mod, sample_rate=sdr.sample_rate)
                # Mutable holder so auto-tune can swap the demodulator
                # mid-session from the audio_stream generator.
                demod_holder = [demod]

                if cfg.transcriber:
                    cfg.transcriber.write_log_header(
                        format_frequency(cfg.freq), cfg.mod
                    )

                def audio_stream():
                    for iq_block in sdr.stream():
                        iq_pwr = iq_power_db(iq_block)
                        # Publish signal power to StateManager
                        if sm is not None:
                            sm.update("signal_power", float(iq_pwr))
                        audio = demod_holder[0].demodulate(iq_block)
                        # Include pre-HP audio if the demodulator provides it
                        pre_hp = getattr(demod_holder[0], "pre_hp_audio", None)
                        if pre_hp is not None:
                            yield (iq_pwr, audio, pre_hp)
                        else:
                            yield (iq_pwr, audio)

                if cfg.monitor:
                    stats = self._run_with_monitor(cfg, audio_stream, sdr, demod_holder)
                else:
                    stats = self._run_headless(cfg, audio_stream)

            return stats

        finally:
            # Publish stopped status before cleanup
            if sm is not None:
                sm.update("status", "stopped")
            if cfg.transcriber:
                cfg.transcriber.close()

    def _run_headless(self, cfg: RecordConfig, audio_stream) -> dict:
        """Record without a TUI monitor."""
        from .recorder import AudioRecorder

        dcs_decoder = None
        if cfg.dcs_code is not None:
            from .dcs import DCSDecoder

            dcs_decoder = DCSDecoder(cfg.dcs_code)

        recorder = AudioRecorder(
            output_path=cfg.output_path,
            audio_format=cfg.audio_format,
            squelch_db=cfg.squelch_db,
            transcriber=cfg.transcriber,
            audio_monitor=cfg.monitor,
            dcs_decoder=dcs_decoder,
        )
        return recorder.record(audio_stream(), duration=cfg.duration)

    def _run_with_monitor(
        self,
        cfg: RecordConfig,
        audio_stream,
        sdr_device=None,
        demod_holder=None,
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

            dcs_decoder = None
            if cfg.dcs_code is not None:
                from .dcs import DCSDecoder

                dcs_decoder = DCSDecoder(cfg.dcs_code)

            recorder = AudioRecorder(
                output_path=cfg.output_path,
                audio_format=cfg.audio_format,
                squelch_db=cfg.squelch_db,
                transcriber=cfg.transcriber,
                audio_monitor=cfg.monitor,
                dcs_decoder=dcs_decoder,
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

            def autotune_stream():
                """Wraps audio_stream to intercept auto-tune requests."""
                from .autotune import classify_signal
                from .demod import Demodulator

                for iq_pwr, audio in audio_stream():
                    # Check if auto-tune was requested by the UI thread
                    if (
                        monitor_ui._autotune_requested
                        and sdr_device is not None
                        and demod_holder is not None
                    ):
                        monitor_ui._autotune_requested = False
                        try:
                            # Grab a fresh IQ block for analysis
                            iq_block = sdr_device.read_samples()
                            result = classify_signal(iq_block, sdr_device.sample_rate)

                            # Apply gain
                            sdr_device.set_gain(result.gain)
                            monitor_ui.gain = result.gain

                            # Apply squelch
                            recorder.squelch_db = result.squelch_db
                            monitor_ui.squelch_db = result.squelch_db

                            # Swap demodulator if modulation changed
                            if result.modulation != monitor_ui.mod:
                                demod_holder[0] = Demodulator.create(
                                    result.modulation,
                                    sample_rate=sdr_device.sample_rate,
                                )
                                monitor_ui.mod = result.modulation

                            monitor_ui.set_autotune_status(result.summary())
                            logger.info("Auto-tune applied: %s", result.summary())

                        except Exception as e:
                            logger.warning("Auto-tune failed: %s", e)
                            monitor_ui.set_autotune_status(f"Auto-tune failed: {e}")

                    yield (iq_pwr, audio)

            def record_func():
                return recorder.record(
                    autotune_stream(),
                    duration=cfg.duration,
                    progress_callback=monitor_ui.update_progress,
                )

            return monitor_ui.launch(record_func)
        finally:
            cfg.monitor.stop()
