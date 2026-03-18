# TUI Enhancement: Live Squelch/Gain/PPM Adjustment + Model Display

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add live runtime adjustment of squelch, gain, and PPM via keyboard shortcuts in the curses MonitorUI, and display the Whisper model size in the TUI header.

**Architecture:** Three layers of changes: (1) SDRDevice gets individual `set_gain()`/`set_ppm()` setter methods, (2) MonitorUI gets new optional constructor params (`model_size`, `gain`, `ppm`, `sdr_device`, `recorder`) and new key handlers (s/S, g/G, p/P), new display rows for the settings, and updated footer, (3) session.py wires the new params through when constructing MonitorUI. All existing constructor params remain unchanged for backward compatibility — new params are keyword-only with defaults.

**Tech Stack:** Python 3.12, curses, pytest, unittest.mock

**Baseline:** 353 tests passing. NOT a git repo — skip all commit steps.

---

### Task 1: SDRDevice.set_gain() and set_ppm()

**Files:**
- Modify: `src/vtms_sdr/sdr.py:83-117` (add two new methods after `configure()`)
- Test: `tests/test_sdr.py`

**Step 1: Write the failing tests**

Add to `tests/test_sdr.py`:

```python
class TestSDRDeviceSetGain:
    """Test SDRDevice.set_gain() individual setter."""

    def test_set_gain_numeric(self):
        """set_gain(20.0) sets gain to 20.0 on the underlying device."""
        from vtms_sdr.sdr import SDRDevice

        sdr = SDRDevice(device_index=0)
        sdr._sdr = MagicMock()
        sdr.set_gain(20.0)
        assert sdr._sdr.gain == 20.0

    def test_set_gain_auto(self):
        """set_gain('auto') sets gain to 'auto' on the underlying device."""
        from vtms_sdr.sdr import SDRDevice

        sdr = SDRDevice(device_index=0)
        sdr._sdr = MagicMock()
        sdr.set_gain("auto")
        assert sdr._sdr.gain == "auto"

    def test_set_gain_raises_when_closed(self):
        """set_gain() raises RuntimeError if device not open."""
        from vtms_sdr.sdr import SDRDevice

        sdr = SDRDevice(device_index=0)
        sdr._sdr = None
        with pytest.raises(RuntimeError, match="not open"):
            sdr.set_gain(20.0)


class TestSDRDeviceSetPPM:
    """Test SDRDevice.set_ppm() individual setter."""

    def test_set_ppm(self):
        """set_ppm(5) sets freq_correction to 5."""
        from vtms_sdr.sdr import SDRDevice

        sdr = SDRDevice(device_index=0)
        sdr._sdr = MagicMock()
        sdr.set_ppm(5)
        assert sdr._sdr.freq_correction == 5

    def test_set_ppm_zero(self):
        """set_ppm(0) sets freq_correction to 0."""
        from vtms_sdr.sdr import SDRDevice

        sdr = SDRDevice(device_index=0)
        sdr._sdr = MagicMock()
        sdr.set_ppm(0)
        assert sdr._sdr.freq_correction == 0

    def test_set_ppm_raises_when_closed(self):
        """set_ppm() raises RuntimeError if device not open."""
        from vtms_sdr.sdr import SDRDevice

        sdr = SDRDevice(device_index=0)
        sdr._sdr = None
        with pytest.raises(RuntimeError, match="not open"):
            sdr.set_ppm(5)
```

**Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_sdr.py -k "SetGain or SetPPM" -v`
Expected: FAIL — `AttributeError: 'SDRDevice' object has no attribute 'set_gain'`

**Step 3: Write minimal implementation**

Add to `src/vtms_sdr/sdr.py` after the `configure()` method (after line 117):

```python
    def set_gain(self, gain: str | float) -> None:
        """Set the SDR gain at runtime.

        Args:
            gain: Gain in dB, or 'auto' for automatic gain.

        Raises:
            RuntimeError: If device is not open.
        """
        if self._sdr is None:
            raise RuntimeError("SDR device is not open")

        if gain == "auto":
            self._sdr.gain = "auto"
        else:
            self._sdr.gain = float(gain)

    def set_ppm(self, ppm: int) -> None:
        """Set the PPM frequency correction at runtime.

        Args:
            ppm: Crystal oscillator frequency correction in parts-per-million.

        Raises:
            RuntimeError: If device is not open.
        """
        if self._sdr is None:
            raise RuntimeError("SDR device is not open")

        self._sdr.freq_correction = int(ppm)
```

**Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_sdr.py -k "SetGain or SetPPM" -v`
Expected: 6 passed

**Step 5: Run full suite**

Run: `source .venv/bin/activate && python -m pytest tests/ -v --tb=short`
Expected: 359 passed (353 + 6)

---

### Task 2: MonitorUI new constructor params (backward compatible)

**Files:**
- Modify: `src/vtms_sdr/monitor.py:150-172` (extend `__init__`)
- Test: `tests/test_monitor_ui.py`

**Step 1: Write the failing tests**

Add new test class to `tests/test_monitor_ui.py`:

```python
class TestMonitorUIExtendedInit:
    """Test MonitorUI extended constructor params for TUI enhancements."""

    def test_default_model_size_is_none(self):
        """model_size defaults to None when not provided."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui.model_size is None

    def test_stores_model_size(self):
        """MonitorUI stores model_size when provided."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            model_size="medium",
        )
        assert ui.model_size == "medium"

    def test_default_gain_is_none(self):
        """gain defaults to None when not provided."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui.gain is None

    def test_stores_gain(self):
        """MonitorUI stores gain when provided."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            gain=20.0,
        )
        assert ui.gain == 20.0

    def test_stores_gain_auto(self):
        """MonitorUI stores 'auto' gain."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            gain="auto",
        )
        assert ui.gain == "auto"

    def test_default_ppm_is_none(self):
        """ppm defaults to None when not provided."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui.ppm is None

    def test_stores_ppm(self):
        """MonitorUI stores ppm when provided."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            ppm=5,
        )
        assert ui.ppm == 5

    def test_default_sdr_device_is_none(self):
        """sdr_device defaults to None."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui.sdr_device is None

    def test_stores_sdr_device(self):
        """MonitorUI stores sdr_device when provided."""
        from vtms_sdr.monitor import MonitorUI

        sdr = MagicMock()
        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            sdr_device=sdr,
        )
        assert ui.sdr_device is sdr

    def test_default_recorder_is_none(self):
        """recorder defaults to None."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui.recorder is None

    def test_stores_recorder(self):
        """MonitorUI stores recorder when provided."""
        from vtms_sdr.monitor import MonitorUI

        recorder = MagicMock()
        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
            recorder=recorder,
        )
        assert ui.recorder is recorder

    def test_existing_tests_still_pass_without_new_params(self):
        """All existing constructor calls with 5 args still work."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        ui = MonitorUI(
            freq=146520000,
            mod="fm",
            output_path="/tmp/test.wav",
            squelch_db=-40.0,
            audio_monitor=monitor,
        )
        assert ui.freq == 146520000
        assert ui.stopped is False
```

**Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_monitor_ui.py::TestMonitorUIExtendedInit -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'model_size'`

**Step 3: Write minimal implementation**

Modify `src/vtms_sdr/monitor.py:150-172` — extend `__init__` signature:

```python
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

        self._lock = threading.Lock()
        self._state: dict = {
            "elapsed": 0.0,
            "audio_duration": 0.0,
            "squelch_open": False,
            "power_db": -100.0,
            "transcriptions": [],
        }
```

Also add forward-reference type imports near the top of monitor.py (inside `TYPE_CHECKING`):

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .sdr import SDRDevice
    from .recorder import AudioRecorder
```

**Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_monitor_ui.py -v --tb=short`
Expected: All pass (existing + new)

---

### Task 3: Key handlers for squelch/gain/PPM adjustment

**Files:**
- Modify: `src/vtms_sdr/monitor.py:199-210` (`_handle_key`)
- Test: `tests/test_monitor_ui.py`

**Step 1: Write the failing tests**

```python
class TestMonitorUILiveAdjustKeys:
    """Test squelch/gain/PPM key handlers."""

    # --- Squelch keys (s/S) ---

    def test_s_decreases_squelch_by_1(self):
        """'s' key decreases squelch_db by 1 and updates recorder."""
        from vtms_sdr.monitor import MonitorUI

        recorder = MagicMock()
        recorder.squelch_db = -30.0
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000, mod="fm", output_path="/tmp/test.wav",
            squelch_db=-30.0, audio_monitor=monitor, recorder=recorder,
        )
        ui._handle_key(ord("s"))
        assert ui.squelch_db == -31.0
        assert recorder.squelch_db == -31.0

    def test_S_increases_squelch_by_1(self):
        """'S' key increases squelch_db by 1 and updates recorder."""
        from vtms_sdr.monitor import MonitorUI

        recorder = MagicMock()
        recorder.squelch_db = -30.0
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000, mod="fm", output_path="/tmp/test.wav",
            squelch_db=-30.0, audio_monitor=monitor, recorder=recorder,
        )
        ui._handle_key(ord("S"))
        assert ui.squelch_db == -29.0
        assert recorder.squelch_db == -29.0

    def test_squelch_no_recorder_still_updates_ui(self):
        """Squelch keys update UI squelch_db even without recorder."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000, mod="fm", output_path="/tmp/test.wav",
            squelch_db=-30.0, audio_monitor=monitor,
        )
        ui._handle_key(ord("s"))
        assert ui.squelch_db == -31.0

    # --- Gain keys (g/G) ---

    def test_g_decreases_gain_by_1(self):
        """'g' key decreases gain by 1 and calls sdr_device.set_gain()."""
        from vtms_sdr.monitor import MonitorUI

        sdr = MagicMock()
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000, mod="fm", output_path="/tmp/test.wav",
            squelch_db=-30.0, audio_monitor=monitor,
            gain=20.0, sdr_device=sdr,
        )
        ui._handle_key(ord("g"))
        assert ui.gain == 19.0
        sdr.set_gain.assert_called_once_with(19.0)

    def test_G_increases_gain_by_1(self):
        """'G' key increases gain by 1 and calls sdr_device.set_gain()."""
        from vtms_sdr.monitor import MonitorUI

        sdr = MagicMock()
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000, mod="fm", output_path="/tmp/test.wav",
            squelch_db=-30.0, audio_monitor=monitor,
            gain=20.0, sdr_device=sdr,
        )
        ui._handle_key(ord("G"))
        assert ui.gain == 21.0
        sdr.set_gain.assert_called_once_with(21.0)

    def test_gain_auto_converts_to_20_on_first_adjustment(self):
        """If gain is 'auto', first key press converts to 20.0 then adjusts."""
        from vtms_sdr.monitor import MonitorUI

        sdr = MagicMock()
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000, mod="fm", output_path="/tmp/test.wav",
            squelch_db=-30.0, audio_monitor=monitor,
            gain="auto", sdr_device=sdr,
        )
        ui._handle_key(ord("g"))
        assert ui.gain == 19.0
        sdr.set_gain.assert_called_once_with(19.0)

    def test_gain_clamps_at_0(self):
        """Gain should not go below 0."""
        from vtms_sdr.monitor import MonitorUI

        sdr = MagicMock()
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000, mod="fm", output_path="/tmp/test.wav",
            squelch_db=-30.0, audio_monitor=monitor,
            gain=0.5, sdr_device=sdr,
        )
        ui._handle_key(ord("g"))
        assert ui.gain == 0.0
        sdr.set_gain.assert_called_once_with(0.0)

    def test_gain_clamps_at_50(self):
        """Gain should not exceed 50."""
        from vtms_sdr.monitor import MonitorUI

        sdr = MagicMock()
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000, mod="fm", output_path="/tmp/test.wav",
            squelch_db=-30.0, audio_monitor=monitor,
            gain=49.5, sdr_device=sdr,
        )
        ui._handle_key(ord("G"))
        assert ui.gain == 50.0
        sdr.set_gain.assert_called_once_with(50.0)

    def test_gain_no_sdr_still_updates_ui(self):
        """Gain keys update UI gain even without sdr_device."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000, mod="fm", output_path="/tmp/test.wav",
            squelch_db=-30.0, audio_monitor=monitor,
            gain=20.0,
        )
        ui._handle_key(ord("g"))
        assert ui.gain == 19.0

    def test_gain_none_ignores_keys(self):
        """If gain is None (not provided), gain keys are ignored."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000, mod="fm", output_path="/tmp/test.wav",
            squelch_db=-30.0, audio_monitor=monitor,
        )
        ui._handle_key(ord("g"))
        assert ui.gain is None

    # --- PPM keys (p/P) ---

    def test_p_decreases_ppm_by_1(self):
        """'p' key decreases ppm by 1 and calls sdr_device.set_ppm()."""
        from vtms_sdr.monitor import MonitorUI

        sdr = MagicMock()
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000, mod="fm", output_path="/tmp/test.wav",
            squelch_db=-30.0, audio_monitor=monitor,
            ppm=5, sdr_device=sdr,
        )
        ui._handle_key(ord("p"))
        assert ui.ppm == 4
        sdr.set_ppm.assert_called_once_with(4)

    def test_P_increases_ppm_by_1(self):
        """'P' key increases ppm by 1 and calls sdr_device.set_ppm()."""
        from vtms_sdr.monitor import MonitorUI

        sdr = MagicMock()
        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000, mod="fm", output_path="/tmp/test.wav",
            squelch_db=-30.0, audio_monitor=monitor,
            ppm=5, sdr_device=sdr,
        )
        ui._handle_key(ord("P"))
        assert ui.ppm == 6
        sdr.set_ppm.assert_called_once_with(6)

    def test_ppm_no_sdr_still_updates_ui(self):
        """PPM keys update UI ppm even without sdr_device."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000, mod="fm", output_path="/tmp/test.wav",
            squelch_db=-30.0, audio_monitor=monitor,
            ppm=5,
        )
        ui._handle_key(ord("p"))
        assert ui.ppm == 4

    def test_ppm_none_ignores_keys(self):
        """If ppm is None (not provided), ppm keys are ignored."""
        from vtms_sdr.monitor import MonitorUI

        monitor = MagicMock()
        monitor.volume = 0.5
        ui = MonitorUI(
            freq=146520000, mod="fm", output_path="/tmp/test.wav",
            squelch_db=-30.0, audio_monitor=monitor,
        )
        ui._handle_key(ord("p"))
        assert ui.ppm is None
```

**Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_monitor_ui.py::TestMonitorUILiveAdjustKeys -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Replace `_handle_key` in `src/vtms_sdr/monitor.py`:

```python
    SQUELCH_STEP = 1.0
    GAIN_STEP = 1.0
    GAIN_DEFAULT = 20.0
    GAIN_MIN = 0.0
    GAIN_MAX = 50.0
    PPM_STEP = 1

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
        elif key == ord("q") or key == ord("Q"):
            self.stopped = True
```

**Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_monitor_ui.py -v --tb=short`
Expected: All pass

---

### Task 4: Updated _draw() with new display rows

**Files:**
- Modify: `src/vtms_sdr/monitor.py:241-321` (`_draw`)
- Test: `tests/test_monitor_ui.py`

**Step 1: Write the failing tests**

```python
class TestMonitorUIDrawEnhancements:
    """Test the enhanced _draw() display rows."""

    def _make_ui(self, **kwargs):
        """Helper to create MonitorUI with common defaults."""
        from vtms_sdr.monitor import MonitorUI

        defaults = dict(
            freq=146520000, mod="fm", output_path="/tmp/test.wav",
            squelch_db=-30.0, audio_monitor=MagicMock(volume=0.5),
        )
        defaults.update(kwargs)
        return MonitorUI(**defaults)

    def test_draw_shows_model_size(self):
        """_draw() includes 'Model: medium' when model_size is set."""
        ui = self._make_ui(model_size="medium")
        stdscr = MagicMock()
        stdscr.getmaxyx.return_value = (40, 100)
        ui._draw(stdscr)

        drawn = " ".join(
            str(call.args[2]) for call in stdscr.addstr.call_args_list
            if len(call.args) >= 3
        )
        assert "Model: medium" in drawn

    def test_draw_no_model_row_when_none(self):
        """_draw() does not show model row when model_size is None."""
        ui = self._make_ui()
        stdscr = MagicMock()
        stdscr.getmaxyx.return_value = (40, 100)
        ui._draw(stdscr)

        drawn = " ".join(
            str(call.args[2]) for call in stdscr.addstr.call_args_list
            if len(call.args) >= 3
        )
        assert "Model:" not in drawn

    def test_draw_shows_gain(self):
        """_draw() includes gain value when gain is set."""
        ui = self._make_ui(gain=20.0)
        stdscr = MagicMock()
        stdscr.getmaxyx.return_value = (40, 100)
        ui._draw(stdscr)

        drawn = " ".join(
            str(call.args[2]) for call in stdscr.addstr.call_args_list
            if len(call.args) >= 3
        )
        assert "Gain:" in drawn
        assert "20.0" in drawn

    def test_draw_shows_gain_auto(self):
        """_draw() shows 'auto' for gain when set to auto."""
        ui = self._make_ui(gain="auto")
        stdscr = MagicMock()
        stdscr.getmaxyx.return_value = (40, 100)
        ui._draw(stdscr)

        drawn = " ".join(
            str(call.args[2]) for call in stdscr.addstr.call_args_list
            if len(call.args) >= 3
        )
        assert "Gain:" in drawn
        assert "auto" in drawn

    def test_draw_shows_ppm(self):
        """_draw() includes PPM value when ppm is set."""
        ui = self._make_ui(ppm=5)
        stdscr = MagicMock()
        stdscr.getmaxyx.return_value = (40, 100)
        ui._draw(stdscr)

        drawn = " ".join(
            str(call.args[2]) for call in stdscr.addstr.call_args_list
            if len(call.args) >= 3
        )
        assert "PPM:" in drawn
        assert "5" in drawn

    def test_draw_footer_shows_key_hints(self):
        """Footer includes key hints for new controls."""
        ui = self._make_ui(gain=20.0, ppm=5)
        stdscr = MagicMock()
        stdscr.getmaxyx.return_value = (40, 100)
        ui._draw(stdscr)

        drawn = " ".join(
            str(call.args[2]) for call in stdscr.addstr.call_args_list
            if len(call.args) >= 3
        )
        assert "s/S" in drawn
        assert "g/G" in drawn
        assert "p/P" in drawn
```

**Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_monitor_ui.py::TestMonitorUIDrawEnhancements -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Replace `_draw()` in `src/vtms_sdr/monitor.py`:

```python
    def _draw(self, stdscr) -> None:
        """Draw the monitoring UI to the curses screen."""
        state = self._get_state_snapshot()
        height, width = stdscr.getmaxyx()

        stdscr.erase()

        row = 0
        # Title
        title = " vtms-sdr Monitor "
        if width >= len(title) + 4:
            stdscr.addstr(
                row,
                0,
                f"\u250c\u2500{title}" + "\u2500" * (width - len(title) - 4) + "\u2510",
            )
        row += 1

        # Frequency and modulation
        freq_line = (
            f"  Frequency: {self._format_freq()}   Modulation: {self.mod.upper()}"
        )
        stdscr.addstr(row, 0, freq_line[: width - 1])
        row += 1

        # Recording duration and file
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(state["elapsed"]))
        audio_str = time.strftime("%H:%M:%S", time.gmtime(state["audio_duration"]))
        out_name = Path(self.output_path).name
        if len(out_name) > width - 40:
            out_name = out_name[: width - 43] + "..."
        rec_line = f"  Recording: {elapsed_str}   Audio: {audio_str}   File: {out_name}"
        stdscr.addstr(row, 0, rec_line[: width - 1])
        row += 1

        # Squelch
        squelch_status = "OPEN" if state["squelch_open"] else "CLOSED"
        squelch_line = (
            f"  Squelch: {squelch_status}  "
            f"({state['power_db']:.1f} dB / {self.squelch_db:.1f} dB)   [s/S \u00b11 dB]"
        )
        stdscr.addstr(row, 0, squelch_line[: width - 1])
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
            stdscr.addstr(row, 0, settings_line[: width - 1])
            row += 1

        # Whisper model (only if provided)
        if self.model_size is not None:
            model_line = f"  Model: {self.model_size}"
            stdscr.addstr(row, 0, model_line[: width - 1])
            row += 1

        # Volume
        vol_pct = int(self._audio_monitor.volume * 100)
        vol_bar = self._format_volume_bar(width=min(20, width - 30))
        vol_line = f"  Volume:  {vol_bar} {vol_pct}%   (+/- to adjust)"
        stdscr.addstr(row, 0, vol_line[: width - 1])
        row += 2

        # Transcription log header
        if row < height - 2:
            header = "  --- Transcription Log ---"
            stdscr.addstr(row, 0, header[: width - 1])
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
                stdscr.addstr(row, 0, line[: width - 1])
                row += 1

        # Footer
        footer_row = height - 1
        footer = "  q quit | +/- vol | s/S squelch | g/G gain | p/P ppm"
        try:
            stdscr.addstr(footer_row, 0, footer[: width - 1])
        except curses.error:
            pass  # Terminal too small

        stdscr.refresh()
```

**Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_monitor_ui.py -v --tb=short`
Expected: All pass

---

### Task 5: Wire new params through session.py

**Files:**
- Modify: `src/vtms_sdr/session.py:107-143` (`_run_with_monitor`)
- Test: `tests/test_session.py`

**Step 1: Write the failing test**

Add to `tests/test_session.py`:

```python
class TestSessionMonitorUIWiring:
    """Test that _run_with_monitor passes new params to MonitorUI."""

    @patch("vtms_sdr.session.MonitorUI")  # or wherever the import lands
    def test_passes_sdr_device_and_recorder(self, MockMonitorUI):
        """_run_with_monitor should pass sdr_device, recorder, model_size, gain, ppm."""
        # This test verifies the MonitorUI constructor is called with the new kwargs.
        # Implementation will need to check the actual import path.
        pass  # Placeholder — actual test depends on session.py import structure
```

**NOTE:** This task is a thin wiring change. The session already has `cfg.gain` and `cfg.ppm` on RecordConfig. We need to:

1. Pass `sdr_device=sdr` (the SDRDevice instance from `run()`) to `_run_with_monitor`
2. Pass `recorder` reference to MonitorUI
3. Pass `gain=cfg.gain`, `ppm=cfg.ppm` to MonitorUI
4. If transcriber exists and has a `model_size` attr, pass `model_size`

Modify `session.py:56-88` (`run()`) to pass `sdr` to `_run_with_monitor`:

```python
    if cfg.monitor:
        stats = self._run_with_monitor(cfg, audio_stream, sdr)
    else:
        stats = self._run_headless(cfg, audio_stream)
```

Modify `_run_with_monitor` signature and MonitorUI construction:

```python
    def _run_with_monitor(self, cfg: RecordConfig, audio_stream, sdr_device=None) -> dict:
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
                squelch_callback=None,  # will be set after MonitorUI
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
```

**Step 2: Run full test suite**

Run: `source .venv/bin/activate && python -m pytest tests/ -v --tb=short`
Expected: All pass

---

### Task 6: Integration test for session wiring

**Files:**
- Test: `tests/test_session.py`

**Step 1: Write integration test**

```python
class TestSessionMonitorUIWiring:
    """Test that _run_with_monitor passes new params to MonitorUI."""

    @patch("vtms_sdr.session.AudioRecorder")
    @patch("vtms_sdr.session.MonitorUI")
    def test_passes_new_params_to_monitor_ui(self, MockMonitorUI, MockRecorder):
        """MonitorUI receives model_size, gain, ppm, sdr_device, recorder."""
        from vtms_sdr.session import RecordingSession, RecordConfig

        mock_transcriber = MagicMock()
        mock_transcriber.model_size = "medium"
        mock_monitor = MagicMock()
        mock_sdr = MagicMock()

        mock_ui_instance = MockMonitorUI.return_value
        mock_ui_instance.launch.return_value = {"audio_duration_sec": 1.0}

        cfg = RecordConfig(
            freq=146520000, mod="fm", output_path=Path("/tmp/test.wav"),
            audio_format="wav", gain=20.0, ppm=5,
            squelch_db=-30.0, transcriber=mock_transcriber,
            monitor=mock_monitor,
        )

        session = RecordingSession(cfg)
        session._run_with_monitor(cfg, lambda: iter([]), mock_sdr)

        call_kwargs = MockMonitorUI.call_args[1]
        assert call_kwargs.get("model_size") == "medium" or MockMonitorUI.call_args[1].get("model_size") == "medium"
        assert call_kwargs.get("gain") == 20.0
        assert call_kwargs.get("ppm") == 5
        assert call_kwargs.get("sdr_device") is mock_sdr
```

**Step 2: Run to verify**

Run: `source .venv/bin/activate && python -m pytest tests/test_session.py::TestSessionMonitorUIWiring -v`
Expected: PASS

**Step 3: Final full suite**

Run: `source .venv/bin/activate && python -m pytest tests/ -v --tb=short`
Expected: All pass (353 baseline + ~30 new tests)
