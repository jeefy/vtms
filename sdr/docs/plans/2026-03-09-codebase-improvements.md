# Codebase Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Address seven improvement areas across the vtms-sdr codebase: TUI wiring, demodulator quality, transcription, scanner, CLI refactor, logging, and cleanup.

**Architecture:** Four batches ordered by dependency — B1 (TUI wiring + cleanup), B2 (demod quality), B3 (transcription + scanner), B4 (CLI refactor + logging). Each batch follows strict RED-GREEN-REFACTOR TDD. B1 and B2 are independent. B4 depends on B1.

**Tech Stack:** Python 3.12, pytest, Click, numpy, scipy, sounddevice, faster-whisper, curses, logging

**Test command:** `source .venv/bin/activate && python -m pytest tests/ -v --tb=short`

---

## Batch 1: TUI Wiring + Cleanup

### Task 1.1: Add progress_callback to AudioRecorder.record()

**Files:**
- Modify: `src/vtms_sdr/recorder.py:29-37` (constructor), `src/vtms_sdr/recorder.py:150-154` (record method), `src/vtms_sdr/recorder.py:294-308` (_print_progress)
- Test: `tests/test_recorder.py`

**Step 1: Write failing tests**

Add to `tests/test_recorder.py`:

```python
class TestAudioRecorderProgressCallback:
    """Test progress_callback parameter on record()."""

    def test_accepts_progress_callback(self, tmp_path):
        """record() should accept a progress_callback kwarg."""
        from vtms_sdr.recorder import AudioRecorder
        output = str(tmp_path / "test.wav")
        recorder = AudioRecorder(output_path=output)
        calls = []
        audio = _make_loud_audio()
        stats = recorder.record(
            _audio_gen([audio]),
            duration=0.1,
            progress_callback=lambda e, s, r: calls.append((e, s, r)),
        )
        assert len(calls) > 0

    def test_progress_callback_receives_data(self, tmp_path):
        """progress_callback should receive (elapsed, samples_written, sample_rate)."""
        from vtms_sdr.recorder import AudioRecorder
        output = str(tmp_path / "test.wav")
        recorder = AudioRecorder(output_path=output)
        calls = []
        audio = _make_loud_audio()
        stats = recorder.record(
            _audio_gen([audio]),
            duration=0.1,
            progress_callback=lambda e, s, r: calls.append((e, s, r)),
        )
        elapsed, samples, rate = calls[-1]
        assert elapsed > 0
        assert samples > 0
        assert rate == 48000

    def test_no_stderr_when_callback_provided(self, tmp_path, capsys):
        """_print_progress should not write to stderr when callback provided."""
        from vtms_sdr.recorder import AudioRecorder
        output = str(tmp_path / "test.wav")
        recorder = AudioRecorder(output_path=output)
        audio = _make_loud_audio()
        recorder.record(
            _audio_gen([audio]),
            duration=0.1,
            progress_callback=lambda e, s, r: None,
        )
        captured = capsys.readouterr()
        assert "Recording:" not in captured.err
```

Note: `_make_loud_audio()` and `_audio_gen()` are helpers that should already exist in test_recorder.py or need to be created. Check existing test helpers before duplicating.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_recorder.py::TestAudioRecorderProgressCallback -v`
Expected: FAIL — `record()` does not accept `progress_callback`

**Step 3: Implement**

In `recorder.py`:
- Add `progress_callback` parameter to `record()` signature (line 150): `progress_callback: Callable[[float, int, int], None] | None = None`
- Add import: `from typing import Callable` (or use `collections.abc.Callable`)
- In the recording loop, where `_print_progress()` is called, add: `if progress_callback: progress_callback(elapsed, samples_written, self._sample_rate)` and gate `_print_progress()` behind `else`

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_recorder.py -v`
Expected: All pass including new tests

**Step 5: Commit**

```
feat(recorder): add progress_callback parameter to record()
```

---

### Task 1.2: Add squelch_callback to AudioRecorder

**Files:**
- Modify: `src/vtms_sdr/recorder.py:29-37` (constructor), recording loop where squelch is evaluated
- Test: `tests/test_recorder.py`

**Step 1: Write failing tests**

```python
class TestAudioRecorderSquelchCallback:
    """Test squelch_callback parameter."""

    def test_accepts_squelch_callback(self, tmp_path):
        """Constructor should accept squelch_callback."""
        from vtms_sdr.recorder import AudioRecorder
        output = str(tmp_path / "test.wav")
        calls = []
        recorder = AudioRecorder(
            output_path=output,
            squelch_callback=lambda is_open, power: calls.append((is_open, power)),
        )
        assert recorder is not None

    def test_squelch_callback_receives_state(self, tmp_path):
        """squelch_callback should be called with (is_open, power_db)."""
        from vtms_sdr.recorder import AudioRecorder
        output = str(tmp_path / "test.wav")
        calls = []
        loud = _make_loud_audio()
        recorder = AudioRecorder(
            output_path=output,
            squelch_db=-30.0,
            squelch_callback=lambda is_open, power: calls.append((is_open, power)),
        )
        recorder.record(_audio_gen([loud]), duration=0.1)
        assert len(calls) > 0
        is_open, power_db = calls[-1]
        assert isinstance(is_open, bool)
        assert isinstance(power_db, float)

    def test_squelch_callback_reflects_signal_state(self, tmp_path):
        """Loud signal should produce squelch_open=True, quiet should produce False."""
        from vtms_sdr.recorder import AudioRecorder
        import numpy as np
        output = str(tmp_path / "test.wav")
        calls = []
        loud = np.random.randn(4800).astype(np.float32)  # Loud
        quiet = np.zeros(4800, dtype=np.float32)  # Silent
        recorder = AudioRecorder(
            output_path=output,
            squelch_db=-30.0,
            squelch_callback=lambda is_open, power: calls.append((is_open, power)),
        )
        recorder.record(_audio_gen([loud, quiet]), duration=0.2)
        opens = [c for c in calls if c[0] is True]
        closes = [c for c in calls if c[0] is False]
        assert len(opens) > 0
        assert len(closes) > 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_recorder.py::TestAudioRecorderSquelchCallback -v`
Expected: FAIL — constructor does not accept `squelch_callback`

**Step 3: Implement**

- Add `squelch_callback: Callable[[bool, float], None] | None = None` to `__init__`
- In the recording loop, after computing `is_above` and `iq_power`, call: `if self._squelch_callback: self._squelch_callback(is_above, iq_power_db)`
- Note: `iq_power_db` may need to be computed. Check what `_is_above_squelch` (line 111) already computes — it receives `iq_power` in dB. The caller should pass the same dB value to the callback.

**Step 4: Run tests**

Run: `pytest tests/test_recorder.py -v`
Expected: All pass

**Step 5: Commit**

```
feat(recorder): add squelch_callback for real-time squelch state reporting
```

---

### Task 1.3: Wire MonitorUI state updates in cli.py

**Files:**
- Modify: `src/vtms_sdr/cli.py:313-392` (monitor setup + recording loop)
- Modify: `src/vtms_sdr/recorder.py` (if needed for callback threading)
- Test: `tests/test_cli.py`

**Step 1: Write failing tests**

Add to the TestRecordMonitorUI class in `tests/test_cli.py`:

```python
@patch("vtms_sdr.monitor.sd")
def test_monitor_receives_progress_callback(self, mock_sd, runner, mock_sdr, tmp_path):
    """MonitorUI.update_progress should be wired as progress_callback."""
    output = str(tmp_path / "test.wav")
    stats = _mock_record_stats(output)
    with patch("vtms_sdr.recorder.AudioRecorder") as mock_recorder_cls, \
         patch("vtms_sdr.monitor.MonitorUI") as mock_ui_cls, \
         patch("vtms_sdr.monitor.AudioMonitor") as mock_am_cls:
        mock_recorder_cls.return_value.record.return_value = stats
        mock_ui_cls.return_value.launch.return_value = stats

        result = runner.invoke(
            main, self._base_args(output, ["--monitor"]),
        )

        # record() should have been called with progress_callback
        record_call = mock_recorder_cls.return_value.record
        call_kwargs = record_call.call_args
        # The record_func is wrapped in launch(), so check that
        # MonitorUI.update_progress is the callback target.
        # This depends on how the wiring is done — check implementation.

@patch("vtms_sdr.monitor.sd")
def test_monitor_receives_squelch_callback(self, mock_sd, runner, mock_sdr, tmp_path):
    """AudioRecorder should be created with squelch_callback pointing to MonitorUI."""
    output = str(tmp_path / "test.wav")
    stats = _mock_record_stats(output)
    with patch("vtms_sdr.recorder.AudioRecorder") as mock_recorder_cls, \
         patch("vtms_sdr.monitor.MonitorUI") as mock_ui_cls, \
         patch("vtms_sdr.monitor.AudioMonitor") as mock_am_cls:
        mock_recorder_cls.return_value.record.return_value = stats
        mock_ui_cls.return_value.launch.return_value = stats

        result = runner.invoke(
            main, self._base_args(output, ["--monitor"]),
        )

        # AudioRecorder should be constructed with squelch_callback
        call_kwargs = mock_recorder_cls.call_args[1]
        assert "squelch_callback" in call_kwargs
        assert call_kwargs["squelch_callback"] is not None
```

**Step 2:** Run tests, verify FAIL.

**Step 3: Implement wiring in cli.py**

In the monitor block (lines 357-375):
```python
if audio_monitor_instance:
    from .monitor import MonitorUI

    audio_monitor_instance.start()
    try:
        monitor_ui = MonitorUI(
            freq=freq,
            mod=mod,
            output_path=output_path,
            squelch_db=squelch,
            audio_monitor=audio_monitor_instance,
        )

        recorder = AudioRecorder(
            output_path=output_path,
            audio_format=audio_format,
            squelch_db=squelch,
            transcriber=transcriber_instance,
            audio_monitor=audio_monitor_instance,
            squelch_callback=monitor_ui.update_squelch,
        )

        def record_func():
            return recorder.record(
                audio_stream(),
                duration=duration,
                progress_callback=monitor_ui.update_progress,
            )

        stats = monitor_ui.launch(record_func)
    finally:
        audio_monitor_instance.stop()
```

Note: Move the `recorder = AudioRecorder(...)` construction inside the `if/else` so the monitor path can pass `squelch_callback` while the non-monitor path doesn't.

**Step 4:** Run tests, verify all pass.

**Step 5: Commit**

```
feat(cli): wire MonitorUI state updates for live progress, squelch, and transcription display
```

---

### Task 1.4: Wire transcription output to MonitorUI

**Files:**
- Modify: `src/vtms_sdr/transcriber.py:256-301` (_flush_buffer output section)
- Modify: `src/vtms_sdr/cli.py` (wiring)
- Test: `tests/test_transcriber.py`, `tests/test_cli.py`

**Step 1: Write failing tests**

In `tests/test_transcriber.py`:

```python
class TestTranscriberUICallback:
    """Test ui_callback parameter for forwarding transcriptions."""

    def test_accepts_ui_callback(self, mock_faster_whisper):
        """Transcriber should accept a ui_callback parameter."""
        t = Transcriber(model_size="tiny", ui_callback=lambda ts, lbl, txt: None)
        assert t is not None

    def test_ui_callback_called_on_transcription(self, mock_faster_whisper):
        """ui_callback should be called with (timestamp, label, text)."""
        calls = []
        t = Transcriber(
            model_size="tiny",
            label="PIT",
            ui_callback=lambda ts, lbl, txt: calls.append((ts, lbl, txt)),
        )
        t.on_squelch_open(0.0)
        t.on_audio_chunk(_make_audio(duration=2.0))
        t.on_squelch_close(2.0)
        assert len(calls) == 1
        ts, label, text = calls[0]
        assert label == "PIT"
        assert isinstance(ts, str)
        assert isinstance(text, str)
```

**Step 2:** Run tests, verify FAIL.

**Step 3: Implement**

- Add `ui_callback: Callable[[str, str, str], None] | None = None` to `Transcriber.__init__`
- In `_flush_buffer()`, after building the transcription output (around line 294), call: `if self._ui_callback: self._ui_callback(timestamp_str, self._label or "", text)`
- In `cli.py`, when both `--monitor` and `--transcribe` are active, pass `monitor_ui.add_transcription` as `ui_callback`

**Step 4:** Run tests, verify all pass.

**Step 5: Commit**

```
feat(transcriber): add ui_callback for forwarding transcriptions to TUI
```

---

### Task 1.5: Cleanup — dead code, imports, preset validation, __all__

**Files:**
- Modify: `src/vtms_sdr/utils.py:15-26` (remove COMMON_STEPS), `src/vtms_sdr/utils.py:120-124` (fix import)
- Modify: `src/vtms_sdr/presets.py:57-70` (expand validation)
- Modify: All `src/vtms_sdr/*.py` (add `__all__`)
- Test: `tests/test_presets.py`

**Step 1: Write failing preset validation tests**

In `tests/test_presets.py`:

```python
class TestValidatePresetTypes:
    """Test type validation for optional preset fields."""

    def test_invalid_gain_type_raises(self, tmp_path):
        data = {"presets": {"bad": {"freq": "146.52M", "gain": [1, 2, 3]}}}
        p = tmp_path / "presets.yaml"
        p.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="gain"):
            load_presets(p)

    def test_invalid_squelch_type_raises(self, tmp_path):
        data = {"presets": {"bad": {"freq": "146.52M", "squelch": "loud"}}}
        p = tmp_path / "presets.yaml"
        p.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="squelch"):
            load_presets(p)

    def test_invalid_ppm_type_raises(self, tmp_path):
        data = {"presets": {"bad": {"freq": "146.52M", "ppm": "five"}}}
        p = tmp_path / "presets.yaml"
        p.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="ppm"):
            load_presets(p)

    def test_valid_gain_auto_accepted(self, tmp_path):
        data = {"presets": {"ok": {"freq": "146.52M", "gain": "auto"}}}
        p = tmp_path / "presets.yaml"
        p.write_text(yaml.dump(data))
        result = load_presets(p)
        assert "ok" in result

    def test_valid_gain_numeric_accepted(self, tmp_path):
        data = {"presets": {"ok": {"freq": "146.52M", "gain": 40.2}}}
        p = tmp_path / "presets.yaml"
        p.write_text(yaml.dump(data))
        result = load_presets(p)
        assert "ok" in result
```

**Step 2:** Run tests, verify FAIL for the raises tests (validation doesn't check these yet).

**Step 3: Implement**

In `presets.py:_validate_preset()`:
```python
def _validate_preset(name: str, settings: dict) -> None:
    if not isinstance(settings, dict) or "freq" not in settings:
        raise ValueError(f"Preset '{name}' must have a 'freq' field")

    mod = settings.get("mod")
    if mod is not None and mod.lower() not in VALID_MODULATIONS:
        raise ValueError(
            f"Preset '{name}': invalid mod '{mod}'. Must be one of {VALID_MODULATIONS}"
        )

    gain = settings.get("gain")
    if gain is not None:
        if not (isinstance(gain, (int, float)) or (isinstance(gain, str) and gain.lower() == "auto")):
            raise ValueError(f"Preset '{name}': gain must be numeric or 'auto', got {type(gain).__name__}")

    squelch = settings.get("squelch")
    if squelch is not None and not isinstance(squelch, (int, float)):
        raise ValueError(f"Preset '{name}': squelch must be numeric, got {type(squelch).__name__}")

    ppm = settings.get("ppm")
    if ppm is not None and not isinstance(ppm, (int, float)):
        raise ValueError(f"Preset '{name}': ppm must be numeric, got {type(ppm).__name__}")

    label = settings.get("label")
    if label is not None and not isinstance(label, str):
        raise ValueError(f"Preset '{name}': label must be a string, got {type(label).__name__}")
```

Then do the cleanup:
- `utils.py`: Remove `COMMON_STEPS` (lines 15-26), remove redundant import in `db_to_power` (line 122)
- All modules: Add `__all__` listing public API

**Step 4:** Run full test suite.

**Step 5: Commit**

```
chore: remove dead code, validate preset types, add __all__ exports
```

---

## Batch 2: Demodulator Quality

### Task 2.1: Extract _multi_decimate to base class

**Files:**
- Modify: `src/vtms_sdr/demod.py:19-79` (base class), remove copies at lines 311-330, 378-396, 465-483
- Test: `tests/test_demod.py`

**Step 1: Write failing test**

```python
def test_multi_decimate_on_base_class():
    """_multi_decimate should be defined on Demodulator base class."""
    assert hasattr(Demodulator, '_multi_decimate')
```

**Step 2:** Run, verify FAIL.

**Step 3:** Move `_multi_decimate` to `Demodulator` base class, remove from FM/AM/SSB.

**Step 4:** Run full demod test suite — all 22 tests should pass unchanged.

**Step 5: Commit**

```
refactor(demod): extract _multi_decimate to Demodulator base class
```

---

### Task 2.2: Vectorize FM _dc_block and _apply_deemphasis

**Files:**
- Modify: `src/vtms_sdr/demod.py:247-251` (_dc_block), `src/vtms_sdr/demod.py:263-265` (_apply_deemphasis)
- Test: `tests/test_demod.py`

**Step 1: Write tests**

No new behavioral tests needed — existing fidelity tests cover the output. Add a regression test:

```python
def test_fm_demod_output_unchanged_after_vectorize():
    """FM demodulator should produce identical output after vectorization."""
    demod = FMDemodulator(sample_rate=2_400_000)
    iq = _make_fm_signal(tone_hz=1000, duration_ms=100)
    audio = demod.demodulate(iq)
    # Just verify it runs and produces reasonable output
    assert audio.dtype == np.float32
    assert len(audio) > 0
    assert np.max(np.abs(audio)) <= 1.0
```

**Step 2:** Run, verify PASS (baseline).

**Step 3: Vectorize**

Replace `_dc_block` Python loop with:
```python
def _dc_block(self, signal: np.ndarray) -> np.ndarray:
    b = np.array([1.0, -1.0])
    a = np.array([1.0, -self._dc_alpha])
    filtered, self._filter_state["dc_zi"] = lfilter(b, a, signal, zi=self._filter_state.get("dc_zi", lfilter_zi(b, a) * signal[0]))
    return filtered
```

Replace `_apply_deemphasis` Python loop with:
```python
def _apply_deemphasis(self, audio: np.ndarray) -> np.ndarray:
    alpha = self._deemph_alpha
    b = np.array([1.0 - alpha])
    a = np.array([1.0, -alpha])
    result, self._filter_state["deemph_zi"] = lfilter(b, a, audio, zi=self._filter_state.get("deemph_zi", lfilter_zi(b, a) * audio[0]))
    return result
```

Note: Use `scipy.signal.lfilter_zi` for initial conditions.

**Step 4:** Run all demod tests. Verify fidelity tests still pass.

**Step 5: Commit**

```
perf(demod): vectorize FM _dc_block and _apply_deemphasis using lfilter
```

---

### Task 2.3: Fix AM cross-block filter state

**Files:**
- Modify: `src/vtms_sdr/demod.py:343-374` (AM demodulate + filter setup)
- Test: `tests/test_demod.py`

**Step 1: Write failing test**

```python
class TestAMCrossBlockContinuity:
    """AM demodulator should maintain filter state across blocks."""

    def test_am_no_discontinuity_at_block_boundary(self):
        """Output should be smooth across block boundaries."""
        demod = AMDemodulator(sample_rate=2_400_000)
        iq = _make_am_signal(tone_hz=1000, duration_ms=200)
        mid = len(iq) // 2

        # Process as two blocks
        audio1 = demod.demodulate(iq[:mid])
        audio2 = demod.demodulate(iq[mid:])
        joined = np.concatenate([audio1, audio2])

        # Process as one block (fresh demod)
        demod_single = AMDemodulator(sample_rate=2_400_000)
        audio_single = demod_single.demodulate(iq)

        # The joined output should be close to single-block output
        min_len = min(len(joined), len(audio_single))
        correlation = np.corrcoef(joined[:min_len], audio_single[:min_len])[0, 1]
        assert correlation > 0.95, f"Cross-block correlation too low: {correlation}"
```

**Step 2:** Run, verify FAIL (correlation will be low due to filter transients).

**Step 3: Implement**

Add `_filter_state` dict to `AMDemodulator.__init__`. Maintain `zi` arrays for channel filter and DC filter across calls to `demodulate()`. Pattern: copy FM's approach at lines 142-143 and 192-203.

**Step 4:** Run test, verify PASS.

**Step 5: Commit**

```
fix(demod): maintain AM filter state across blocks to prevent click artifacts
```

---

### Task 2.4: Fix SSB cross-block filter state

**Files:**
- Modify: `src/vtms_sdr/demod.py:420-461` (SSB demodulate + filter setup)
- Test: `tests/test_demod.py`

Same pattern as Task 2.3 but for SSB. Add `_filter_state` dict, maintain `zi` for SSB lowpass filter.

---

### Task 2.5: Fix AM/SSB per-block normalization

**Files:**
- Modify: `src/vtms_sdr/demod.py:372-374` (AM), `src/vtms_sdr/demod.py:459-461` (SSB)
- Test: `tests/test_demod.py`

**Step 1: Write failing test**

```python
class TestAMAmplitudeStability:
    """AM demodulator should not independently normalize each block."""

    def test_quiet_block_stays_quiet(self):
        """A quiet block should produce quieter output than a loud block."""
        demod = AMDemodulator(sample_rate=2_400_000)
        loud_iq = _make_am_signal(tone_hz=1000, duration_ms=100, mod_depth=0.9)
        quiet_iq = _make_am_signal(tone_hz=1000, duration_ms=100, mod_depth=0.1)

        loud_audio = demod.demodulate(loud_iq)
        quiet_audio = demod.demodulate(quiet_iq)

        loud_rms = np.sqrt(np.mean(loud_audio ** 2))
        quiet_rms = np.sqrt(np.mean(quiet_audio ** 2))
        assert quiet_rms < loud_rms * 0.5, "Quiet block should be significantly quieter"
```

**Step 2:** Run, verify FAIL (per-block normalization makes both similar amplitude).

**Step 3: Implement**

Replace per-block `audio / max_val * 0.9` with a simple running-average AGC:
- Track `_agc_level` as an exponential moving average of RMS
- Apply gain relative to target level (e.g., 0.3 RMS)
- Clip to [-1.0, 1.0]
- Same approach for SSB

**Step 4:** Run tests.

**Step 5: Commit**

```
fix(demod): replace per-block normalization with running AGC for AM/SSB
```

---

## Batch 3: Transcription + Scanner

### Task 3.1: Model caching for transcribe_file()

**Files:**
- Modify: `src/vtms_sdr/transcriber.py:367-472` (transcribe_file function)
- Test: `tests/test_transcriber.py`

**Step 1: Write failing tests**

```python
class TestModelCache:
    """Test Whisper model caching."""

    def test_second_call_reuses_model(self, mock_faster_whisper, tmp_path):
        """Calling transcribe_file twice should reuse the cached model."""
        wav = _make_test_wav(tmp_path / "test.wav")
        transcribe_file(wav, model_size="tiny")
        transcribe_file(wav, model_size="tiny")
        # FWModel should only be called once
        from vtms_sdr.transcriber import _MODEL_CACHE
        assert "tiny" in _MODEL_CACHE

    def test_different_model_creates_new_entry(self, mock_faster_whisper, tmp_path):
        """Different model sizes should get separate cache entries."""
        wav = _make_test_wav(tmp_path / "test.wav")
        transcribe_file(wav, model_size="tiny")
        transcribe_file(wav, model_size="base")
        from vtms_sdr.transcriber import _MODEL_CACHE
        assert "tiny" in _MODEL_CACHE
        assert "base" in _MODEL_CACHE
```

**Step 2:** FAIL — `_MODEL_CACHE` does not exist.

**Step 3: Implement**

Add module-level `_MODEL_CACHE: dict[str, Any] = {}` to transcriber.py. In `transcribe_file()`, check cache before creating model. Add `clear_model_cache()` for testing.

**Step 4:** Run tests.

**Step 5: Commit**

```
perf(transcriber): cache Whisper models to avoid reloading on repeated calls
```

---

### Task 3.2: Extract shared whisper transcription helper

**Files:**
- Modify: `src/vtms_sdr/transcriber.py:303-345` (_transcribe), `src/vtms_sdr/transcriber.py:432-441` (transcribe_file)
- Test: `tests/test_transcriber.py`

**Step 1:** Extract `_run_whisper(model, audio, language) -> list[tuple[str, str]]` as a module-level function. Both `_transcribe()` and `transcribe_file()` call it.

**Step 2:** Run all transcriber tests — should pass unchanged.

**Step 3: Commit**

```
refactor(transcriber): extract _run_whisper helper to deduplicate transcription call
```

---

### Task 3.3: Scanner PLL settling delay

**Files:**
- Modify: `src/vtms_sdr/scanner.py:85-106` (measure_power)
- Test: `tests/test_scanner.py`

**Step 1: Write failing test**

```python
def test_measure_power_discards_settling_samples(self, mock_sdr):
    """measure_power should read and discard samples for PLL settling."""
    scanner = FrequencyScanner(mock_sdr, threshold_db=-50)
    scanner.measure_power(146_520_000)
    # read_samples should be called at least twice — once for settling, once for measurement
    assert mock_sdr.read_samples.call_count >= 2
```

**Step 2:** FAIL — currently only one read_samples call.

**Step 3: Implement**

In `measure_power()`, add a settling read before the measurement:
```python
def measure_power(self, freq_hz: int) -> float:
    self.sdr.configure(center_freq=freq_hz, sample_rate=DEFAULT_SAMPLE_RATE)
    # Discard first read for PLL settling
    self.sdr.read_samples(self.dwell_samples)
    # Measurement read
    samples = self.sdr.read_samples(self.dwell_samples)
    ...
```

**Step 4:** Run tests.

**Step 5: Commit**

```
fix(scanner): add PLL settling delay before power measurement
```

---

### Task 3.4: Add --ppm to scan commands

**Files:**
- Modify: `src/vtms_sdr/cli.py:422-506` (scan_active), `src/vtms_sdr/cli.py:572-665` (scan_clear)
- Modify: `src/vtms_sdr/scanner.py:85-106` (pass ppm to configure)
- Test: `tests/test_cli.py`, `tests/test_scanner.py`

**Step 1: Write failing tests**

```python
def test_scan_active_ppm_in_help(self, runner):
    result = runner.invoke(main, ["scan", "active", "--help"])
    assert "--ppm" in result.output

def test_scan_clear_ppm_in_help(self, runner):
    result = runner.invoke(main, ["scan", "clear", "--help"])
    assert "--ppm" in result.output
```

**Step 2:** FAIL.

**Step 3:** Add `@click.option("--ppm", ...)` to both scan commands. Pass through to `FrequencyScanner` or to `sdr.configure()`. The scanner's `measure_power()` should accept and forward `ppm`.

**Step 4:** Run tests.

**Step 5: Commit**

```
feat(scanner): add --ppm flag to scan active and scan clear commands
```

---

## Batch 4: CLI Refactor + Logging

### Task 4.1: Create session.py orchestration module

**Files:**
- Create: `src/vtms_sdr/session.py`
- Modify: `src/vtms_sdr/cli.py:167-411` (record function)
- Create: `tests/test_session.py`
- Test: `tests/test_cli.py` (existing tests should still pass)

**Step 1: Design RecordConfig and RecordingSession**

```python
@dataclass
class RecordConfig:
    """Resolved configuration for a recording session."""
    freq: int
    mod: str
    output_path: Path
    audio_format: str
    duration: float | None
    gain: str | float
    squelch_db: float
    device: int
    ppm: int
    transcriber: Transcriber | None
    monitor: bool
    volume: float
    label: str | None

class RecordingSession:
    """Orchestrates an SDR recording session."""

    def __init__(self, config: RecordConfig) -> None:
        self.config = config

    def run(self) -> dict:
        """Execute the recording session. Returns stats dict."""
        ...
```

**Step 2: Write tests for RecordingSession**

Test the session with mocked SDR, demodulator, and recorder — similar to existing CLI tests but without Click.

**Step 3: Implement session.py**

Extract the body of `record()` (lines ~201-404) into `RecordingSession.run()`. The `cli.py:record()` function becomes:
1. Parse Click options
2. Resolve presets
3. Build `RecordConfig`
4. Call `RecordingSession(config).run()`
5. Print results

**Step 4:** Run full test suite — all existing CLI tests must still pass.

**Step 5: Commit**

```
refactor(cli): extract recording pipeline into RecordingSession in session.py
```

---

### Task 4.2: Replace print() with logging module

**Files:**
- Modify: `src/vtms_sdr/sdr.py` (stream error handler)
- Modify: `src/vtms_sdr/scanner.py` (signal handler, status messages)
- Modify: `src/vtms_sdr/recorder.py` (_print_progress)
- Modify: `src/vtms_sdr/transcriber.py` (stderr output)
- Test: Minimal — verify no print() calls remain

**Step 1: Add logger to each module**

At top of each file:
```python
import logging
logger = logging.getLogger(__name__)
```

**Step 2: Replace print() calls**

- `sdr.py`: `print("IOError...", file=sys.stderr)` → `logger.warning("IOError during streaming: %s", e)`
- `scanner.py`: `print("\nStopping scan...", file=sys.stderr)` → `logger.info("Stopping scan...")`
- `recorder.py`: `_print_progress()` stderr output → `logger.info(...)` (only when no progress_callback)
- `transcriber.py`: `print(...)` stderr output → `logger.info(...)` for transcription, `logger.error(...)` for errors

**Step 3: Verify**

Run: `grep -rn 'print(' src/vtms_sdr/ | grep -v '__pycache__'` — should return zero results (except any intentional stdout output in CLI).

**Step 4: Commit**

```
refactor: replace print() with logging module throughout
```

---

### Task 4.3: Add --verbose flag

**Files:**
- Modify: `src/vtms_sdr/cli.py:43-51` (main group)
- Test: `tests/test_cli.py`

**Step 1: Write failing test**

```python
def test_verbose_flag_in_help(self, runner):
    result = runner.invoke(main, ["--help"])
    assert "--verbose" in result.output or "-v" in result.output
```

**Step 2:** FAIL.

**Step 3: Implement**

```python
@click.group()
@click.version_option(...)
@click.option("-v", "--verbose", count=True, help="Increase verbosity (-v info, -vv debug).")
@click.pass_context
def main(ctx, verbose):
    """vtms-sdr: ..."""
    ctx.ensure_object(dict)
    level = logging.WARNING
    if verbose == 1:
        level = logging.INFO
    elif verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(name)s: %(message)s", stream=sys.stderr)
```

**Step 4:** Run tests.

**Step 5: Commit**

```
feat(cli): add --verbose / -v flag for controlling log verbosity
```

---

### Task 4.4: Make pydub optional

**Files:**
- Modify: `pyproject.toml` (move pydub to optional)
- Modify: `src/vtms_sdr/recorder.py` (improve error message)

**Step 1:** Move `pydub>=0.25.0` from `dependencies` to `[project.optional-dependencies]` under an `mp3` key.

**Step 2:** In recorder.py where pydub is lazily imported, improve the error:
```python
try:
    from pydub import AudioSegment
except ImportError:
    raise RuntimeError(
        "MP3 output requires pydub. Install with: pip install vtms-sdr[mp3]"
    )
```

**Step 3:** Run tests (MP3 tests should still pass if pydub is installed).

**Step 4: Commit**

```
chore: make pydub optional under [mp3] extra dependency
```

---

## Verification Checklist

After all batches, run:

1. `pytest tests/ -v --tb=short` — all tests pass
2. `grep -rn 'print(' src/vtms_sdr/ | grep -v '__pycache__'` — no stray print() calls
3. `grep -rn 'COMMON_STEPS' src/` — no references to removed constant
4. `python -c "from vtms_sdr import utils; print(utils.__all__)"` — exports defined
5. `vtms-sdr --help` — `--verbose` flag visible
6. `vtms-sdr scan active --help` — `--ppm` flag visible
