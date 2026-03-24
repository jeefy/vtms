# Unified Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Consolidate all Web UIs into a single React dashboard on base-pi, integrating SDR monitoring alongside existing telemetry and GoPro controls, and fixing critical bugs from the code review.

**Architecture:** SDR publishes state to MQTT topics (`lemons/sdr/state/#`) and receives control commands via MQTT (`lemons/sdr/control/#`), eliminating the need for FastAPI/Svelte. Audio streams over a lightweight WebSocket. The existing React dashboard and Express server absorb all UI responsibilities.

**Tech Stack:** React 19 + TypeScript + Vite (existing), Express 5 (existing), Python MQTT integration for SDR, WebSocket for audio, Playwright for E2E tests.

---

## Phase 0: Critical Bug Fixes

### Task 0.1: Fix CORS Wildcard in Server

**Files:**
- Modify: `server/src/index.ts:22-28`

Replace wildcard CORS with origin allowlist:

```ts
const ALLOWED_ORIGINS = new Set([
  `http://localhost:${PORT}`,
  `http://localhost:5173`, // Vite dev
]);

app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (origin && ALLOWED_ORIGINS.has(origin)) {
    res.header("Access-Control-Allow-Origin", origin);
    res.header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS");
    res.header("Access-Control-Allow-Headers", "Content-Type");
  }
  if (req.method === "OPTIONS") {
    res.sendStatus(204);
    return;
  }
  next();
});
```

**Commit:** `fix(server): restrict CORS to known origins instead of wildcard`

---

### Task 0.2: Fix MQTT Client Cleanup Race Condition

**Files:**
- Modify: `web/src/hooks/useMqtt.ts:22-58`

Refactor to create client inside `useEffect` instead of a `useCallback`:

```ts
useEffect(() => {
  const client = mqtt.connect(brokerUrl, {
    reconnectPeriod: 5000,
    connectTimeout: 10_000,
  });
  clientRef.current = client;

  client.on("connect", () => {
    setConnected(true);
    client.subscribe(`${topicPrefix}#`);
  });

  client.on("close", () => setConnected(false));
  client.on("error", (err) => console.error("[mqtt]", err.message));
  client.on("message", (topic, payload) => {
    onMessage(topic, payload.toString());
  });

  return () => {
    client.end(true);
    clientRef.current = null;
    setConnected(false);
  };
}, [brokerUrl, topicPrefix]);
```

Remove the `connect` callback wrapper entirely.

**Verify:** `pnpm --filter web exec playwright test`

**Commit:** `fix(web): prevent MQTT client leak on rapid config changes`

---

### Task 0.3: Optimize Telemetry Re-renders

**Files:**
- Modify: `web/src/hooks/useTelemetry.ts:88-94, 123-127`
- Modify: `web/src/components/RadialGauge.tsx` (add `React.memo`)

1. Add `React.memo` to `RadialGauge` with custom comparator:

```tsx
export default React.memo(RadialGauge, (prev, next) => {
  return (
    prev.value === next.value &&
    prev.min === next.min &&
    prev.max === next.max &&
    prev.label === next.label
  );
});
```

2. Throttle trail state updates to every 5th GPS point (keep ref updated on every point):

```ts
trailRef.current = newTrail;
trailCountRef.current++;
if (trailCountRef.current % 5 === 0) {
  setTrail([...trailRef.current]);
}
```

**Verify:** `pnpm --filter web exec playwright test`

**Commit:** `perf(web): memoize RadialGauge and throttle GPS trail updates`

---

### Task 0.4: Fix RadialGauge Division by Zero

**Files:**
- Modify: `web/src/components/RadialGauge.tsx:29`

Guard against `min === max`:

```ts
const range = max - min;
const ratio = range === 0 ? 0 : Math.max(0, Math.min(1, (value - min) / range));
```

**Commit:** `fix(web): prevent NaN gauge rendering when min equals max`

---

### Task 0.5: Fix Server Process Management

**Files:**
- Modify: `server/src/stream-manager.ts` (SIGKILL fallback, reset running on failure, try/catch in reconnect)
- Modify: `server/src/index.ts` (global error handlers)

1. SIGKILL fallback in `stopStream`:

```ts
if (this.ffmpeg) {
  const proc = this.ffmpeg;
  this.ffmpeg = null;
  proc.kill("SIGTERM");
  setTimeout(() => {
    if (!proc.killed) {
      console.warn("[stream] FFmpeg did not exit, sending SIGKILL");
      proc.kill("SIGKILL");
    }
  }, 5000);
}
```

2. Reset `running` on failure in `startStream`:

```ts
async startStream(): Promise<void> {
  if (this.running) return;
  this.running = true;
  this.backoffMs = 1000;
  try {
    await this.requestGoProStream();
    this.spawnFfmpeg();
  } catch (err) {
    this.running = false;
    throw err;
  }
}
```

3. Try/catch in `scheduleReconnect`:

```ts
this.reconnectTimer = setTimeout(async () => {
  try {
    await this.requestGoProStream();
    this.spawnFfmpeg();
    this.backoffMs = Math.min(this.backoffMs * 2, 30_000);
  } catch (err) {
    console.error("[stream] Reconnect failed:", err);
    if (this.running) this.scheduleReconnect();
  }
}, this.backoffMs);
```

4. Global handlers in `index.ts`:

```ts
process.on("unhandledRejection", (reason) => {
  console.error("Unhandled rejection:", reason);
});

process.on("uncaughtException", (err) => {
  console.error("Uncaught exception:", err);
  keepAlive.stop();
  streamManager.destroy();
  process.exit(1);
});
```

**Commit:** `fix(server): harden process management and add global error handlers`

---

### Task 0.6: Fix Config Validation & Persistence

**Files:**
- Modify: `server/src/config-store.ts`

1. Validate config on load (not just save)
2. Clone defaults in `getDefaultConfig()` and fallback paths
3. Validate `zones[]` entries in `validateConfig`
4. Atomic writes (write to .tmp, rename)

```ts
import { rename } from "node:fs/promises";

export function getDefaultConfig(): AppConfig {
  return structuredClone(DEFAULT_CONFIG);
}

export async function loadConfig(): Promise<AppConfig> {
  try {
    const raw = await readFile(CONFIG_PATH, "utf-8");
    const parsed = JSON.parse(raw);
    validateConfig(parsed);
    return parsed;
  } catch {
    console.warn("Failed to load config, using defaults");
    return structuredClone(DEFAULT_CONFIG);
  }
}

export async function saveConfig(config: AppConfig): Promise<void> {
  validateConfig(config);
  await mkdir(CONFIG_DIR, { recursive: true });
  const tmpPath = CONFIG_PATH + ".tmp";
  await writeFile(tmpPath, JSON.stringify(config, null, 2), "utf-8");
  await rename(tmpPath, CONFIG_PATH);
}
```

Add zone validation inside `validateConfig`:

```ts
if (gauge.zones !== undefined) {
  if (!Array.isArray(gauge.zones)) throw new Error("gauge.zones must be an array");
  for (const z of gauge.zones) {
    if (typeof z !== "object" || z === null) throw new Error("zone must be an object");
    if (typeof z.from !== "number") throw new Error("zone.from must be a number");
    if (typeof z.to !== "number") throw new Error("zone.to must be a number");
    if (typeof z.color !== "string") throw new Error("zone.color must be a string");
  }
}
if (gauge.decimals !== undefined && typeof gauge.decimals !== "number") {
  throw new Error("gauge.decimals must be a number");
}
```

**Commit:** `fix(server): validate config on load, atomic writes, clone defaults`

---

### Task 0.7: Fix Docker Image

**Files:**
- Modify: `Dockerfile.web`

Add `ffmpeg` to runtime image and expose WS port:

```dockerfile
# After FROM node:22-alpine AS runtime
RUN apk add --no-cache ffmpeg
```

```dockerfile
EXPOSE 3001 9002
```

**Commit:** `fix(docker): install ffmpeg in runtime image and expose WS port`

---

### Task 0.8: Bundle Leaflet Assets for Offline Use

**Files:**
- Modify: `web/src/components/MapView.tsx:9-13`
- Create: `web/public/images/marker-icon.png` (copy from node_modules/leaflet)
- Create: `web/public/images/marker-icon-2x.png`
- Create: `web/public/images/marker-shadow.png`

Copy marker assets from leaflet package to `web/public/images/`, update icon URLs to local paths:

```tsx
const markerIcon = new L.Icon({
  iconUrl: "/images/marker-icon.png",
  iconRetinaUrl: "/images/marker-icon-2x.png",
  shadowUrl: "/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});
```

**Commit:** `fix(web): bundle Leaflet marker icons locally for offline use`

---

### Task 0.9: Fix SettingsPanel Error Handling

**Files:**
- Modify: `web/src/components/SettingsPanel.tsx`

1. Wrap `handleSave` and `handleReset` in try/catch/finally
2. Type field parameters as `keyof MqttConfig` / `keyof GoProConfig`

**Commit:** `fix(web): add error handling to settings save/reset and type field params`

---

## Phase 1: SDR MQTT Integration

### Task 1.1: Create SDR StateManager

**Files:**
- Create: `sdr/src/vtms_sdr/state.py`
- Test: `sdr/tests/test_state.py`

Thread-safe shared state bus:
- `update(key, value)` — session publishes state changes
- `subscribe(callback)` — consumers register for change notifications
- `snapshot()` — returns current state as dict
- `dispatch_control(action, value)` — control commands flow back to session
- `on_control(callback)` — register control handler

**Commit:** `feat(sdr): add StateManager for shared state bus`

---

### Task 1.2: Create SDR MQTT Bridge

**Files:**
- Create: `sdr/src/vtms_sdr/mqtt_bridge.py`
- Test: `sdr/tests/test_mqtt_bridge.py`
- Modify: `sdr/pyproject.toml` (add `paho-mqtt>=2.0`)

Bridges StateManager to MQTT:
- Publishes state updates to `{prefix}/sdr/state/{key}` topics (with retain)
- Subscribes to `{prefix}/sdr/control/#` for control commands
- Debounces `signal_power` to max 5 Hz
- Uses JSON for list/dict values, str() for scalars

**Commit:** `feat(sdr): add MQTT bridge for state publishing and control commands`

---

### Task 1.3: Integrate StateManager into SDR Session

**Files:**
- Modify: `sdr/src/vtms_sdr/session.py`
- Modify: `sdr/src/vtms_sdr/cli.py` (add `--mqtt-broker`, `--mqtt-prefix` flags)

Wire `RecordingSession` to publish key state changes through `StateManager`. Add CLI flags to enable MQTT integration.

**Commit:** `feat(sdr): integrate StateManager into recording session with MQTT bridge`

---

## Phase 2: SDR Audio WebSocket

### Task 2.1: Audio WebSocket Server

**Files:**
- Create: `sdr/src/vtms_sdr/audio_ws.py`
- Test: `sdr/tests/test_audio_ws.py`
- Modify: `sdr/pyproject.toml` (add `websockets`)
- Modify: `sdr/src/vtms_sdr/cli.py` (add `--audio-ws-port` flag)

Lightweight WebSocket server streaming demodulated PCM audio (float32 @ 48kHz) as binary frames. Threaded, broadcasts to all connected clients.

**Commit:** `feat(sdr): add WebSocket server for live PCM audio streaming`

---

## Phase 3: React SDR Components

### Task 3.1: SDR Types and Hook

**Files:**
- Create: `web/src/types/sdr.ts`
- Create: `web/src/hooks/useSDR.ts`

Define `SDRState`, `SDRControls`, `TranscriptionLine` types. Implement `useSDR` hook that subscribes to `{prefix}sdr/state/#` MQTT topics and provides control publishers.

**Commit:** `feat(web): add SDR types and useSDR hook for MQTT state/control`

---

### Task 3.2: Signal Meter Component

**Files:**
- Create: `web/src/components/SignalMeter.tsx`

Horizontal bar showing signal power with squelch threshold marker. Uses `role="meter"` for accessibility.

**Commit:** `feat(web): add SignalMeter component for SDR signal visualization`

---

### Task 3.3: Transcription Log Component

**Files:**
- Create: `web/src/components/TranscriptionLog.tsx`

Scrolling log of transcription lines with timestamps. Auto-scrolls to bottom on new entries. Uses `role="log"` for accessibility.

**Commit:** `feat(web): add TranscriptionLog component for SDR radio comms`

---

### Task 3.4: SDR Controls Component

**Files:**
- Create: `web/src/components/SDRControls.tsx`

Frequency display, squelch/gain/PPM sliders, autotune button. Publishes MQTT control messages.

**Commit:** `feat(web): add SDRControls component with frequency/squelch/gain sliders`

---

### Task 3.5: SDR Audio Player Component

**Files:**
- Create: `web/src/components/SDRAudioPlayer.tsx`

Web Audio API playback of PCM audio from SDR WebSocket. Mute/unmute toggle + volume slider.

**Commit:** `feat(web): add SDRAudioPlayer component for live radio audio`

---

### Task 3.6: SDR Panel Container

**Files:**
- Create: `web/src/components/SDRPanel.tsx`

Assembles SignalMeter, SDRControls, TranscriptionLog, SDRAudioPlayer. Shows "SDR Offline" when no data.

**Commit:** `feat(web): add SDRPanel container component`

---

### Task 3.7: Integrate SDR Panel into App Layout

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/components/Layout.tsx`
- Modify: `web/src/App.css`

Three-column layout: Map 45% | Gauges 25% | SDR 30%. GoPro below map. Responsive stacking on narrow screens with collapsible SDR panel.

**Commit:** `feat(web): integrate SDR panel into unified dashboard layout`

---

## Phase 4: Deployment Updates

### Task 4.1: Update Docker Compose and Dockerfiles

**Files:**
- Modify: `deploy/roles/base_pi/templates/docker-compose.yml.j2`
- Modify: `sdr/Dockerfile`

Add MQTT broker/prefix env vars and audio WS port to SDR service. Expose port 9003 in SDR Dockerfile.

**Commit:** `feat(deploy): add MQTT and audio WS config to SDR service`

---

## Phase 5: Testing

### Task 5.1: E2E Tests for SDR Panel

**Files:**
- Create: `web/e2e/sdr-panel.spec.ts`

Test: SDR offline state, signal meter updates, frequency display, transcription log, control message publishing.

**Commit:** `test(web): add E2E tests for SDR dashboard panel`
