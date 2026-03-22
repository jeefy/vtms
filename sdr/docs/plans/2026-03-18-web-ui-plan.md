# Web UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Svelte + FastAPI Web UI that complements the existing curses TUI, providing full monitor + control parity accessible from a browser, with live audio streaming.

**Architecture:** A shared `StateManager` event bus decouples the recording session from its consumers (TUI and Web UI). FastAPI serves a WebSocket API and the built Svelte SPA. Both interfaces can run simultaneously.

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, WebSockets, Svelte 5, Vite, Web Audio API

**Design doc:** `docs/plans/2026-03-18-web-ui-design.md`

---

### Task 1: StateManager — Shared State Bus

**Files:**
- Create: `src/vtms_sdr/state.py`
- Test: `tests/test_state.py`

The StateManager is the foundation everything else builds on. It's a thread-safe
observable state container that decouples producers (session/recorder) from
consumers (TUI, Web UI).

**Step 1: Write the failing tests**

Create `tests/test_state.py`:

```python
"""Tests for state.py: StateManager shared state bus."""

from __future__ import annotations

import threading
import time

import pytest


class TestStateManagerInit:
    """Test StateManager construction."""

    def test_can_import(self):
        from vtms_sdr.state import StateManager

    def test_initial_snapshot_has_all_keys(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        snap = sm.snapshot()
        expected_keys = {
            "signal_power", "squelch_open", "squelch_threshold",
            "frequency", "modulation", "gain", "ppm", "volume",
            "elapsed", "audio_duration", "output_path",
            "transcription_lines", "autotune_status", "recording_active",
        }
        assert set(snap.keys()) == expected_keys

    def test_initial_values_are_defaults(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        snap = sm.snapshot()
        assert snap["signal_power"] == -100.0
        assert snap["squelch_open"] is False
        assert snap["recording_active"] is False
        assert snap["transcription_lines"] == []


class TestStateManagerUpdate:
    """Test state updates and subscriptions."""

    def test_update_changes_snapshot(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        sm.update("signal_power", -42.0)
        assert sm.snapshot()["signal_power"] == -42.0

    def test_update_unknown_key_raises(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        with pytest.raises(KeyError):
            sm.update("nonexistent_key", 42)

    def test_subscribe_receives_updates(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        received = []
        sm.subscribe(lambda key, value: received.append((key, value)))
        sm.update("signal_power", -42.0)
        assert received == [("signal_power", -42.0)]

    def test_multiple_subscribers(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        r1, r2 = [], []
        sm.subscribe(lambda k, v: r1.append((k, v)))
        sm.subscribe(lambda k, v: r2.append((k, v)))
        sm.update("frequency", 146520000)
        assert r1 == [("frequency", 146520000)]
        assert r2 == [("frequency", 146520000)]

    def test_unsubscribe(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        received = []
        cb = lambda k, v: received.append((k, v))
        sm.subscribe(cb)
        sm.update("volume", 0.5)
        sm.unsubscribe(cb)
        sm.update("volume", 0.8)
        assert len(received) == 1

    def test_snapshot_returns_copy(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        snap1 = sm.snapshot()
        snap1["signal_power"] = 999
        assert sm.snapshot()["signal_power"] == -100.0

    def test_transcription_lines_appended(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        sm.add_transcription("12:00:00", "PIT", "Box this lap")
        snap = sm.snapshot()
        assert len(snap["transcription_lines"]) == 1
        assert snap["transcription_lines"][0] == ("12:00:00", "PIT", "Box this lap")

    def test_transcription_lines_trimmed(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        for i in range(150):
            sm.add_transcription(f"{i}", "", f"line {i}")
        snap = sm.snapshot()
        assert len(snap["transcription_lines"]) == 100


class TestStateManagerControls:
    """Test control dispatch."""

    def test_dispatch_control(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        received = []
        sm.on_control(lambda action, value: received.append((action, value)))
        sm.dispatch_control("set_squelch", -25.0)
        assert received == [("set_squelch", -25.0)]


class TestStateManagerThreadSafety:
    """Test thread safety of StateManager."""

    def test_concurrent_updates(self):
        from vtms_sdr.state import StateManager

        sm = StateManager()
        errors = []

        def updater(key, values):
            try:
                for v in values:
                    sm.update(key, v)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=updater, args=("signal_power", range(100)))
        t2 = threading.Thread(target=updater, args=("volume", [x/100 for x in range(100)]))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert errors == []
        # Final state should be deterministic
        snap = sm.snapshot()
        assert snap["signal_power"] == 99
        assert snap["volume"] == 0.99
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtms_sdr.state'`

**Step 3: Implement StateManager**

Create `src/vtms_sdr/state.py`:

```python
"""Shared state bus for vtms-sdr.

Thread-safe observable state container that decouples data producers
(RecordingSession, Recorder) from consumers (TUI, Web UI).
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable
from typing import Any

__all__ = ["StateManager"]

MAX_TRANSCRIPTION_LINES = 100


class StateManager:
    """Thread-safe shared state bus.

    Producers call update() to change state values.
    Consumers call subscribe() to receive change notifications.
    Control commands flow back via dispatch_control().
    """

    _DEFAULTS: dict[str, Any] = {
        "signal_power": -100.0,
        "squelch_open": False,
        "squelch_threshold": -30.0,
        "frequency": 0,
        "modulation": "fm",
        "gain": "auto",
        "ppm": 0,
        "volume": 0.5,
        "elapsed": 0.0,
        "audio_duration": 0.0,
        "output_path": "",
        "transcription_lines": [],
        "autotune_status": None,
        "recording_active": False,
    }

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] = copy.deepcopy(self._DEFAULTS)
        self._subscribers: list[Callable[[str, Any], None]] = []
        self._control_handlers: list[Callable[[str, Any], None]] = []

    def update(self, key: str, value: Any) -> None:
        """Update a state value and notify subscribers.

        Args:
            key: State key (must be a known key).
            value: New value for the key.

        Raises:
            KeyError: If key is not a known state key.
        """
        with self._lock:
            if key not in self._state:
                raise KeyError(f"Unknown state key: {key!r}")
            self._state[key] = value
            subscribers = list(self._subscribers)
        for cb in subscribers:
            cb(key, value)

    def add_transcription(self, timestamp: str, label: str, text: str) -> None:
        """Append a transcription line and notify subscribers.

        Trims to MAX_TRANSCRIPTION_LINES.
        """
        with self._lock:
            lines = self._state["transcription_lines"]
            lines.append((timestamp, label, text))
            if len(lines) > MAX_TRANSCRIPTION_LINES:
                self._state["transcription_lines"] = lines[-MAX_TRANSCRIPTION_LINES:]
            new_lines = list(self._state["transcription_lines"])
            subscribers = list(self._subscribers)
        for cb in subscribers:
            cb("transcription_lines", new_lines)

    def snapshot(self) -> dict[str, Any]:
        """Return a deep copy of the current state."""
        with self._lock:
            return copy.deepcopy(self._state)

    def subscribe(self, callback: Callable[[str, Any], None]) -> None:
        """Register a callback for state change notifications.

        Callback receives (key, value) on each update.
        """
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[str, Any], None]) -> None:
        """Remove a previously registered callback."""
        with self._lock:
            self._subscribers.remove(callback)

    def on_control(self, handler: Callable[[str, Any], None]) -> None:
        """Register a handler for control commands from consumers."""
        with self._lock:
            self._control_handlers.append(handler)

    def dispatch_control(self, action: str, value: Any) -> None:
        """Dispatch a control command to registered handlers."""
        with self._lock:
            handlers = list(self._control_handlers)
        for handler in handlers:
            handler(action, value)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_state.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/vtms_sdr/state.py tests/test_state.py
git commit -m "feat: add StateManager shared state bus

Thread-safe observable state container that decouples data producers
(session/recorder) from consumers (TUI, Web UI)."
```

---

### Task 2: Refactor MonitorUI to Use StateManager

**Files:**
- Modify: `src/vtms_sdr/monitor.py:146-580`
- Modify: `src/vtms_sdr/session.py:113-210`
- Modify: `tests/test_monitor_ui.py` (update tests for new constructor)
- Modify: `tests/test_session.py` (update tests for StateManager)

MonitorUI currently stores state directly as attributes that the session sets.
Refactor it to optionally accept a `StateManager` and subscribe to it. Keep
backward compatibility so existing tests don't break unnecessarily.

**Step 1: Add `state_manager` parameter to MonitorUI.__init__**

In `src/vtms_sdr/monitor.py:175-212`, add an optional `state_manager` parameter:

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
    state_manager: StateManager | None = None,
) -> None:
```

Store it as `self._state_manager = state_manager`.

**Step 2: Wire MonitorUI.update_progress to also update StateManager**

In the `update_progress` method (line 214), after updating `self._state`, also
call `self._state_manager.update("elapsed", elapsed)` and
`self._state_manager.update("audio_duration", audio_duration)` if state_manager
is not None.

Do the same for `update_squelch` → updates `signal_power` and `squelch_open`.
Do the same for `add_transcription` → calls `state_manager.add_transcription()`.
Do the same for `set_autotune_status` → updates `autotune_status`.

**Step 3: Wire _handle_key to dispatch controls via StateManager**

In `_handle_key` (line 275), after making local changes (e.g., setting
`self.squelch_db`), also call:
```python
if self._state_manager is not None:
    self._state_manager.dispatch_control("set_squelch", self.squelch_db)
```

Apply the same pattern for volume, gain, ppm, and autotune controls.

**Step 4: Update session.py to create StateManager and pass it**

In `_run_with_monitor` (line 113), create a StateManager instance, initialize it
with the config values, and pass it to MonitorUI:

```python
from .state import StateManager

state_manager = StateManager()
state_manager.update("frequency", cfg.freq)
state_manager.update("modulation", cfg.mod)
state_manager.update("squelch_threshold", cfg.squelch_db)
state_manager.update("output_path", str(cfg.output_path))
state_manager.update("gain", cfg.gain)
state_manager.update("ppm", cfg.ppm)
state_manager.update("volume", cfg.volume)
state_manager.update("recording_active", True)
```

Pass `state_manager=state_manager` to MonitorUI constructor.

Store `self._state_manager = state_manager` on the session for the web server to
access later (Task 6).

**Step 5: Update existing tests**

Most existing tests use MagicMock for MonitorUI, so they should still pass.
Add new tests verifying StateManager integration:
- MonitorUI.update_progress publishes to StateManager
- MonitorUI.update_squelch publishes to StateManager
- MonitorUI.add_transcription publishes to StateManager
- _handle_key dispatches controls to StateManager

**Step 6: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add src/vtms_sdr/monitor.py src/vtms_sdr/session.py tests/
git commit -m "feat: wire StateManager into MonitorUI and session

MonitorUI now accepts an optional StateManager and publishes state
updates to it. Session creates and initializes the StateManager."
```

---

### Task 3: FastAPI Web Server + WebSocket Bridge

**Files:**
- Create: `src/vtms_sdr/web/__init__.py`
- Create: `src/vtms_sdr/web/server.py`
- Create: `src/vtms_sdr/web/bridge.py`
- Test: `tests/test_web_server.py`
- Test: `tests/test_web_bridge.py`
- Modify: `pyproject.toml` (add `web` dependency group)

**Step 1: Add `web` dependency group to pyproject.toml**

In `pyproject.toml`, after the `monitor` group (line 28), add:

```toml
web = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "websockets>=12.0",
]
```

Also add `"web"` to the `default-groups` list in `[tool.uv]` (line 42).

Run: `uv sync`

**Step 2: Write failing tests for WebBridge**

Create `tests/test_web_bridge.py`:

```python
"""Tests for web/bridge.py: WebSocket bridge between StateManager and clients."""

from __future__ import annotations

import asyncio
import json

import pytest


class TestWebBridge:
    def test_can_import(self):
        from vtms_sdr.web.bridge import WebBridge

    def test_state_update_queued_for_clients(self):
        from vtms_sdr.state import StateManager
        from vtms_sdr.web.bridge import WebBridge

        sm = StateManager()
        bridge = WebBridge(sm)
        # Add a mock client queue
        client_queue = asyncio.Queue()
        bridge.add_client(client_queue)
        # Trigger an update
        sm.update("signal_power", -42.0)
        # Check the queue has the update
        msg = client_queue.get_nowait()
        parsed = json.loads(msg)
        assert parsed["type"] == "state"
        assert parsed["key"] == "signal_power"
        assert parsed["value"] == -42.0

    def test_remove_client(self):
        from vtms_sdr.state import StateManager
        from vtms_sdr.web.bridge import WebBridge

        sm = StateManager()
        bridge = WebBridge(sm)
        client_queue = asyncio.Queue()
        bridge.add_client(client_queue)
        bridge.remove_client(client_queue)
        sm.update("signal_power", -42.0)
        assert client_queue.empty()

    def test_control_message_dispatched(self):
        from vtms_sdr.state import StateManager
        from vtms_sdr.web.bridge import WebBridge

        sm = StateManager()
        bridge = WebBridge(sm)
        received = []
        sm.on_control(lambda a, v: received.append((a, v)))
        bridge.handle_control('{"action": "set_squelch", "value": -25.0}')
        assert received == [("set_squelch", -25.0)]
```

**Step 3: Implement WebBridge**

Create `src/vtms_sdr/web/__init__.py` (empty) and `src/vtms_sdr/web/bridge.py`:

```python
"""WebSocket bridge between StateManager and browser clients."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from ..state import StateManager

logger = logging.getLogger(__name__)

__all__ = ["WebBridge"]


class WebBridge:
    """Bridges StateManager updates to WebSocket client queues.

    Subscribes to StateManager and enqueues JSON messages for each
    connected WebSocket client. Also routes control commands from
    clients back to the StateManager.
    """

    def __init__(self, state_manager: StateManager) -> None:
        self._state_manager = state_manager
        self._clients: list[asyncio.Queue] = []
        self._lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None
        state_manager.subscribe(self._on_state_update)

    def add_client(self, queue: asyncio.Queue) -> None:
        self._clients.append(queue)

    def remove_client(self, queue: asyncio.Queue) -> None:
        if queue in self._clients:
            self._clients.remove(queue)

    def _on_state_update(self, key: str, value: Any) -> None:
        msg = json.dumps({"type": "state", "key": key, "value": value})
        dead = []
        for q in self._clients:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.remove_client(q)

    def handle_control(self, raw_message: str) -> None:
        data = json.loads(raw_message)
        action = data.get("action", "")
        value = data.get("value")
        self._state_manager.dispatch_control(action, value)
```

**Step 4: Write failing tests for FastAPI server**

Create `tests/test_web_server.py`:

```python
"""Tests for web/server.py: FastAPI application."""

from __future__ import annotations

import pytest


class TestWebApp:
    def test_can_import(self):
        from vtms_sdr.web.server import create_app

    def test_create_app_returns_fastapi(self):
        from vtms_sdr.state import StateManager
        from vtms_sdr.web.server import create_app
        from fastapi import FastAPI

        sm = StateManager()
        app = create_app(sm)
        assert isinstance(app, FastAPI)
```

Use httpx + pytest-asyncio for deeper WebSocket tests if desired, but start
with import and smoke tests.

**Step 5: Implement FastAPI server**

Create `src/vtms_sdr/web/server.py`:

```python
"""FastAPI web server for vtms-sdr Web UI."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from ..state import StateManager
from .bridge import WebBridge

logger = logging.getLogger(__name__)

__all__ = ["create_app", "start_server"]

STATIC_DIR = Path(__file__).parent / "static"


def create_app(state_manager: StateManager) -> FastAPI:
    """Create the FastAPI application.

    Args:
        state_manager: The shared state bus to bridge to WebSocket clients.
    """
    app = FastAPI(title="vtms-sdr Web UI")
    bridge = WebBridge(state_manager)
    app.state.bridge = bridge
    app.state.state_manager = state_manager

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        client_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        bridge.add_client(client_queue)

        # Send initial state snapshot
        snapshot = state_manager.snapshot()
        await ws.send_json({"type": "snapshot", "data": snapshot})

        try:
            # Run send and receive concurrently
            send_task = asyncio.create_task(_send_loop(ws, client_queue))
            recv_task = asyncio.create_task(_recv_loop(ws, bridge))
            done, pending = await asyncio.wait(
                {send_task, recv_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
        except WebSocketDisconnect:
            pass
        finally:
            bridge.remove_client(client_queue)

    @app.websocket("/ws/audio")
    async def audio_websocket(ws: WebSocket):
        await ws.accept()
        audio_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        # Register with bridge for audio frames
        if hasattr(bridge, "add_audio_client"):
            bridge.add_audio_client(audio_queue)
        try:
            while True:
                data = await audio_queue.get()
                await ws.send_bytes(data)
        except WebSocketDisconnect:
            pass
        finally:
            if hasattr(bridge, "remove_audio_client"):
                bridge.remove_audio_client(audio_queue)

    # Serve static files (built Svelte app) if directory exists
    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


async def _send_loop(ws: WebSocket, queue: asyncio.Queue):
    """Send queued state updates to the WebSocket client."""
    while True:
        msg = await queue.get()
        await ws.send_text(msg)


async def _recv_loop(ws: WebSocket, bridge: WebBridge):
    """Receive control messages from the WebSocket client."""
    while True:
        data = await ws.receive_text()
        bridge.handle_control(data)


def start_server(state_manager: StateManager, host: str = "0.0.0.0", port: int = 8080):
    """Start the web server in a background thread."""
    import threading
    import uvicorn

    app = create_app(state_manager)

    def run():
        uvicorn.run(app, host=host, port=port, log_level="warning")

    thread = threading.Thread(target=run, daemon=True, name="web-server")
    thread.start()
    logger.info("Web UI available at http://%s:%d", host, port)
    return thread
```

**Step 6: Run tests**

Run: `uv run pytest tests/test_web_bridge.py tests/test_web_server.py -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add src/vtms_sdr/web/ tests/test_web_bridge.py tests/test_web_server.py pyproject.toml
git commit -m "feat: add FastAPI web server and WebSocket bridge

WebBridge connects StateManager to WebSocket clients. FastAPI app
serves the WebSocket API and static files."
```

---

### Task 4: CLI Integration — `--web` and `--web-port` Flags

**Files:**
- Modify: `src/vtms_sdr/cli.py:69-216` (add options to record command)
- Modify: `src/vtms_sdr/session.py:56-98` (start web server when configured)
- Modify: `src/vtms_sdr/session.py:30-47` (add web fields to RecordConfig)
- Test: `tests/test_cli.py` (add tests for new options)
- Test: `tests/test_session.py` (add tests for web server startup)

**Step 1: Add `web` and `web_port` to RecordConfig**

In `src/vtms_sdr/session.py:30-47`, add:
```python
web: bool = False
web_port: int = 8080
```

**Step 2: Add CLI options**

In `src/vtms_sdr/cli.py`, after the `--volume` option (line 182), add:

```python
@click.option(
    "--web",
    is_flag=True,
    default=False,
    help="Enable Web UI for remote monitoring and control.",
)
@click.option(
    "--web-port",
    type=int,
    default=8080,
    show_default=True,
    help="Port for the Web UI server. Requires --web.",
)
```

Add `web` and `web_port` to the `record` function parameters.

Pass `web=web, web_port=web_port` to `RecordConfig`.

**Step 3: Start web server in session.py**

In `RecordingSession.run()` (line 59), after SDR configuration, check
`cfg.web` and start the web server:

```python
if cfg.web:
    from .state import StateManager
    from .web.server import start_server

    self._state_manager = StateManager()
    self._state_manager.update("frequency", cfg.freq)
    self._state_manager.update("modulation", cfg.mod)
    self._state_manager.update("squelch_threshold", cfg.squelch_db)
    self._state_manager.update("output_path", str(cfg.output_path))
    self._state_manager.update("gain", cfg.gain)
    self._state_manager.update("ppm", cfg.ppm)
    self._state_manager.update("volume", cfg.volume)
    self._state_manager.update("recording_active", True)
    start_server(self._state_manager, port=cfg.web_port)
```

When running with `--monitor`, pass the StateManager to MonitorUI (from Task 2).

When running headless with `--web` only (no `--monitor`), the session needs to
publish state updates to the StateManager directly from the recorder callbacks.
Add a `_web_progress_callback` and `_web_squelch_callback` that update the
StateManager.

**Step 4: Wire audio streaming to web clients**

In the recorder's audio path (where `audio_monitor.feed()` is called), also
feed audio to the WebBridge's audio queue. Add an `add_audio_client` /
`remove_audio_client` / `feed_audio` method to WebBridge that converts
float32 numpy arrays to bytes and enqueues them.

**Step 5: Update tests**

Add tests in `tests/test_session.py`:
- RecordConfig accepts web=True, web_port=9090
- When web=True, session starts the web server (mock start_server)

Add tests in `tests/test_cli.py`:
- `--web` flag is accepted
- `--web-port` flag is accepted

**Step 6: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add src/vtms_sdr/cli.py src/vtms_sdr/session.py tests/
git commit -m "feat: add --web and --web-port CLI flags

Starts a FastAPI web server in a background thread when --web is used.
Works alongside --monitor or standalone."
```

---

### Task 5: Svelte Frontend — Project Scaffolding

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/svelte.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.js`
- Create: `frontend/src/App.svelte`
- Create: `frontend/src/app.css`

**Step 1: Initialize the Svelte project**

In the `frontend/` directory, create a minimal Svelte 5 + Vite project.

`frontend/package.json`:
```json
{
  "name": "vtms-sdr-web",
  "private": true,
  "version": "0.0.1",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "devDependencies": {
    "@sveltejs/vite-plugin-svelte": "^4.0.0",
    "svelte": "^5.0.0",
    "vite": "^6.0.0"
  }
}
```

`frontend/vite.config.js`:
```javascript
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  build: {
    outDir: '../src/vtms_sdr/web/static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/ws': {
        target: 'ws://localhost:8080',
        ws: true,
      },
    },
  },
});
```

`frontend/svelte.config.js`:
```javascript
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

export default {
  preprocess: vitePreprocess(),
};
```

`frontend/index.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>vtms-sdr Web UI</title>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.js"></script>
</body>
</html>
```

`frontend/src/main.js`:
```javascript
import App from './App.svelte';
import './app.css';

const app = new App({ target: document.getElementById('app') });
export default app;
```

`frontend/src/App.svelte` — placeholder:
```svelte
<script>
  let status = $state('Connecting...');
</script>

<main>
  <h1>vtms-sdr Web UI</h1>
  <p>{status}</p>
</main>
```

`frontend/src/app.css`:
```css
:root {
  --bg: #1a1a2e;
  --fg: #e0e0e0;
  --accent: #00d4ff;
  --danger: #ff4444;
  --success: #44ff44;
  --warning: #ffaa00;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  background: var(--bg);
  color: var(--fg);
  min-height: 100vh;
}
```

**Step 2: Install dependencies and verify build**

```bash
cd frontend && npm install && npm run build
```

Expected: Build succeeds, output in `src/vtms_sdr/web/static/`

**Step 3: Add static dir to .gitignore**

Add `src/vtms_sdr/web/static/` to `.gitignore` — these are build artifacts.
Keep `frontend/` tracked in git.

**Step 4: Commit**

```bash
git add frontend/ .gitignore
git commit -m "feat: scaffold Svelte frontend project

Minimal Svelte 5 + Vite setup. Build output goes to web/static/
for FastAPI to serve."
```

---

### Task 6: Svelte WebSocket Client + State Store

**Files:**
- Create: `frontend/src/lib/websocket.js`
- Create: `frontend/src/lib/stores.js`
- Modify: `frontend/src/App.svelte`

**Step 1: Create WebSocket client**

`frontend/src/lib/websocket.js`:
```javascript
/**
 * WebSocket client for vtms-sdr.
 * Connects to the backend, handles reconnection, and dispatches messages.
 */

export function createWebSocket(url, { onSnapshot, onStateUpdate, onDisconnect, onConnect }) {
  let ws = null;
  let reconnectTimer = null;

  function connect() {
    ws = new WebSocket(url);

    ws.onopen = () => {
      if (onConnect) onConnect();
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'snapshot' && onSnapshot) {
        onSnapshot(msg.data);
      } else if (msg.type === 'state' && onStateUpdate) {
        onStateUpdate(msg.key, msg.value);
      }
    };

    ws.onclose = () => {
      if (onDisconnect) onDisconnect();
      reconnectTimer = setTimeout(connect, 2000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  function sendControl(action, value) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ action, value }));
    }
  }

  function close() {
    clearTimeout(reconnectTimer);
    if (ws) ws.close();
  }

  connect();

  return { sendControl, close };
}
```

**Step 2: Create reactive state store**

`frontend/src/lib/stores.js`:
```javascript
/**
 * Svelte 5 reactive state store for SDR state.
 */

export function createSdrState() {
  let state = $state({
    signal_power: -100,
    squelch_open: false,
    squelch_threshold: -30,
    frequency: 0,
    modulation: 'fm',
    gain: 'auto',
    ppm: 0,
    volume: 0.5,
    elapsed: 0,
    audio_duration: 0,
    output_path: '',
    transcription_lines: [],
    autotune_status: null,
    recording_active: false,
    connected: false,
  });

  function applySnapshot(data) {
    Object.assign(state, data);
    state.connected = true;
  }

  function applyUpdate(key, value) {
    if (key in state) {
      state[key] = value;
    }
  }

  function setConnected(val) {
    state.connected = val;
  }

  return {
    get state() { return state; },
    applySnapshot,
    applyUpdate,
    setConnected,
  };
}
```

**Step 3: Wire up App.svelte**

Update `frontend/src/App.svelte` to connect the WebSocket client to the state
store and render basic status info. This verifies the full pipeline works
end-to-end before building individual components.

**Step 4: Build and test manually**

```bash
cd frontend && npm run build
```

Start a recording with `--web` and open http://localhost:8080 to verify the
WebSocket connection works and state flows through.

**Step 5: Commit**

```bash
git add frontend/src/
git commit -m "feat: add WebSocket client and reactive state store

Svelte WebSocket client with auto-reconnect. Reactive state store
syncs with backend StateManager."
```

---

### Task 7: Svelte Dashboard Components

**Files:**
- Create: `frontend/src/lib/components/SignalMeter.svelte`
- Create: `frontend/src/lib/components/Controls.svelte`
- Create: `frontend/src/lib/components/TranscriptionLog.svelte`
- Create: `frontend/src/lib/components/StatusBar.svelte`
- Create: `frontend/src/lib/components/ConnectionStatus.svelte`
- Modify: `frontend/src/App.svelte`

**Step 1: SignalMeter component**

Renders a horizontal signal power bar (like the TUI's power bar) with:
- Filled/empty segments proportional to signal_power in [-80, 0] range
- Color changes based on squelch_open (green=open, red=closed)
- Squelch threshold marker line
- Numeric power_db and squelch_db readout

Use a `<canvas>` or CSS-based bar. CSS is simpler and sufficient.

**Step 2: Controls component**

Renders sliders and buttons for:
- Volume slider (0.0-1.0) → sends `set_volume` control
- Squelch slider → sends `set_squelch` control
- Gain slider (0-50 dB, or "auto") → sends `set_gain` control
- PPM input → sends `set_ppm` control
- Auto-tune button → sends `autotune` control

Each control calls `sendControl(action, value)` on change.

**Step 3: TranscriptionLog component**

Renders the list of `transcription_lines` as a scrolling log:
- Auto-scrolls to bottom on new entries
- Shows timestamp, label (if present), and text
- Styled like the TUI's transcription area

**Step 4: StatusBar component**

Shows: frequency (formatted as MHz), modulation, elapsed time, audio captured,
output filename, recording status indicator.

**Step 5: ConnectionStatus component**

Small indicator showing WebSocket connection state (connected/disconnected).
Green dot when connected, red when disconnected with "Reconnecting..." text.

**Step 6: Assemble in App.svelte**

Layout the components in a dashboard grid matching the TUI's vertical layout:
1. StatusBar (header)
2. SignalMeter
3. Controls
4. TranscriptionLog
5. ConnectionStatus (footer)

**Step 7: Build and verify**

```bash
cd frontend && npm run build
```

**Step 8: Commit**

```bash
git add frontend/
git commit -m "feat: add Svelte dashboard components

SignalMeter, Controls, TranscriptionLog, StatusBar, and
ConnectionStatus components assembled into the main dashboard."
```

---

### Task 8: Audio Streaming

**Files:**
- Modify: `src/vtms_sdr/web/bridge.py` (add audio client management)
- Modify: `src/vtms_sdr/recorder.py:206-210` (feed audio to web bridge)
- Modify: `src/vtms_sdr/session.py` (wire audio feed to bridge)
- Create: `frontend/src/lib/audio.js` (Web Audio API playback)
- Create: `frontend/src/lib/components/AudioPlayer.svelte`
- Test: `tests/test_web_bridge.py` (add audio tests)

**Step 1: Add audio client management to WebBridge**

Add to `bridge.py`:

```python
def __init__(self, state_manager):
    ...
    self._audio_clients: list[asyncio.Queue] = []

def add_audio_client(self, queue: asyncio.Queue) -> None:
    self._audio_clients.append(queue)

def remove_audio_client(self, queue: asyncio.Queue) -> None:
    if queue in self._audio_clients:
        self._audio_clients.remove(queue)

def feed_audio(self, audio_block: np.ndarray) -> None:
    """Feed an audio block to all connected audio clients.

    Converts float32 numpy array to bytes for WebSocket binary frames.
    """
    audio_bytes = audio_block.astype(np.float32).tobytes()
    dead = []
    for q in self._audio_clients:
        try:
            q.put_nowait(audio_bytes)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        self.remove_audio_client(q)
```

**Step 2: Feed audio from recorder to bridge**

In `session.py`, when `cfg.web` is true, create a callback that feeds audio to
the bridge. In the recorder's audio path (after squelch check), if audio is
above squelch and the web bridge exists, call `bridge.feed_audio(audio_block)`.

This can be done by adding a second audio consumer alongside AudioMonitor. Add
a `web_audio_callback` to the recorder or extend the existing `audio_monitor.feed()`
call site in `recorder.py:209-210`.

**Step 3: Create Web Audio API player**

`frontend/src/lib/audio.js`:

```javascript
/**
 * Web Audio API player for PCM audio from WebSocket.
 *
 * Receives float32 PCM at 48kHz via WebSocket binary frames,
 * buffers them, and plays through AudioContext.
 */

export function createAudioPlayer() {
  let ctx = null;
  let gainNode = null;
  let ws = null;
  let playing = false;
  let nextStartTime = 0;

  function start(wsUrl) {
    ctx = new AudioContext({ sampleRate: 48000 });
    gainNode = ctx.createGain();
    gainNode.connect(ctx.destination);
    nextStartTime = ctx.currentTime;

    ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';

    ws.onmessage = (event) => {
      if (!playing) return;
      const float32 = new Float32Array(event.data);
      const buffer = ctx.createBuffer(1, float32.length, 48000);
      buffer.getChannelData(0).set(float32);

      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(gainNode);

      // Schedule playback to avoid gaps
      const now = ctx.currentTime;
      if (nextStartTime < now) nextStartTime = now;
      source.start(nextStartTime);
      nextStartTime += buffer.duration;
    };

    playing = true;
  }

  function stop() {
    playing = false;
    if (ws) ws.close();
    if (ctx) ctx.close();
  }

  function setVolume(vol) {
    if (gainNode) gainNode.gain.value = vol;
  }

  return { start, stop, setVolume };
}
```

**Step 4: Create AudioPlayer component**

`frontend/src/lib/components/AudioPlayer.svelte`:

Simple play/mute toggle button and a volume slider that controls the GainNode.
On play, connects to `ws://host/ws/audio`. On mute/stop, closes the connection.

**Step 5: Add tests for audio bridge**

In `tests/test_web_bridge.py`, add:
- `test_feed_audio_enqueues_bytes` — feed a numpy array, verify bytes in queue
- `test_feed_audio_drops_when_full` — fill queue, verify no crash

**Step 6: Run tests and build**

```bash
uv run pytest tests/test_web_bridge.py -v
cd frontend && npm run build
```

**Step 7: Commit**

```bash
git add src/vtms_sdr/web/bridge.py src/vtms_sdr/recorder.py \
        src/vtms_sdr/session.py frontend/src/lib/audio.js \
        frontend/src/lib/components/AudioPlayer.svelte \
        tests/test_web_bridge.py
git commit -m "feat: add live audio streaming to Web UI

PCM audio streamed over WebSocket binary frames. Browser plays
back via Web Audio API with volume control."
```

---

### Task 9: Control Command Handling

**Files:**
- Modify: `src/vtms_sdr/session.py` (handle control commands from StateManager)
- Modify: `src/vtms_sdr/web/bridge.py` (validate control messages)
- Test: `tests/test_session.py`

**Step 1: Register control handler in session**

When `cfg.web` is True, register a control handler on the StateManager that
applies the control action to the live session:

```python
def _handle_web_control(self, action: str, value) -> None:
    """Handle control commands from the Web UI."""
    if action == "set_squelch":
        self._recorder.squelch_db = float(value)
        self._state_manager.update("squelch_threshold", float(value))
    elif action == "set_volume" and self._audio_monitor:
        self._audio_monitor.volume = float(value)
        self._state_manager.update("volume", float(value))
    elif action == "set_gain" and self._sdr_device:
        self._sdr_device.set_gain(float(value))
        self._state_manager.update("gain", float(value))
    elif action == "set_ppm" and self._sdr_device:
        self._sdr_device.set_ppm(int(value))
        self._state_manager.update("ppm", int(value))
    elif action == "autotune":
        # Set flag for auto-tune (same as TUI 'a' key)
        if hasattr(self, '_monitor_ui') and self._monitor_ui:
            self._monitor_ui._autotune_requested = True
```

When `--web` is used with `--monitor`, both control paths (TUI keys and web
controls) should work. The TUI's `_handle_key` already updates the MonitorUI
state directly; the web control handler updates via StateManager, and both
write to the same recorder/sdr_device.

**Step 2: Add validation to bridge.handle_control**

Validate the `action` field against a known set:
`{"set_squelch", "set_volume", "set_gain", "set_ppm", "autotune"}`

Log and ignore unknown actions.

**Step 3: Add tests**

Test that the control handler correctly modifies the recorder's squelch,
the audio monitor's volume, etc. Use mocks for the SDR device and recorder.

**Step 4: Run tests**

Run: `uv run pytest -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/vtms_sdr/session.py src/vtms_sdr/web/bridge.py tests/
git commit -m "feat: handle Web UI control commands

Web UI controls (squelch, gain, volume, ppm, autotune) are routed
through StateManager to the live SDR session."
```

---

### Task 10: Integration Testing + Polish

**Files:**
- Modify: `frontend/src/App.svelte` (final layout polish)
- Modify: `frontend/src/app.css` (responsive design)
- Modify: `pyproject.toml` (update default-groups)
- Update: `.gitignore`

**Step 1: Manual integration test**

1. Start a recording with `--web --monitor`:
   ```bash
   vtms-sdr record -f 146.52M --monitor --web
   ```
2. Open http://localhost:8080 in a browser
3. Verify: signal meter updates, transcriptions appear, controls work
4. Verify: TUI and Web UI both reflect the same state
5. Verify: audio plays in the browser

**Step 2: Polish the frontend**

- Responsive layout for mobile (portrait mode for field use)
- Dark theme matching the terminal aesthetic
- Smooth transitions for signal meter updates
- Auto-scroll on transcription log

**Step 3: Update pyproject.toml**

Ensure the `web` dependency group is in `default-groups` if desired, or
document that users should install with `uv sync --group web`.

**Step 4: Final test suite run**

Run: `uv run pytest -v`
Expected: All PASS, no regressions

**Step 5: Build frontend for distribution**

```bash
cd frontend && npm run build
```

Verify `src/vtms_sdr/web/static/index.html` exists.

**Step 6: Commit**

```bash
git add -A
git commit -m "feat: polish Web UI and finalize integration

Responsive dashboard layout, dark theme, all controls working.
Full parity with TUI monitor."
```
