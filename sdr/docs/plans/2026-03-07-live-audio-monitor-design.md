# Feature 5: Live Audio Monitor with Curses TUI

## Summary

Add `--monitor` flag to the `record` command that enables real-time audio playback through speakers/headphones and a curses-based terminal UI showing recording status, squelch state, volume control, and live transcription output.

## Architecture

### New Module: `src/vtms_sdr/monitor.py`

Two classes:

**AudioMonitor** - Manages real-time audio playback via sounddevice.
- Opens a `sounddevice.OutputStream` (48kHz, mono, float32)
- Queue-based: `feed()` enqueues audio blocks, sounddevice callback dequeues and plays
- Volume property (0.0-1.0) applied as scalar multiplication in the callback
- If queue empty, callback writes silence (zeros)

**MonitorUI** - Curses-based terminal display.
- Runs curses in main thread (required by curses)
- Recording loop runs in a background thread
- Thread-safe update methods buffer state changes behind a lock
- Keyboard input: +/- for volume (5% steps), q to stop

### Changes to Existing Code

**recorder.py** - Add optional `audio_monitor` parameter to `AudioRecorder.__init__()`.
- After squelch check, if monitor is set, call `monitor.feed(audio_block)` for blocks above squelch.
- This is the same tap point as the transcriber.

**cli.py** - Add flags to `record` command:
- `--monitor` (bool): Enable live audio monitoring with curses UI
- `--volume` (float, 0.0-1.0, default 0.5): Initial monitor volume

### New Dependency

`sounddevice` as optional dependency in pyproject.toml under `[monitor]` extra.
Users install with `pip install vtms-sdr[monitor]`.

## TUI Layout

```
┌─ vtms-sdr Monitor ──────────────────────────────────┐
│  Frequency: 146.520 MHz   Modulation: FM            │
│  Recording: 00:05:23      File: recording_146...wav  │
│  Squelch: ████████░░░░ OPEN  (-32.1 dB / -40.0 dB) │
│  Volume:  ████████░░░░ 80%   (+/- to adjust)        │
│                                                       │
│  ─── Transcription Log ───                           │
│  [00:04:51] [Spotter] Box box, car 42 pit entry     │
│  [00:05:12] [Spotter] Clear, back on track          │
│                                                       │
│  Press q to stop · +/- volume · Ctrl+C to abort     │
└──────────────────────────────────────────────────────┘
```

## Threading Model

- Main thread: curses event loop (input + draw at ~10Hz)
- Background thread: SDR → demod → recorder → monitor.feed()
- sounddevice callback: runs in PortAudio's audio thread (pulls from queue)

## Data Flow

```
SDR → Demodulator → AudioRecorder
                        ├── WAV/MP3 file write
                        ├── Transcriber (squelch-gated)
                        └── AudioMonitor.feed() (squelch-gated)
                                └── Queue → sounddevice callback → speakers
```

## Error Handling

- If sounddevice/PortAudio unavailable: clear error message suggesting `pip install vtms-sdr[monitor]`
- If no audio output device: warn and continue recording without playback
- Queue overflow (slow consumer): drop oldest blocks to prevent memory growth

## Implementation Order (TDD)

1. AudioMonitor class (queue, feed, volume, start/stop)
2. AudioRecorder integration (audio_monitor parameter, feed calls)
3. MonitorUI class (curses display, key handling, thread-safe updates)
4. CLI integration (--monitor, --volume flags, wiring)
5. Integration tests
