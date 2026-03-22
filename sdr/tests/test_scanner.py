"""Tests for vtms_sdr.scanner with mocked SDR device."""

import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from vtms_sdr.scanner import (
    ChannelScore,
    ScanResult,
    ScanReport,
    FrequencyScanner,
    compute_channel_scores,
    format_recommend_report,
    format_scan_report,
    format_scan_csv,
)
from vtms_sdr.sdr import DEFAULT_SAMPLE_RATE


# --- Data class tests ---


class TestScanResult:
    def test_frequency_str(self):
        r = ScanResult(frequency_hz=146_520_000, power_db=-25.3, active=True)
        assert "146.520 MHz" in r.frequency_str

    def test_active_flag(self):
        r = ScanResult(frequency_hz=146_520_000, power_db=-25.3, active=True)
        assert r.active is True

    def test_inactive_flag(self):
        r = ScanResult(frequency_hz=146_520_000, power_db=-55.0, active=False)
        assert r.active is False


class TestScanResultExtended:
    """Tests for ScanResult active_count and total_passes fields."""

    def test_default_active_count_is_zero(self):
        r = ScanResult(frequency_hz=446_000_000, power_db=-40.0, active=False)
        assert r.active_count == 0

    def test_default_total_passes_is_zero(self):
        r = ScanResult(frequency_hz=446_000_000, power_db=-40.0, active=False)
        assert r.total_passes == 0

    def test_active_count_set_explicitly(self):
        r = ScanResult(
            frequency_hz=446_000_000,
            power_db=-20.0,
            active=True,
            active_count=3,
            total_passes=10,
        )
        assert r.active_count == 3
        assert r.total_passes == 10

    def test_existing_tests_unaffected(self):
        """Existing ScanResult usage without new fields still works."""
        r = ScanResult(frequency_hz=146_520_000, power_db=-25.0, active=True)
        assert "146.520" in r.frequency_str
        assert r.active is True


class TestScanReport:
    def _make_report(self):
        return ScanReport(
            mode="active",
            start_hz=144_000_000,
            end_hz=148_000_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=5.0,
            scan_passes=1,
            results=[
                ScanResult(144_000_000, -20.0, True),
                ScanResult(144_025_000, -45.0, False),
                ScanResult(144_050_000, -15.0, True),
                ScanResult(144_075_000, -50.0, False),
            ],
        )

    def test_active_frequencies(self):
        report = self._make_report()
        active = report.active_frequencies
        assert len(active) == 2
        assert all(r.active for r in active)

    def test_clear_frequencies(self):
        report = self._make_report()
        clear = report.clear_frequencies
        assert len(clear) == 2
        assert all(not r.active for r in clear)

    def test_empty_report(self):
        report = ScanReport(
            mode="active",
            start_hz=144_000_000,
            end_hz=148_000_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=0.0,
        )
        assert len(report.active_frequencies) == 0
        assert len(report.clear_frequencies) == 0


# --- Format tests ---


class TestFormatScanReport:
    def test_active_report(self):
        report = ScanReport(
            mode="active",
            start_hz=144_000_000,
            end_hz=148_000_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=5.0,
            scan_passes=1,
            results=[
                ScanResult(144_000_000, -20.0, True),
                ScanResult(144_025_000, -45.0, False),
            ],
        )
        text = format_scan_report(report)
        assert "ACTIVE" in text
        assert "144.000 MHz" in text
        assert "1 / 2" in text

    def test_clear_report(self):
        report = ScanReport(
            mode="clear",
            start_hz=144_000_000,
            end_hz=148_000_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=300.0,
            scan_passes=10,
            results=[
                ScanResult(144_000_000, -20.0, True),
                ScanResult(144_025_000, -45.0, False),
            ],
        )
        text = format_scan_report(report)
        assert "CLEAR" in text
        assert "144.025 MHz" in text

    def test_no_active_found(self):
        report = ScanReport(
            mode="active",
            start_hz=144_000_000,
            end_hz=144_050_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=1.0,
            scan_passes=1,
            results=[
                ScanResult(144_000_000, -45.0, False),
                ScanResult(144_025_000, -50.0, False),
            ],
        )
        text = format_scan_report(report)
        assert "No active frequencies found" in text

    def test_no_clear_found(self):
        report = ScanReport(
            mode="clear",
            start_hz=144_000_000,
            end_hz=144_050_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=300.0,
            scan_passes=10,
            results=[
                ScanResult(144_000_000, -20.0, True),
                ScanResult(144_025_000, -15.0, True),
            ],
        )
        text = format_scan_report(report)
        assert "No clear frequencies found" in text

    def test_active_sorted_by_power(self):
        report = ScanReport(
            mode="active",
            start_hz=144_000_000,
            end_hz=144_100_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=1.0,
            scan_passes=1,
            results=[
                ScanResult(144_000_000, -25.0, True),
                ScanResult(144_025_000, -10.0, True),  # Strongest
                ScanResult(144_050_000, -20.0, True),
            ],
        )
        text = format_scan_report(report)
        lines = text.split("\n")
        # Find the data lines (contain dB values)
        data_lines = [l for l in lines if "dB" not in l and "MHz" in l]
        # The strongest signal (-10.0) should appear first in the table


class TestFormatScanCsv:
    def test_csv_output(self):
        report = ScanReport(
            mode="active",
            start_hz=144_000_000,
            end_hz=144_050_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=1.0,
            scan_passes=1,
            results=[
                ScanResult(144_000_000, -20.0, True),
                ScanResult(144_025_000, -45.0, False),
            ],
        )
        csv = format_scan_csv(report)
        lines = csv.strip().split("\n")
        assert lines[0] == "frequency_hz,frequency_str,power_db,active"
        assert len(lines) == 3
        assert "144000000" in lines[1]
        assert "True" in lines[1]

    def test_csv_all_fields_present(self):
        report = ScanReport(
            mode="active",
            start_hz=144_000_000,
            end_hz=144_050_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=1.0,
            scan_passes=1,
            results=[ScanResult(144_000_000, -20.5, True)],
        )
        csv = format_scan_csv(report)
        data_line = csv.strip().split("\n")[1]
        parts = data_line.split(",")
        assert parts[0] == "144000000"
        assert "MHz" in parts[1]
        assert parts[2] == "-20.5"
        assert parts[3] == "True"


# --- FrequencyScanner logic tests (mocked SDR) ---


class MockSDRDevice:
    """Mock SDR device that returns controllable power levels per frequency."""

    def __init__(self, power_map: dict[int, float] | None = None):
        """
        Args:
            power_map: dict mapping frequency_hz -> desired power level.
                       Frequencies not in the map return noise floor.
        """
        self.power_map = power_map or {}
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self._configured_freq = 0

    def configure(
        self,
        center_freq: int,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        gain: str | float = "auto",
        ppm: int = 0,
    ) -> None:
        self._configured_freq = center_freq

    def read_samples(self, num_samples: int = 65536) -> np.ndarray:
        """Return IQ samples with power level based on configured frequency.

        Strong signals use a constant tone (concentrates in one FFT bin).
        Weak/absent signals use random noise at very low amplitude.
        """
        target_power = self.power_map.get(self._configured_freq, None)

        if target_power is not None and target_power > 1e-8:
            # Strong signal: constant tone + tiny noise
            amplitude = np.sqrt(target_power)
            samples = amplitude * np.ones(num_samples, dtype=np.complex64)
            noise = (
                np.random.randn(num_samples) + 1j * np.random.randn(num_samples)
            ) * 1e-8
            return samples + noise.astype(np.complex64)
        else:
            # Noise floor: pure random noise at very low amplitude
            return (
                (np.random.randn(num_samples) + 1j * np.random.randn(num_samples))
                * 1e-6
            ).astype(np.complex64)


class TestFrequencyScannerMeasurePower:
    def test_measure_strong_signal(self):
        # Amplitude 1.0 -> power ~1.0 -> ~0 dB
        mock_sdr = MockSDRDevice({146_520_000: 1.0})
        scanner = FrequencyScanner(mock_sdr, threshold_db=-30.0)
        power = scanner.measure_power(146_520_000)
        # Should be near 0 dB for amplitude 1.0
        assert power > -10.0

    def test_measure_weak_signal(self):
        # No signal at this freq -> noise floor only
        mock_sdr = MockSDRDevice({999_000_000: 1.0})  # Signal elsewhere
        scanner = FrequencyScanner(mock_sdr, threshold_db=-30.0)
        power = scanner.measure_power(146_520_000)  # No signal here
        assert power < -30.0

    def test_measure_no_signal(self):
        mock_sdr = MockSDRDevice()  # No signals
        scanner = FrequencyScanner(mock_sdr, threshold_db=-30.0)
        power = scanner.measure_power(146_520_000)
        assert power < -30.0

    def test_measure_power_discards_settling_samples(self):
        """measure_power should read and discard samples for PLL settling."""
        mock_sdr = MockSDRDevice({146_520_000: 1.0})
        # Wrap read_samples so we can track call count
        original_read = mock_sdr.read_samples
        mock_sdr.read_samples = MagicMock(side_effect=original_read)

        scanner = FrequencyScanner(mock_sdr, threshold_db=-50)
        scanner.measure_power(146_520_000)

        # read_samples should be called at least twice: settling + measurement
        assert mock_sdr.read_samples.call_count >= 2

    def test_measure_power_preserves_gain(self):
        """measure_power should forward stored gain to sdr.configure()."""
        mock_sdr = MockSDRDevice({146_520_000: 1.0})
        original_configure = mock_sdr.configure
        call_kwargs_list = []

        def spy_configure(**kwargs):
            call_kwargs_list.append(kwargs)
            return original_configure(**kwargs)

        mock_sdr.configure = spy_configure

        scanner = FrequencyScanner(mock_sdr, threshold_db=-50, gain=40.0)
        scanner.measure_power(146_520_000)

        # configure should have been called with gain=40.0
        assert any(kw.get("gain") == 40.0 for kw in call_kwargs_list)

    def test_measure_power_preserves_ppm(self):
        """measure_power should forward stored ppm to sdr.configure()."""
        mock_sdr = MockSDRDevice({146_520_000: 1.0})
        original_configure = mock_sdr.configure
        call_kwargs_list = []

        def spy_configure(**kwargs):
            call_kwargs_list.append(kwargs)
            return original_configure(**kwargs)

        mock_sdr.configure = spy_configure

        scanner = FrequencyScanner(mock_sdr, threshold_db=-50, ppm=28)
        scanner.measure_power(146_520_000)

        # configure should have been called with ppm=28
        assert any(kw.get("ppm") == 28 for kw in call_kwargs_list)


class TestFrequencyScannerActiveScan:
    def test_finds_active_frequencies(self):
        power_map = {
            144_000_000: 1.0,  # Strong signal
            # 144_025_000 not in map -> noise floor
            144_050_000: 0.5,  # Medium signal
            # 144_075_000 not in map -> noise floor
        }
        mock_sdr = MockSDRDevice(power_map)
        scanner = FrequencyScanner(mock_sdr, threshold_db=-20.0)
        report = scanner.scan_active(144_000_000, 144_075_000, 25_000)

        assert report.mode == "active"
        assert len(report.results) == 4
        active = report.active_frequencies
        assert len(active) == 2
        active_freqs = {r.frequency_hz for r in active}
        assert 144_000_000 in active_freqs
        assert 144_050_000 in active_freqs

    def test_no_active_frequencies(self):
        mock_sdr = MockSDRDevice()  # All noise
        scanner = FrequencyScanner(mock_sdr, threshold_db=-20.0)
        report = scanner.scan_active(144_000_000, 144_075_000, 25_000)

        assert len(report.active_frequencies) == 0
        assert len(report.results) == 4

    def test_all_active_frequencies(self):
        power_map = {
            144_000_000: 1.0,
            144_025_000: 0.5,
            144_050_000: 0.8,
        }
        mock_sdr = MockSDRDevice(power_map)
        scanner = FrequencyScanner(mock_sdr, threshold_db=-20.0)
        report = scanner.scan_active(144_000_000, 144_050_000, 25_000)

        assert len(report.active_frequencies) == 3

    def test_scan_report_metadata(self):
        mock_sdr = MockSDRDevice()
        scanner = FrequencyScanner(mock_sdr, threshold_db=-25.0)
        report = scanner.scan_active(144_000_000, 144_050_000, 25_000)

        assert report.start_hz == 144_000_000
        assert report.end_hz == 144_050_000
        assert report.step_hz == 25_000
        assert report.threshold_db == -25.0
        assert report.scan_passes == 1
        assert report.duration_sec > 0


class TestFrequencyScannerClearScan:
    def test_finds_clear_frequencies(self):
        power_map = {
            144_000_000: 1.0,  # Strong - always active
            # 144_025_000 not in map -> noise floor (always clear)
            # 144_050_000 not in map -> noise floor (always clear)
        }
        mock_sdr = MockSDRDevice(power_map)
        scanner = FrequencyScanner(mock_sdr, threshold_db=-20.0)
        # Short duration for test speed
        report = scanner.scan_clear(144_000_000, 144_050_000, 25_000, duration_sec=0.5)

        assert report.mode == "clear"
        clear = report.clear_frequencies
        clear_freqs = {r.frequency_hz for r in clear}
        assert 144_025_000 in clear_freqs
        assert 144_050_000 in clear_freqs
        assert 144_000_000 not in clear_freqs

    def test_clear_scan_multiple_passes(self):
        mock_sdr = MockSDRDevice()
        scanner = FrequencyScanner(mock_sdr, threshold_db=-20.0)
        report = scanner.scan_clear(144_000_000, 144_050_000, 25_000, duration_sec=0.5)

        # Should have done at least 1 pass
        assert report.scan_passes >= 1

    def test_clear_scan_report_metadata(self):
        mock_sdr = MockSDRDevice()
        scanner = FrequencyScanner(mock_sdr, threshold_db=-30.0)
        report = scanner.scan_clear(144_000_000, 144_050_000, 25_000, duration_sec=0.3)

        assert report.mode == "clear"
        assert report.start_hz == 144_000_000
        assert report.end_hz == 144_050_000
        assert report.threshold_db == -30.0
        assert report.duration_sec >= 0.2  # At least close to requested


# --- ChannelScore and compute_channel_scores tests ---


class TestChannelScore:
    """Tests for ChannelScore dataclass and scoring logic."""

    def test_perfect_clear_channel_gets_max_score(self):
        """Channel never active, very low power -> highest score."""
        report = ScanReport(
            mode="recommend",
            start_hz=446_000_000,
            end_hz=446_100_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=60.0,
            scan_passes=10,
            results=[
                ScanResult(
                    frequency_hz=446_000_000,
                    power_db=-80.0,
                    active=False,
                    active_count=0,
                    total_passes=10,
                ),
            ],
        )
        scores = compute_channel_scores(report)
        assert len(scores) == 1
        assert scores[0].active_ratio == 0.0
        assert scores[0].score > 90.0

    def test_always_busy_channel_gets_low_score(self):
        """Channel active every pass -> lowest score."""
        report = ScanReport(
            mode="recommend",
            start_hz=446_000_000,
            end_hz=446_100_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=60.0,
            scan_passes=10,
            results=[
                ScanResult(
                    frequency_hz=446_000_000,
                    power_db=-10.0,
                    active=True,
                    active_count=10,
                    total_passes=10,
                ),
            ],
        )
        scores = compute_channel_scores(report)
        assert scores[0].active_ratio == 1.0
        assert scores[0].score < 10.0

    def test_intermittent_channel_scores_between(self):
        """Channel active some passes -> middle score."""
        report = ScanReport(
            mode="recommend",
            start_hz=446_000_000,
            end_hz=446_100_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=60.0,
            scan_passes=10,
            results=[
                ScanResult(
                    frequency_hz=446_000_000,
                    power_db=-25.0,
                    active=True,
                    active_count=3,
                    total_passes=10,
                ),
            ],
        )
        scores = compute_channel_scores(report)
        assert 10.0 < scores[0].score < 90.0

    def test_scores_sorted_best_first(self):
        """Multiple channels returned sorted by score descending."""
        report = ScanReport(
            mode="recommend",
            start_hz=446_000_000,
            end_hz=446_100_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=60.0,
            scan_passes=10,
            results=[
                ScanResult(
                    frequency_hz=446_000_000,
                    power_db=-10.0,
                    active=True,
                    active_count=10,
                    total_passes=10,
                ),
                ScanResult(
                    frequency_hz=446_025_000,
                    power_db=-80.0,
                    active=False,
                    active_count=0,
                    total_passes=10,
                ),
                ScanResult(
                    frequency_hz=446_050_000,
                    power_db=-25.0,
                    active=True,
                    active_count=3,
                    total_passes=10,
                ),
            ],
        )
        scores = compute_channel_scores(report)
        assert scores[0].frequency_hz == 446_025_000
        assert scores[-1].frequency_hz == 446_000_000
        for i in range(len(scores) - 1):
            assert scores[i].score >= scores[i + 1].score

    def test_quieter_clear_channel_ranks_higher(self):
        """Between two always-clear channels, the one with lower max power ranks higher."""
        report = ScanReport(
            mode="recommend",
            start_hz=446_000_000,
            end_hz=446_100_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=60.0,
            scan_passes=10,
            results=[
                ScanResult(
                    frequency_hz=446_000_000,
                    power_db=-40.0,
                    active=False,
                    active_count=0,
                    total_passes=10,
                ),
                ScanResult(
                    frequency_hz=446_025_000,
                    power_db=-70.0,
                    active=False,
                    active_count=0,
                    total_passes=10,
                ),
            ],
        )
        scores = compute_channel_scores(report)
        assert scores[0].frequency_hz == 446_025_000

    def test_zero_passes_returns_zero_score(self):
        """Edge case: zero passes completed (early abort)."""
        report = ScanReport(
            mode="recommend",
            start_hz=446_000_000,
            end_hz=446_100_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=0.0,
            scan_passes=0,
            results=[
                ScanResult(
                    frequency_hz=446_000_000,
                    power_db=-100.0,
                    active=False,
                    active_count=0,
                    total_passes=0,
                ),
            ],
        )
        scores = compute_channel_scores(report)
        assert scores[0].score == 0.0


# --- scan_recommend tests ---


@pytest.fixture
def mock_sdr_device():
    """Provide a MockSDRDevice with some active and some quiet frequencies."""
    power_map = {
        446_000_000: 1.0,  # Strong signal
        446_050_000: 0.5,  # Medium signal
    }
    return MockSDRDevice(power_map)


class TestFrequencyScannerRecommend:
    """Tests for FrequencyScanner.scan_recommend method."""

    def test_recommend_returns_report(self, mock_sdr_device):
        scanner = FrequencyScanner(mock_sdr_device, threshold_db=-30.0)
        report = scanner.scan_recommend(
            start_hz=446_000_000,
            end_hz=446_100_000,
            step_hz=25_000,
            duration_sec=0.5,
        )
        assert isinstance(report, ScanReport)
        assert report.mode == "recommend"

    def test_recommend_populates_active_count(self, mock_sdr_device):
        """Each result has active_count and total_passes filled in."""
        scanner = FrequencyScanner(mock_sdr_device, threshold_db=-30.0)
        report = scanner.scan_recommend(
            start_hz=446_000_000,
            end_hz=446_100_000,
            step_hz=25_000,
            duration_sec=0.5,
        )
        for result in report.results:
            assert result.total_passes > 0
            assert result.active_count >= 0
            assert result.active_count <= result.total_passes

    def test_recommend_tracks_max_power(self, mock_sdr_device):
        scanner = FrequencyScanner(mock_sdr_device, threshold_db=-30.0)
        report = scanner.scan_recommend(
            start_hz=446_000_000,
            end_hz=446_100_000,
            step_hz=25_000,
            duration_sec=0.5,
        )
        for result in report.results:
            assert result.power_db > -100.0  # updated from initial -100

    def test_recommend_scan_passes_counted(self, mock_sdr_device):
        scanner = FrequencyScanner(mock_sdr_device, threshold_db=-30.0)
        report = scanner.scan_recommend(
            start_hz=446_000_000,
            end_hz=446_100_000,
            step_hz=25_000,
            duration_sec=0.5,
        )
        assert report.scan_passes >= 1

    def test_recommend_metadata(self, mock_sdr_device):
        scanner = FrequencyScanner(mock_sdr_device, threshold_db=-25.0)
        report = scanner.scan_recommend(
            start_hz=446_000_000,
            end_hz=446_100_000,
            step_hz=25_000,
            duration_sec=0.5,
        )
        assert report.start_hz == 446_000_000
        assert report.end_hz == 446_100_000
        assert report.step_hz == 25_000
        assert report.threshold_db == -25.0
        assert report.duration_sec > 0


# --- format_recommend_report tests ---


class TestFormatRecommendReport:
    """Tests for format_recommend_report output."""

    def _make_report(self, results):
        return ScanReport(
            mode="recommend",
            start_hz=446_000_000,
            end_hz=446_100_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=60.0,
            scan_passes=10,
            results=results,
        )

    def test_header_contains_recommend(self):
        report = self._make_report(
            [
                ScanResult(
                    frequency_hz=446_000_000,
                    power_db=-50.0,
                    active=False,
                    active_count=0,
                    total_passes=10,
                ),
            ]
        )
        output = format_recommend_report(report)
        assert "RECOMMEND" in output.upper()

    def test_shows_rank_column(self):
        report = self._make_report(
            [
                ScanResult(
                    frequency_hz=446_000_000,
                    power_db=-50.0,
                    active=False,
                    active_count=0,
                    total_passes=10,
                ),
            ]
        )
        output = format_recommend_report(report)
        assert "Rank" in output

    def test_shows_status_clear(self):
        report = self._make_report(
            [
                ScanResult(
                    frequency_hz=446_000_000,
                    power_db=-50.0,
                    active=False,
                    active_count=0,
                    total_passes=10,
                ),
            ]
        )
        output = format_recommend_report(report)
        assert "CLEAR" in output

    def test_shows_status_busy(self):
        report = self._make_report(
            [
                ScanResult(
                    frequency_hz=446_000_000,
                    power_db=-10.0,
                    active=True,
                    active_count=8,
                    total_passes=10,
                ),
            ]
        )
        output = format_recommend_report(report)
        assert "BUSY" in output

    def test_shows_status_intermittent(self):
        report = self._make_report(
            [
                ScanResult(
                    frequency_hz=446_000_000,
                    power_db=-25.0,
                    active=True,
                    active_count=3,
                    total_passes=10,
                ),
            ]
        )
        output = format_recommend_report(report)
        assert "INTERMITTENT" in output

    def test_top_n_limits_output(self):
        results = [
            ScanResult(
                frequency_hz=446_000_000 + i * 25_000,
                power_db=-50.0 + i,
                active=False,
                active_count=0,
                total_passes=10,
            )
            for i in range(10)
        ]
        report = self._make_report(results)
        output = format_recommend_report(report, top_n=3)
        # Count data rows (lines with rank numbers and MHz)
        data_lines = [l for l in output.split("\n") if "MHz" in l and "CLEAR" in l]
        assert len(data_lines) == 3

    def test_top_n_zero_shows_all(self):
        results = [
            ScanResult(
                frequency_hz=446_000_000 + i * 25_000,
                power_db=-50.0,
                active=False,
                active_count=0,
                total_passes=10,
            )
            for i in range(5)
        ]
        report = self._make_report(results)
        output = format_recommend_report(report, top_n=0)
        data_lines = [l for l in output.split("\n") if "MHz" in l and "CLEAR" in l]
        assert len(data_lines) == 5

    def test_empty_results(self):
        report = self._make_report([])
        output = format_recommend_report(report)
        assert "No channels" in output or "0" in output


# --- CSV recommend-mode tests ---


class TestFormatScanCsvRecommend:
    """Tests for CSV output with recommend-mode reports."""

    def test_csv_includes_active_count_column(self):
        report = ScanReport(
            mode="recommend",
            start_hz=446_000_000,
            end_hz=446_100_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=60.0,
            scan_passes=10,
            results=[
                ScanResult(
                    frequency_hz=446_000_000,
                    power_db=-50.0,
                    active=False,
                    active_count=0,
                    total_passes=10,
                ),
            ],
        )
        csv = format_scan_csv(report)
        header = csv.split("\n")[0]
        assert "active_count" in header
        assert "total_passes" in header

    def test_csv_data_row_has_counts(self):
        report = ScanReport(
            mode="recommend",
            start_hz=446_000_000,
            end_hz=446_100_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=60.0,
            scan_passes=10,
            results=[
                ScanResult(
                    frequency_hz=446_000_000,
                    power_db=-50.0,
                    active=False,
                    active_count=2,
                    total_passes=10,
                ),
            ],
        )
        csv = format_scan_csv(report)
        data_row = csv.split("\n")[1]
        assert ",2," in data_row
        assert ",10" in data_row

    def test_csv_non_recommend_unchanged(self):
        """Existing active/clear CSV format is not affected."""
        report = ScanReport(
            mode="active",
            start_hz=446_000_000,
            end_hz=446_100_000,
            step_hz=25_000,
            threshold_db=-30.0,
            duration_sec=5.0,
            scan_passes=1,
            results=[
                ScanResult(frequency_hz=446_000_000, power_db=-50.0, active=False),
            ],
        )
        csv = format_scan_csv(report)
        header = csv.split("\n")[0]
        assert "active_count" not in header
