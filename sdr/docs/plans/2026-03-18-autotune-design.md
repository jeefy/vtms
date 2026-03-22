# Auto-Tune Feature Design

**Date:** 2026-03-18
**Status:** Approved

## Summary

Add a dynamic signal probing feature to the vtms-sdr monitor TUI that
automatically determines optimal modulation type (FM/AM/SSB), gain, and
squelch settings by analyzing live IQ samples from the SDR.

## Motivation

Users must manually specify modulation, gain, and squelch via CLI flags or
presets. Choosing the wrong modulation produces garbage audio, and gain/squelch
require trial and error. Auto-tune lets users press a single key to optimize
all three settings based on actual signal characteristics.

## Approach

**Signal Statistics Classifier** -- pure dynamic probing using IQ sample
statistics. No band-plan table or external data needed.

Alternatives considered:
- Hybrid (band plan + dynamic refinement): rejected because user wanted
  purely dynamic probing.
- Multi-demod trial (run all three demods, score audio quality): rejected
  due to complexity and latency (three demod passes per probe).

## Architecture

### New Module: `src/vtms_sdr/autotune.py`

**`AutoTuneResult` dataclass:**
- `modulation: str` -- detected modulation ("fm", "am", "ssb")
- `gain: float` -- recommended gain in dB
- `squelch_db: float` -- recommended squelch threshold
- `signal_power_db: float` -- measured signal power
- `confidence: float` -- classification confidence (0.0--1.0)

**`classify_signal(iq_samples, sample_rate) -> AutoTuneResult`:**

Signal analysis pipeline:

1. **Power measurement**: FFT-based mean power in dB (consistent with
   `scanner.measure_power`).
2. **Envelope analysis**: `|IQ|` amplitude, compute coefficient of variation
   (std/mean).
3. **Instantaneous frequency**: `np.diff(np.unwrap(np.angle(IQ)))`, compute
   coefficient of variation.
4. **Spectral asymmetry**: FFT power ratio between upper and lower halves
   (for SSB detection).
5. **Classification decision tree**:
   - If envelope CV < 0.3 and inst. freq CV > 0.5: FM
   - If envelope CV > 0.5 and inst. freq CV < 0.3: AM
   - If spectral asymmetry ratio > 3:1: SSB
   - Default: FM with lower confidence
6. **Gain mapping**: power to gain lookup (strong > -10 dB: 10 dB gain;
   moderate -10 to -40: 25 dB; weak < -40: 40 dB).
7. **Squelch**: `measured_power - 6 dB`.

### Modified: `src/vtms_sdr/monitor.py`

- New keybinding `a` in `_handle_key()` sets `_autotune_requested = True`.
- New state field `_autotune_status` for displaying results.
- Status line rendered between settings row and volume row, auto-clears
  after ~5 seconds.
- Footer updated to include `a auto-tune`.

### Modified: `src/vtms_sdr/session.py`

- Make `demod` swappable: store in a mutable holder captured by the
  `audio_stream()` closure.
- Wire `_autotune_requested` flag from MonitorUI into the audio stream
  generator.
- When flag is set, classify current IQ block, apply results (gain,
  squelch, modulation swap), update MonitorUI display fields.

### Testing: `tests/test_autotune.py`

- Synthetic FM signal: should classify as FM.
- Synthetic AM signal: should classify as AM.
- Synthetic SSB signal: should classify as SSB.
- Gain mapping and squelch derivation edge cases.
- Noise-only input: should return low confidence.

## Implementation Plan

| Step | What | Files |
|------|------|-------|
| 1 | Create `autotune.py` with dataclass and classifier | `src/vtms_sdr/autotune.py` |
| 2 | Write unit tests with synthetic IQ signals | `tests/test_autotune.py` |
| 3 | Add keybinding and status display to MonitorUI | `src/vtms_sdr/monitor.py` |
| 4 | Wire auto-tune into session pipeline | `src/vtms_sdr/session.py` |
| 5 | Update module exports | `src/vtms_sdr/__init__.py` |
| 6 | Run full test suite | all |
