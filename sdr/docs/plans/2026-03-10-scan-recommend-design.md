# Scan Recommend: Clear Channel Finder

## Problem

The team needs to identify the best UHF frequencies (400-470 MHz) to use on Baofeng radios during a weekend event. The existing `scan clear` command finds frequencies that never exceeded a power threshold, but it only provides binary active/clear classification with no ranking. Users want a single command that scans the full band, monitors over time, and produces a ranked list of the quietest, most consistently clear channels.

## Solution

Add a `vtms-sdr scan recommend` command that monitors a frequency range over a configurable duration (multiple passes), collects per-channel statistics (max power, activity count per pass), computes a quality score, and outputs a ranked table of channel recommendations.

## Data Model

### Extended ScanResult fields

Add two optional fields to the existing `ScanResult` dataclass:

- `active_count: int` -- number of scan passes where this frequency exceeded the threshold
- `total_passes: int` -- total number of completed scan passes

These fields default to 0 for backward compatibility with `scan_active` and `scan_clear`.

### New ChannelScore dataclass

```python
@dataclass
class ChannelScore:
    frequency_hz: int
    max_power_db: float      # worst-case power observed
    active_ratio: float      # active_count / total_passes (0.0 = always clear)
    score: float             # composite quality score (higher = better)
```

### Scoring formula

```
score = (1 - active_ratio) * 100 - max_power_db_normalized
```

Where `max_power_db_normalized` maps the observed max power into a 0-100 range relative to the threshold. Channels that were never active and had the lowest max power get the highest score.

## Scanner Changes

### New method: `FrequencyScanner.scan_recommend`

```
scan_recommend(start_hz, end_hz, step_hz, duration_sec=300.0) -> ScanReport
```

Algorithm:

1. Generate frequency list from start/end/step.
2. Initialize per-frequency counters: `active_count[freq] = 0`, `max_power[freq] = -100.0`.
3. Loop passes until `duration_sec` expires or SIGINT:
   - For each frequency: measure power, update `max_power`, increment `active_count` if above threshold.
   - Print progress to stderr: pass number, elapsed/total time, channels found clear.
4. Build `ScanReport` with `mode="recommend"`, populating `active_count` and `total_passes` on each `ScanResult`.

Existing `scan_active` and `scan_clear` methods remain unchanged.

## Ranking and Output

### New function: `format_recommend_report`

```
format_recommend_report(report: ScanReport, top_n: int = 0) -> str
```

1. Compute `ChannelScore` for each frequency in the report.
2. Sort by `score` descending (best channels first).
3. Format as a table:

```
Channel Recommendations (400.000 - 470.000 MHz)
Scanned for 300.0s (12 passes), threshold: -30 dB
Channels scanned: 2800 | Clear: 1847 | Active: 953

Rank  Frequency        Score  Max Power  Active Passes  Status
----  ---------------  -----  ---------  -------------  ------
  1   446.025000 MHz   100.0    -62.3 dB     0 / 12     CLEAR
  2   446.050000 MHz    99.8    -58.1 dB     0 / 12     CLEAR
  3   446.075000 MHz    97.2    -45.6 dB     0 / 12     CLEAR
 ...
 47   451.200000 MHz    42.1    -32.4 dB     3 / 12     INTERMITTENT
```

Status labels: CLEAR (0 active passes), INTERMITTENT (some active passes), BUSY (>50% active passes).

If `top_n > 0`, only the top N channels are shown. Full results are always available via CSV output.

### CSV output: `format_scan_csv`

The existing `format_scan_csv` function already handles `ScanReport`. The new `active_count` and `total_passes` fields will be added as extra CSV columns for recommend-mode reports.

## CLI Command

```
vtms-sdr scan recommend --start 400MHz --end 470MHz --step 25kHz \
    -d 300 --threshold -30 -g auto --ppm 0 \
    --top 20 -o results.csv
```

Options (consistent with existing scan commands):

- `--start`, `--end`, `--step` -- frequency range (required)
- `-d/--duration` -- monitoring duration in seconds (default 300)
- `--threshold` -- power threshold in dB (default -30.0)
- `--top` -- show only top N channels (default: show all)
- `-o/--output` -- save full results to CSV
- `--device`, `-g/--gain`, `--ppm` -- SDR configuration

## Testing

- `ChannelScore` computation and ranking (unit)
- `scan_recommend` method with mock SDR: verify per-pass counts, max power tracking (unit)
- `format_recommend_report` output formatting, `top_n` filtering (unit)
- `format_scan_csv` with recommend-mode report includes new columns (unit)
- CLI `scan recommend --help` shows expected options (integration)
- CLI basic invocation produces output with "Rank" header (integration)
- CLI `--top` flag limits output rows (integration)
- CLI `-o` flag produces CSV file (integration)

## Files Changed

- `src/vtms_sdr/scanner.py` -- extend `ScanResult`, add `ChannelScore`, add `scan_recommend`, add `format_recommend_report`, extend `format_scan_csv`
- `src/vtms_sdr/cli.py` -- add `scan recommend` command
- `tests/test_scanner.py` -- new test classes for recommend functionality
- `tests/test_cli.py` -- new test class for recommend CLI command
