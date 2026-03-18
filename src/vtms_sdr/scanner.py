"""Frequency scanning: active signal detection and clear channel finding."""

from __future__ import annotations

import logging
import signal
import sys
import time
from dataclasses import dataclass, field

import numpy as np

from .sdr import SDRDevice, DEFAULT_SAMPLE_RATE
from .utils import (
    format_frequency,
    generate_frequency_list,
    power_to_db,
    estimate_scan_time,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ChannelScore",
    "FrequencyScanner",
    "ScanReport",
    "ScanResult",
    "compute_channel_scores",
    "format_recommend_report",
    "format_scan_csv",
    "format_scan_report",
]


@dataclass
class ScanResult:
    """Result for a single scanned frequency."""

    frequency_hz: int
    power_db: float
    active: bool
    active_count: int = 0
    total_passes: int = 0

    @property
    def frequency_str(self) -> str:
        return format_frequency(self.frequency_hz)


@dataclass
class ScanReport:
    """Complete scan report with results and metadata."""

    mode: str  # "active" or "clear"
    start_hz: int
    end_hz: int
    step_hz: int
    threshold_db: float
    duration_sec: float
    results: list[ScanResult] = field(default_factory=list)
    scan_passes: int = 0

    @property
    def active_frequencies(self) -> list[ScanResult]:
        return [r for r in self.results if r.active]

    @property
    def clear_frequencies(self) -> list[ScanResult]:
        return [r for r in self.results if not r.active]


@dataclass
class ChannelScore:
    """Ranked channel recommendation with quality score."""

    frequency_hz: int
    max_power_db: float
    active_ratio: float
    score: float

    @property
    def frequency_str(self) -> str:
        return format_frequency(self.frequency_hz)

    @property
    def status(self) -> str:
        if self.active_ratio == 0.0:
            return "CLEAR"
        elif self.active_ratio > 0.5:
            return "BUSY"
        else:
            return "INTERMITTENT"


def compute_channel_scores(report: ScanReport) -> list[ChannelScore]:
    """Compute quality scores for all channels and return sorted best-first.

    Score formula: (1 - active_ratio) * 100 - power_penalty
    where power_penalty maps max_power_db into 0..10 range relative to threshold.
    """
    if report.scan_passes == 0:
        return [
            ChannelScore(
                frequency_hz=r.frequency_hz,
                max_power_db=r.power_db,
                active_ratio=0.0,
                score=0.0,
            )
            for r in report.results
        ]

    # Find the power range across all results for normalization
    all_powers = [r.power_db for r in report.results]
    min_power = min(all_powers) if all_powers else -100.0
    power_range = report.threshold_db - min_power
    if power_range <= 0:
        power_range = 1.0  # avoid division by zero

    scores = []
    for r in report.results:
        active_ratio = r.active_count / r.total_passes if r.total_passes > 0 else 0.0

        # Power penalty: 0 for quietest channel, up to 10 for threshold-level
        power_normalized = (r.power_db - min_power) / power_range
        power_penalty = min(max(power_normalized, 0.0), 1.0) * 10.0

        score = (1.0 - active_ratio) * 100.0 - power_penalty

        scores.append(
            ChannelScore(
                frequency_hz=r.frequency_hz,
                max_power_db=r.power_db,
                active_ratio=round(active_ratio, 4),
                score=round(score, 1),
            )
        )

    scores.sort(key=lambda s: s.score, reverse=True)
    return scores


class FrequencyScanner:
    """Scans frequency ranges to find active or clear channels.

    Supports two modes:
    - Active scan: Single pass, report frequencies with signals above threshold.
    - Clear scan: Multiple passes over a duration, report frequencies that
                  stayed below threshold the entire time.
    """

    def __init__(
        self,
        sdr: SDRDevice,
        threshold_db: float = -30.0,
        dwell_samples: int = 65_536,
        gain: str | float = "auto",
        ppm: int = 0,
    ):
        """Initialize the frequency scanner.

        Args:
            sdr: An open SDRDevice instance.
            threshold_db: Power threshold in dB for signal detection.
            dwell_samples: Number of samples to collect per frequency for
                          power measurement. More samples = more accurate
                          but slower scan.
            gain: SDR gain in dB, or 'auto' for automatic gain.
            ppm: Crystal oscillator frequency correction in PPM.
        """
        self.sdr = sdr
        self.threshold_db = threshold_db
        self.dwell_samples = dwell_samples
        self._gain = gain
        self._ppm = ppm
        self._stopped = False

    def measure_power(self, freq_hz: int) -> float:
        """Measure signal power at a given frequency.

        Tunes the SDR, collects samples, and computes average power in dB.

        Args:
            freq_hz: Frequency to measure in Hz.

        Returns:
            Power level in dB.
        """
        self.sdr.configure(
            center_freq=freq_hz,
            sample_rate=DEFAULT_SAMPLE_RATE,
            gain=self._gain,
            ppm=self._ppm,
        )

        # Discard first read for PLL settling
        self.sdr.read_samples(self.dwell_samples)

        # Measurement read
        samples = self.sdr.read_samples(self.dwell_samples)

        # Compute power spectral density using FFT
        fft_data = np.fft.fft(samples)
        power_spectrum = np.abs(fft_data) ** 2
        avg_power = np.mean(power_spectrum)

        return power_to_db(avg_power)

    def scan_active(
        self,
        start_hz: int,
        end_hz: int,
        step_hz: int,
    ) -> ScanReport:
        """Scan a frequency range and report active frequencies.

        Single pass through all frequencies, measuring power at each.

        Args:
            start_hz: Start frequency in Hz.
            end_hz: End frequency in Hz.
            step_hz: Step size in Hz.

        Returns:
            ScanReport with results for each frequency.
        """
        frequencies = generate_frequency_list(start_hz, end_hz, step_hz)
        num_channels = len(frequencies)

        est_time = estimate_scan_time(num_channels)
        logger.info(
            "Scanning %s - %s in %s steps (%d channels). Estimated time: %.1fs",
            format_frequency(start_hz),
            format_frequency(end_hz),
            format_frequency(step_hz),
            num_channels,
            est_time,
        )

        self._stopped = False
        self._install_signal_handler()

        report = ScanReport(
            mode="active",
            start_hz=start_hz,
            end_hz=end_hz,
            step_hz=step_hz,
            threshold_db=self.threshold_db,
            duration_sec=0,
            scan_passes=1,
        )

        start_time = time.time()

        try:
            for i, freq in enumerate(frequencies):
                if self._stopped:
                    break

                power_db = self.measure_power(freq)
                is_active = power_db > self.threshold_db

                report.results.append(
                    ScanResult(
                        frequency_hz=freq,
                        power_db=round(power_db, 1),
                        active=is_active,
                    )
                )

                # Progress indicator
                pct = (i + 1) / num_channels * 100
                status = "ACTIVE" if is_active else "      "
                sys.stderr.write(
                    f"\r[{pct:5.1f}%] {format_frequency(freq)}: "
                    f"{power_db:6.1f} dB {status}"
                )
                sys.stderr.flush()

        finally:
            self._restore_signal_handler()

        report.duration_sec = time.time() - start_time
        sys.stderr.write("\n")  # Newline after progress

        return report

    def scan_clear(
        self,
        start_hz: int,
        end_hz: int,
        step_hz: int,
        duration_sec: float = 300.0,
    ) -> ScanReport:
        """Scan for clear (unused) frequencies over a time period.

        Repeatedly scans the frequency range for the given duration.
        Any frequency that exceeds the threshold at any point is marked
        as "active". Frequencies that stay below threshold for the
        entire duration are reported as "clear".

        Args:
            start_hz: Start frequency in Hz.
            end_hz: End frequency in Hz.
            step_hz: Step size in Hz.
            duration_sec: How long to monitor in seconds.

        Returns:
            ScanReport with clear frequencies marked as not active.
        """
        frequencies = generate_frequency_list(start_hz, end_hz, step_hz)
        num_channels = len(frequencies)

        single_pass_time = estimate_scan_time(num_channels)
        est_passes = max(1, int(duration_sec / single_pass_time))

        logger.info(
            "Clear channel scan: %s - %s in %s steps (%d channels).\n"
            "Monitoring for %.0fs (~%d passes, ~%.1fs each).\n"
            "Frequencies with signal above %.0f dB at any point will be excluded.",
            format_frequency(start_hz),
            format_frequency(end_hz),
            format_frequency(step_hz),
            num_channels,
            duration_sec,
            est_passes,
            single_pass_time,
            self.threshold_db,
        )

        self._stopped = False
        self._install_signal_handler()

        # Track which frequencies have been seen as active at any point
        ever_active: set[int] = set()
        # Track max power seen for each frequency
        max_power: dict[int, float] = {f: -100.0 for f in frequencies}

        start_time = time.time()
        scan_passes = 0

        try:
            while not self._stopped:
                elapsed = time.time() - start_time
                if elapsed >= duration_sec:
                    break

                scan_passes += 1
                remaining = duration_sec - elapsed

                sys.stderr.write(
                    f"\rPass {scan_passes} | "
                    f"{elapsed:.0f}/{duration_sec:.0f}s | "
                    f"Active: {len(ever_active)}/{num_channels} | "
                    f"Clear: {num_channels - len(ever_active)}"
                )
                sys.stderr.flush()

                for freq in frequencies:
                    if self._stopped:
                        break

                    elapsed = time.time() - start_time
                    if elapsed >= duration_sec:
                        break

                    power_db = self.measure_power(freq)

                    if power_db > max_power[freq]:
                        max_power[freq] = power_db

                    if power_db > self.threshold_db:
                        ever_active.add(freq)

        finally:
            self._restore_signal_handler()

        sys.stderr.write("\n")  # Newline after progress

        report = ScanReport(
            mode="clear",
            start_hz=start_hz,
            end_hz=end_hz,
            step_hz=step_hz,
            threshold_db=self.threshold_db,
            duration_sec=time.time() - start_time,
            scan_passes=scan_passes,
        )

        for freq in frequencies:
            report.results.append(
                ScanResult(
                    frequency_hz=freq,
                    power_db=round(max_power[freq], 1),
                    active=freq in ever_active,
                )
            )

        return report

    def scan_recommend(
        self,
        start_hz: int,
        end_hz: int,
        step_hz: int,
        duration_sec: float = 300.0,
    ) -> ScanReport:
        """Scan a frequency range and rank channels by quality.

        Repeatedly scans all frequencies for the given duration, tracking
        per-channel statistics. Each frequency gets an activity count
        (how many passes it was above threshold) and max observed power.

        Args:
            start_hz: Start frequency in Hz.
            end_hz: End frequency in Hz.
            step_hz: Step size in Hz.
            duration_sec: How long to monitor in seconds.

        Returns:
            ScanReport with mode="recommend" and per-channel statistics.
        """
        frequencies = generate_frequency_list(start_hz, end_hz, step_hz)
        num_channels = len(frequencies)

        single_pass_time = estimate_scan_time(num_channels)
        est_passes = max(1, int(duration_sec / single_pass_time))

        logger.info(
            "Channel recommendation scan: %s - %s in %s steps (%d channels).\n"
            "Monitoring for %.0fs (~%d passes, ~%.1fs each).\n"
            "Threshold: %.0f dB",
            format_frequency(start_hz),
            format_frequency(end_hz),
            format_frequency(step_hz),
            num_channels,
            duration_sec,
            est_passes,
            single_pass_time,
            self.threshold_db,
        )

        self._stopped = False
        self._install_signal_handler()

        active_count: dict[int, int] = {f: 0 for f in frequencies}
        max_power: dict[int, float] = {f: -100.0 for f in frequencies}

        start_time = time.time()
        scan_passes = 0

        try:
            while not self._stopped:
                elapsed = time.time() - start_time
                if elapsed >= duration_sec:
                    break

                scan_passes += 1
                clear_count = sum(1 for f in frequencies if active_count[f] == 0)

                sys.stderr.write(
                    f"\rPass {scan_passes} | "
                    f"{elapsed:.0f}/{duration_sec:.0f}s | "
                    f"Clear: {clear_count}/{num_channels}"
                )
                sys.stderr.flush()

                for freq in frequencies:
                    if self._stopped:
                        break

                    elapsed = time.time() - start_time
                    if elapsed >= duration_sec:
                        break

                    power_db = self.measure_power(freq)

                    if power_db > max_power[freq]:
                        max_power[freq] = power_db

                    if power_db > self.threshold_db:
                        active_count[freq] += 1

        finally:
            self._restore_signal_handler()

        sys.stderr.write("\n")

        report = ScanReport(
            mode="recommend",
            start_hz=start_hz,
            end_hz=end_hz,
            step_hz=step_hz,
            threshold_db=self.threshold_db,
            duration_sec=time.time() - start_time,
            scan_passes=scan_passes,
        )

        for freq in frequencies:
            report.results.append(
                ScanResult(
                    frequency_hz=freq,
                    power_db=round(max_power[freq], 1),
                    active=active_count[freq] > 0,
                    active_count=active_count[freq],
                    total_passes=scan_passes,
                )
            )

        return report

    def _install_signal_handler(self) -> None:
        """Install SIGINT handler for graceful shutdown."""
        self._original_sigint = signal.getsignal(signal.SIGINT)

        def handler(signum, frame):
            logger.info("Stopping scan...")
            self._stopped = True

        signal.signal(signal.SIGINT, handler)

    def _restore_signal_handler(self) -> None:
        """Restore original SIGINT handler."""
        if hasattr(self, "_original_sigint") and self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)


def format_scan_report(report: ScanReport) -> str:
    """Format a scan report as a human-readable table.

    Args:
        report: ScanReport to format.

    Returns:
        Formatted string with table of results.
    """
    lines = []

    # Header
    lines.append(f"Scan Report: {report.mode.upper()} mode")
    lines.append(
        f"Range: {format_frequency(report.start_hz)} - "
        f"{format_frequency(report.end_hz)} "
        f"(step: {format_frequency(report.step_hz)})"
    )
    lines.append(f"Threshold: {report.threshold_db:.0f} dB")
    lines.append(f"Duration: {report.duration_sec:.1f}s ({report.scan_passes} passes)")
    lines.append("")

    if report.mode == "active":
        active = report.active_frequencies
        lines.append(f"Active frequencies: {len(active)} / {len(report.results)}")
        lines.append("")

        if active:
            lines.append(f"{'Frequency':>15}  {'Power (dB)':>10}")
            lines.append("-" * 28)
            for r in sorted(active, key=lambda x: x.power_db, reverse=True):
                lines.append(f"{r.frequency_str:>15}  {r.power_db:>10.1f}")
        else:
            lines.append("No active frequencies found.")

    elif report.mode == "clear":
        clear = report.clear_frequencies
        lines.append(f"Clear frequencies: {len(clear)} / {len(report.results)}")
        lines.append("")

        if clear:
            lines.append(f"{'Frequency':>15}  {'Max Power (dB)':>14}")
            lines.append("-" * 32)
            for r in sorted(clear, key=lambda x: x.frequency_hz):
                lines.append(f"{r.frequency_str:>15}  {r.power_db:>14.1f}")
        else:
            lines.append("No clear frequencies found. All channels had activity.")

    return "\n".join(lines)


def format_recommend_report(report: ScanReport, top_n: int = 0) -> str:
    """Format a recommend scan report as a ranked table.

    Args:
        report: ScanReport with mode="recommend".
        top_n: Show only the top N channels. 0 = show all.

    Returns:
        Formatted string with ranked channel recommendations.
    """
    lines = []

    lines.append(f"Channel Recommendations ({report.mode.upper()} mode)")
    lines.append(
        f"Range: {format_frequency(report.start_hz)} - "
        f"{format_frequency(report.end_hz)} "
        f"(step: {format_frequency(report.step_hz)})"
    )
    lines.append(
        f"Scanned for {report.duration_sec:.1f}s "
        f"({report.scan_passes} passes), "
        f"threshold: {report.threshold_db:.0f} dB"
    )

    scores = compute_channel_scores(report)

    num_clear = sum(1 for s in scores if s.status == "CLEAR")
    num_active = len(scores) - num_clear
    lines.append(
        f"Channels scanned: {len(scores)} | Clear: {num_clear} | Active: {num_active}"
    )
    lines.append("")

    if not scores:
        lines.append("No channels scanned.")
        return "\n".join(lines)

    display = scores[:top_n] if top_n > 0 else scores

    lines.append(
        f"{'Rank':>4}  {'Frequency':>15}  {'Score':>5}  "
        f"{'Max Power':>9}  {'Active Passes':>13}  {'Status'}"
    )
    lines.append("-" * 68)

    for i, s in enumerate(display, 1):
        passes_str = (
            f"{int(s.active_ratio * report.scan_passes)}/{report.scan_passes}"
            if report.scan_passes > 0
            else "0/0"
        )
        lines.append(
            f"{i:>4}  {s.frequency_str:>15}  {s.score:>5.1f}  "
            f"{s.max_power_db:>7.1f} dB  {passes_str:>13}  {s.status}"
        )

    if top_n > 0 and top_n < len(scores):
        lines.append(f"\n(Showing top {top_n} of {len(scores)} channels)")

    return "\n".join(lines)


def format_scan_csv(report: ScanReport) -> str:
    """Format a scan report as CSV.

    Args:
        report: ScanReport to format.

    Returns:
        CSV string with header row and one row per frequency.
    """
    if report.mode == "recommend":
        lines = ["frequency_hz,frequency_str,power_db,active,active_count,total_passes"]
        for r in report.results:
            lines.append(
                f"{r.frequency_hz},{r.frequency_str},{r.power_db:.1f},"
                f"{r.active},{r.active_count},{r.total_passes}"
            )
    else:
        lines = ["frequency_hz,frequency_str,power_db,active"]
        for r in report.results:
            lines.append(
                f"{r.frequency_hz},{r.frequency_str},{r.power_db:.1f},{r.active}"
            )
    return "\n".join(lines)
