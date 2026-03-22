# Web UI Design for vtms-sdr

**Date:** 2026-03-18
**Status:** Approved

## Goal

Add a Web UI that complements the existing curses-based TUI, providing full
monitor + control parity accessible from a browser. Both interfaces can run
simultaneously against the same SDR session.

## Technology Stack

- **Backend:** FastAPI + uvicorn (WebSocket support)
- **Frontend:** Svelte + Vite (compiled to static files served by FastAPI)
- **Transport:** WebSockets for real-time state updates and control commands
- **Audio:** Raw PCM over WebSocket binary frames, Web Audio API playback

## Architecture

```
SDR Hardware
    |
    v
RecordingSession (existing)
    |
    +---> StateManager (new shared event/state bus)
    |         +---> MonitorUI (existing TUI)
    |         +---> WebBridge (new) ---> FastAPI WebSocket ---> Svelte SPA
    |
    +---> Recorder (existing)
    +---> Transcriber (existing)
```

### StateManager (`src/vtms_sdr/state.py`)

Thread-safe shared state bus decoupling producers from consumers.

- `update(key, value)` -- session publishes state changes
- `subscribe(callback)` -- consumers register for change notifications
- `snapshot()` -- returns current state as dict (initial WebSocket sync)
- `dispatch_control(action, value)` -- control commands flow back to session

Observable state keys: `signal_power`, `squelch_open`, `squelch_threshold`,
`frequency`, `modulation`, `gain`, `ppm`, `volume`, `elapsed`, `audio_captured`,
`output_path`, `transcription_lines`, `autotune_status`, `recording_active`.

### FastAPI Backend (`src/vtms_sdr/web/`)

**server.py:**
- `GET /` -- serves built Svelte SPA (static files)
- `WS /ws` -- primary WebSocket: pushes state events, receives control commands
- `WS /ws/audio` -- binary WebSocket for PCM audio streaming

**bridge.py:**
- Subscribes to StateManager, broadcasts to connected WebSocket clients
- Routes browser control commands to `StateManager.dispatch_control()`

### Svelte Frontend (`frontend/`)

Single-page dashboard mirroring the TUI:

| Area | Content |
|------|---------|
| Header | Frequency, modulation, recording status |
| Signal meter | Real-time power bar with squelch threshold |
| Stats | Elapsed time, audio captured, output file |
| Controls | Squelch, gain, PPM, volume sliders |
| Actions | Auto-tune button |
| Transcription | Scrolling log |
| Footer | Connection status |

Key components: `SignalMeter.svelte`, `Controls.svelte`,
`TranscriptionLog.svelte`, `AudioPlayer.svelte`, `ConnectionStatus.svelte`

### Audio Streaming

1. Demodulated audio (float32 @ 48kHz) queued for web clients
2. Raw PCM sent as binary WebSocket frames (~192 KB/s mono)
3. Browser decodes via AudioContext + AudioWorklet
4. Volume control applied client-side via GainNode
5. Future: Opus encoding for remote/low-bandwidth use

## CLI Integration

- `--web` flag on `record` command (alongside existing `--monitor`)
- `--web-port PORT` (default 8080)
- `--monitor --web` both usable together

## Project Structure

```
vtms-sdr/
├── src/vtms_sdr/
│   ├── state.py          # StateManager
│   ├── web/
│   │   ├── __init__.py
│   │   ├── server.py     # FastAPI app
│   │   ├── bridge.py     # WebSocket bridge
│   │   └── static/       # Built Svelte output
│   ├── monitor.py        # Modified: reads from StateManager
│   ├── session.py        # Modified: publishes to StateManager
│   └── ...
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.svelte
│       └── lib/
└── pyproject.toml        # New 'web' dependency group
```

## Dependencies

**Python (new `web` optional group):**
- fastapi, uvicorn[standard], websockets

**Node.js (build only):**
- svelte, vite, @sveltejs/vite-plugin-svelte

## Refactoring Scope

1. `session.py` -- publish to StateManager instead of setting MonitorUI attrs directly
2. `monitor.py` -- subscribe to StateManager for display state
3. `recorder.py` -- feed web audio queue when web mode active
4. Core SDR/demod/record/transcribe pipeline untouched
