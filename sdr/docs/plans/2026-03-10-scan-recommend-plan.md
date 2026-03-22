# Scan Recommend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `vtms-sdr scan recommend` command that scans a frequency range over multiple passes, ranks channels by quality, and outputs a sorted recommendation table.

**Architecture:** Extend `ScanResult` with per-pass activity counts, add a `ChannelScore` dataclass for ranking, add `scan_recommend()` to `FrequencyScanner`, add `format_recommend_report()` for output, and wire it up as a new `scan recommend` CLI subcommand.

**Tech Stack:** Python, Click (CLI), numpy (FFT power measurement), pytest (testing)

---

### Task 1: Extend ScanResult dataclass

**Files:**
- Modify: `src/vtms_sdr/scanner.py:33-43`
- Test: `tests/test_scanner.py`

**Step 1: Write failing tests for new ScanResult fields**

Add to `tests/test_scanner.py`:

```python
class TestScanResultExtended:
    """Tests for ScanResult active_count and total_passes fields."""

    def test_default_active_count_is_zero(self):
        r = ScanResult(frequency_hz=446_000_000, power_db=-40.0, active=False)
        assert r.active_count == 0

    def test_default_total_passes_is_zero(self):
        r = ScanResult(frequency_hz=446_000_000, power_db=-40.0, active=False)
        assert r.total_passes == 0

    def test_active_count_set_explicitly(self):
        r = ScanResult(frequency_hz=446_000_000, power_db=-20.0, active=True,
                       active_count=3, total_passes=10)
        assert r.active_count == 3
        assert r.total_passes == 10

    def test_existing_tests_unaffected(self):
        """Existing ScanResult usage without new fields still works."""
        r = ScanResult(frequency_hz=146_520_000, power_db=-25.0, active=True)
        assert r.frequency_str == "146.520000 MHz"
        assert r.active is True
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scanner.py::TestScanResultExtended -v`
Expected: FAIL — `ScanResult` does not accept `active_count`/`total_passes`

**Step 3: Add fields to ScanResult**

In `src/vtms_sdr/scanner.py`, add to the `ScanResult` dataclass:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scanner.py -v --tb=short`
Expected: ALL PASS (new tests + existing tests)

---

### Task 2: Add ChannelScore dataclass and compute_channel_scores function

**Files:**
- Modify: `src/vtms_sdr/scanner.py`
- Test: `tests/test_scanner.py`

**Step 1: Write failing tests for ChannelScore**

Add to `tests/test_scanner.py`:

```python
class TestChannelScore:
    """Tests for ChannelScore dataclass and scoring logic."""

    def test_perfect_clear_channel_gets_max_score(self):
        """Channel never active, very low power → highest score."""
        report = ScanReport(
            mode="recommend", start_hz=446_000_000, end_hz=446_100_000,
            step_hz=25_000, threshold_db=-30.0, duration_sec=60.0,
            scan_passes=10,
            results=[
                ScanResult(frequency_hz=446_000_000, power_db=-80.0,
                           active=False, active_count=0, total_passes=10),
            ],
        )
        scores = compute_channel_scores(report)
        assert len(scores) == 1
        assert scores[0].active_ratio == 0.0
        assert scores[0].score > 90.0

    def test_always_busy_channel_gets_low_score(self):
        """Channel active every pass → lowest score."""
        report = ScanReport(
            mode="recommend", start_hz=446_000_000, end_hz=446_100_000,
            step_hz=25_000, threshold_db=-30.0, duration_sec=60.0,
            scan_passes=10,
            results=[
                ScanResult(frequency_hz=446_000_000, power_db=-10.0,
                           active=True, active_count=10, total_passes=10),
            ],
        )
        scores = compute_channel_scores(report)
        assert scores[0].active_ratio == 1.0
        assert scores[0].score < 10.0

    def test_intermittent_channel_scores_between(self):
        """Channel active some passes → middle score."""
        report = ScanReport(
            mode="recommend", start_hz=446_000_000, end_hz=446_100_000,
            step_hz=25_000, threshold_db=-30.0, duration_sec=60.0,
            scan_passes=10,
            results=[
                ScanResult(frequency_hz=446_000_000, power_db=-25.0,
                           active=True, active_count=3, total_passes=10),
            ],
        )
        scores = compute_channel_scores(report)
        assert 10.0 < scores[0].score < 90.0

    def test_scores_sorted_best_first(self):
        """Multiple channels returned sorted by score descending."""
        report = ScanReport(
            mode="recommend", start_hz=446_000_000, end_hz=446_100_000,
            step_hz=25_000, threshold_db=-30.0, duration_sec=60.0,
            scan_passes=10,
            results=[
                ScanResult(frequency_hz=446_000_000, power_db=-10.0,
                           active=True, active_count=10, total_passes=10),
                ScanResult(frequency_hz=446_025_000, power_db=-80.0,
                           active=False, active_count=0, total_passes=10),
                ScanResult(frequency_hz=446_050_000, power_db=-25.0,
                           active=True, active_count=3, total_passes=10),
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
            mode="recommend", start_hz=446_000_000, end_hz=446_100_000,
            step_hz=25_000, threshold_db=-30.0, duration_sec=60.0,
            scan_passes=10,
            results=[
                ScanResult(frequency_hz=446_000_000, power_db=-40.0,
                           active=False, active_count=0, total_passes=10),
                ScanResult(frequency_hz=446_025_000, power_db=-70.0,
                           active=False, active_count=0, total_passes=10),
            ],
        )
        scores = compute_channel_scores(report)
        assert scores[0].frequency_hz == 446_025_000

    def test_zero_passes_returns_zero_score(self):
        """Edge case: zero passes completed (early abort)."""
        report = ScanReport(
            mode="recommend", start_hz=446_000_000, end_hz=446_100_000,
            step_hz=25_000, threshold_db=-30.0, duration_sec=0.0,
            scan_passes=0,
            results=[
                ScanResult(frequency_hz=446_000_000, power_db=-100.0,
                           active=False, active_count=0, total_passes=0),
            ],
        )
        scores = compute_channel_scores(report)
        assert scores[0].score == 0.0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scanner.py::TestChannelScore -v`
Expected: FAIL — `compute_channel_scores` not defined

**Step 3: Implement ChannelScore and compute_channel_scores**

Add to `src/vtms_sdr/scanner.py`:

```python
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
```

Update `__all__` to include `ChannelScore` and `compute_channel_scores`.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scanner.py -v --tb=short`
Expected: ALL PASS

---

### Task 3: Add scan_recommend method to FrequencyScanner

**Files:**
- Modify: `src/vtms_sdr/scanner.py`
- Test: `tests/test_scanner.py`

**Step 1: Write failing tests for scan_recommend**

Add to `tests/test_scanner.py` (uses existing `MockSDRDevice` fixture pattern from test file):

```python
class TestFrequencyScannerRecommend:
    """Tests for FrequencyScanner.scan_recommend method."""

    def test_recommend_returns_report(self, mock_sdr_device):
        scanner = FrequencyScanner(mock_sdr_device, threshold_db=-30.0)
        report = scanner.scan_recommend(
            start_hz=446_000_000, end_hz=446_100_000,
            step_hz=25_000, duration_sec=0.5,
        )
        assert isinstance(report, ScanReport)
        assert report.mode == "recommend"

    def test_recommend_populates_active_count(self, mock_sdr_device):
        """Each result has active_count and total_passes filled in."""
        scanner = FrequencyScanner(mock_sdr_device, threshold_db=-30.0)
        report = scanner.scan_recommend(
            start_hz=446_000_000, end_hz=446_100_000,
            step_hz=25_000, duration_sec=0.5,
        )
        for result in report.results:
            assert result.total_passes > 0
            assert result.active_count >= 0
            assert result.active_count <= result.total_passes

    def test_recommend_tracks_max_power(self, mock_sdr_device):
        scanner = FrequencyScanner(mock_sdr_device, threshold_db=-30.0)
        report = scanner.scan_recommend(
            start_hz=446_000_000, end_hz=446_100_000,
            step_hz=25_000, duration_sec=0.5,
        )
        for result in report.results:
            assert result.power_db > -100.0  # updated from initial -100

    def test_recommend_scan_passes_counted(self, mock_sdr_device):
        scanner = FrequencyScanner(mock_sdr_device, threshold_db=-30.0)
        report = scanner.scan_recommend(
            start_hz=446_000_000, end_hz=446_100_000,
            step_hz=25_000, duration_sec=0.5,
        )
        assert report.scan_passes >= 1

    def test_recommend_metadata(self, mock_sdr_device):
        scanner = FrequencyScanner(mock_sdr_device, threshold_db=-25.0)
        report = scanner.scan_recommend(
            start_hz=446_000_000, end_hz=446_100_000,
            step_hz=25_000, duration_sec=0.5,
        )
        assert report.start_hz == 446_000_000
        assert report.end_hz == 446_100_000
        assert report.step_hz == 25_000
        assert report.threshold_db == -25.0
        assert report.duration_sec > 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scanner.py::TestFrequencyScannerRecommend -v`
Expected: FAIL — `scan_recommend` method not found

**Step 3: Implement scan_recommend**

Add to `FrequencyScanner` class in `src/vtms_sdr/scanner.py`:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scanner.py -v --tb=short`
Expected: ALL PASS

---

### Task 4: Add format_recommend_report function

**Files:**
- Modify: `src/vtms_sdr/scanner.py`
- Test: `tests/test_scanner.py`

**Step 1: Write failing tests**

```python
class TestFormatRecommendReport:
    """Tests for format_recommend_report output."""

    def _make_report(self, results):
        return ScanReport(
            mode="recommend", start_hz=446_000_000, end_hz=446_100_000,
            step_hz=25_000, threshold_db=-30.0, duration_sec=60.0,
            scan_passes=10, results=results,
        )

    def test_header_contains_recommend(self):
        report = self._make_report([
            ScanResult(frequency_hz=446_000_000, power_db=-50.0,
                       active=False, active_count=0, total_passes=10),
        ])
        output = format_recommend_report(report)
        assert "RECOMMEND" in output.upper()

    def test_shows_rank_column(self):
        report = self._make_report([
            ScanResult(frequency_hz=446_000_000, power_db=-50.0,
                       active=False, active_count=0, total_passes=10),
        ])
        output = format_recommend_report(report)
        assert "Rank" in output

    def test_shows_status_clear(self):
        report = self._make_report([
            ScanResult(frequency_hz=446_000_000, power_db=-50.0,
                       active=False, active_count=0, total_passes=10),
        ])
        output = format_recommend_report(report)
        assert "CLEAR" in output

    def test_shows_status_busy(self):
        report = self._make_report([
            ScanResult(frequency_hz=446_000_000, power_db=-10.0,
                       active=True, active_count=8, total_passes=10),
        ])
        output = format_recommend_report(report)
        assert "BUSY" in output

    def test_shows_status_intermittent(self):
        report = self._make_report([
            ScanResult(frequency_hz=446_000_000, power_db=-25.0,
                       active=True, active_count=3, total_passes=10),
        ])
        output = format_recommend_report(report)
        assert "INTERMITTENT" in output

    def test_top_n_limits_output(self):
        results = [
            ScanResult(frequency_hz=446_000_000 + i * 25_000, power_db=-50.0 + i,
                       active=False, active_count=0, total_passes=10)
            for i in range(10)
        ]
        report = self._make_report(results)
        output = format_recommend_report(report, top_n=3)
        # Count data rows (lines with MHz in them)
        data_lines = [l for l in output.split("\n") if "MHz" in l]
        assert len(data_lines) == 3

    def test_top_n_zero_shows_all(self):
        results = [
            ScanResult(frequency_hz=446_000_000 + i * 25_000, power_db=-50.0,
                       active=False, active_count=0, total_passes=10)
            for i in range(5)
        ]
        report = self._make_report(results)
        output = format_recommend_report(report, top_n=0)
        data_lines = [l for l in output.split("\n") if "MHz" in l]
        assert len(data_lines) == 5

    def test_empty_results(self):
        report = self._make_report([])
        output = format_recommend_report(report)
        assert "No channels" in output or "0" in output
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scanner.py::TestFormatRecommendReport -v`
Expected: FAIL

**Step 3: Implement format_recommend_report**

Add to `src/vtms_sdr/scanner.py`:

```python
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
        f"Channels scanned: {len(scores)} | "
        f"Clear: {num_clear} | Active: {num_active}"
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
        passes_str = f"{int(s.active_ratio * report.scan_passes)}/{report.scan_passes}" if report.scan_passes > 0 else "0/0"
        lines.append(
            f"{i:>4}  {s.frequency_str:>15}  {s.score:>5.1f}  "
            f"{s.max_power_db:>7.1f} dB  {passes_str:>13}  {s.status}"
        )

    if top_n > 0 and top_n < len(scores):
        lines.append(f"\n(Showing top {top_n} of {len(scores)} channels)")

    return "\n".join(lines)
```

Update `__all__` to include `format_recommend_report` and `compute_channel_scores`.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scanner.py -v --tb=short`
Expected: ALL PASS

---

### Task 5: Extend format_scan_csv for recommend mode

**Files:**
- Modify: `src/vtms_sdr/scanner.py`
- Test: `tests/test_scanner.py`

**Step 1: Write failing tests**

```python
class TestFormatScanCsvRecommend:
    """Tests for CSV output with recommend-mode reports."""

    def test_csv_includes_active_count_column(self):
        report = ScanReport(
            mode="recommend", start_hz=446_000_000, end_hz=446_100_000,
            step_hz=25_000, threshold_db=-30.0, duration_sec=60.0,
            scan_passes=10,
            results=[
                ScanResult(frequency_hz=446_000_000, power_db=-50.0,
                           active=False, active_count=0, total_passes=10),
            ],
        )
        csv = format_scan_csv(report)
        header = csv.split("\n")[0]
        assert "active_count" in header
        assert "total_passes" in header

    def test_csv_data_row_has_counts(self):
        report = ScanReport(
            mode="recommend", start_hz=446_000_000, end_hz=446_100_000,
            step_hz=25_000, threshold_db=-30.0, duration_sec=60.0,
            scan_passes=10,
            results=[
                ScanResult(frequency_hz=446_000_000, power_db=-50.0,
                           active=False, active_count=2, total_passes=10),
            ],
        )
        csv = format_scan_csv(report)
        data_row = csv.split("\n")[1]
        assert ",2," in data_row
        assert ",10" in data_row

    def test_csv_non_recommend_unchanged(self):
        """Existing active/clear CSV format is not affected."""
        report = ScanReport(
            mode="active", start_hz=446_000_000, end_hz=446_100_000,
            step_hz=25_000, threshold_db=-30.0, duration_sec=5.0,
            scan_passes=1,
            results=[
                ScanResult(frequency_hz=446_000_000, power_db=-50.0, active=False),
            ],
        )
        csv = format_scan_csv(report)
        header = csv.split("\n")[0]
        assert "active_count" not in header
```

**Step 2: Run tests, verify fail, implement, verify pass**

Modify `format_scan_csv` in `src/vtms_sdr/scanner.py` to conditionally add columns:

```python
def format_scan_csv(report: ScanReport) -> str:
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
            lines.append(f"{r.frequency_hz},{r.frequency_str},{r.power_db:.1f},{r.active}")
    return "\n".join(lines)
```

Run: `uv run pytest tests/test_scanner.py -v --tb=short`
Expected: ALL PASS

---

### Task 6: Add scan recommend CLI command

**Files:**
- Modify: `src/vtms_sdr/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Write failing CLI tests**

Add to `tests/test_cli.py`:

```python
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
        result = runner.invoke(main, [
            "scan", "recommend",
            "--start", "446MHz", "--end", "446.1MHz", "--step", "25kHz",
            "-d", "0.5",
        ])
        assert result.exit_code == 0
        assert "Rank" in result.output

    def test_recommend_top_flag(self, runner, mock_sdr):
        result = runner.invoke(main, [
            "scan", "recommend",
            "--start", "446MHz", "--end", "446.2MHz", "--step", "25kHz",
            "-d", "0.5", "--top", "2",
        ])
        assert result.exit_code == 0
        assert "Showing top 2" in result.output

    def test_recommend_csv_output(self, runner, mock_sdr, tmp_path):
        csv_file = str(tmp_path / "recommend.csv")
        result = runner.invoke(main, [
            "scan", "recommend",
            "--start", "446MHz", "--end", "446.1MHz", "--step", "25kHz",
            "-d", "0.5", "-o", csv_file,
        ])
        assert result.exit_code == 0
        import os
        assert os.path.exists(csv_file)
        with open(csv_file) as f:
            header = f.readline()
        assert "active_count" in header

    def test_recommend_missing_params(self, runner):
        result = runner.invoke(main, ["scan", "recommend"])
        assert result.exit_code != 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestScanRecommendCommand -v`
Expected: FAIL

**Step 3: Implement the CLI command**

Add to `src/vtms_sdr/cli.py`, following the same pattern as `scan_clear`:

```python
@scan.command("recommend")
@click.option("--start", required=True, help="Start frequency (e.g. 400MHz)")
@click.option("--end", required=True, help="End frequency (e.g. 470MHz)")
@click.option("--step", required=True, help="Step size (e.g. 25kHz)")
@click.option("-d", "--duration", default=300.0, type=float,
              help="Monitoring duration in seconds")
@click.option("--threshold", default=-30.0, type=float,
              help="Signal detection threshold in dB")
@click.option("--top", "top_n", default=0, type=int,
              help="Show only the top N channels (default: all)")
@click.option("-o", "--output", type=click.Path(), default=None,
              help="Save full results to CSV file")
@click.option("--device", default=0, type=int, help="RTL-SDR device index")
@click.option("-g", "--gain", default="auto", help="Gain in dB or 'auto'")
@click.option("--ppm", default=0, type=int, help="Frequency correction in PPM")
@click.pass_context
def scan_recommend(ctx, start, end, step, duration, threshold, top_n,
                   output, device, gain, ppm):
    """Recommend clear channels for team radio use.

    Scans the frequency range over multiple passes, ranks every channel
    by how quiet and consistently clear it is, and outputs a sorted
    recommendation table.
    """
    # Parse and validate frequencies (same pattern as scan_active/scan_clear)
    ...
    # Create SDR, scanner, run scan_recommend, format output
    ...
```

(Full implementation follows existing scan_clear pattern)

**Step 4: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: ALL PASS

---

### Task 7: Final verification

**Step 1: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: ALL 443+ tests pass

**Step 2: Verify CLI help**

Run: `uv run vtms-sdr scan recommend --help`
Expected: Shows all options with descriptions
