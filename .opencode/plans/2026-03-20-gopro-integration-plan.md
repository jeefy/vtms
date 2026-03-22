# GoPro WiFi Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add live GoPro camera view (via jsmpeg WebSocket) and basic controls (record, presets, status) to the VTMS dashboard in a 2x2 layout.

**Architecture:** Node.js Express backend proxies GoPro HTTP commands and manages an FFmpeg process that converts the GoPro's UDP MPEG-TS stream into MPEG1 piped over WebSocket (port 9002). Frontend uses jsmpeg to render frames on a canvas, with an overlay for camera controls.

**Tech Stack:** Express, ws, child_process (FFmpeg), @cycjimmy/jsmpeg-player, React hooks, Playwright

---

## Task 1: Backend Scaffolding

**Files:**
- Create: `server/package.json`
- Create: `server/tsconfig.json`
- Create: `server/src/index.ts`

**Step 1: Create server/package.json**

```json
{
  "name": "vtms-server",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "tsx watch src/index.ts",
    "build": "tsc",
    "start": "node dist/index.js"
  },
  "dependencies": {
    "express": "^5.1.0",
    "ws": "^8.18.0"
  },
  "devDependencies": {
    "@types/express": "^5.0.0",
    "@types/node": "^24.12.0",
    "@types/ws": "^8.18.1",
    "tsx": "^4.21.0",
    "typescript": "~5.9.3"
  }
}
```

**Step 2: Create server/tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "declaration": true
  },
  "include": ["src"]
}
```

**Step 3: Create server/src/index.ts (minimal Express shell)**

```ts
import express from "express";

const app = express();
const PORT = parseInt(process.env.PORT ?? "3001", 10);
const HOST = process.env.HOST ?? "0.0.0.0";

app.get("/api/health", (_req, res) => {
  res.json({ status: "ok" });
});

app.listen(PORT, HOST, () => {
  console.log(`VTMS server listening on http://${HOST}:${PORT}`);
});
```

**Step 4: Install dependencies**

Run: `cd server && npm install`

**Step 5: Verify server starts**

Run: `cd server && npx tsx src/index.ts &` then `curl http://localhost:3001/api/health`
Expected: `{"status":"ok"}`

**Step 6: Commit**

```
feat(server): scaffold Express backend for GoPro integration
```

---

## Task 2: GoPro Control Proxy

**Files:**
- Create: `server/src/gopro-proxy.ts`
- Modify: `server/src/index.ts`

**Step 1: Create server/src/gopro-proxy.ts**

```ts
import { Router } from "express";

const GOPRO_IP = process.env.GOPRO_IP ?? "10.5.5.9";
const GOPRO_BASE = `http://${GOPRO_IP}:8080`;

const router = Router();

// Camera state (battery, storage, recording status, etc.)
router.get("/state", async (_req, res) => {
  try {
    const response = await fetch(`${GOPRO_BASE}/gopro/camera/state`);
    const data = await response.json();
    res.json(data);
  } catch (err) {
    res.status(502).json({ error: "Camera not reachable", detail: String(err) });
  }
});

// Shutter start/stop
router.get("/shutter/:action", async (req, res) => {
  const action = req.params.action;
  if (action !== "start" && action !== "stop") {
    res.status(400).json({ error: "Invalid action, use start or stop" });
    return;
  }
  try {
    const response = await fetch(`${GOPRO_BASE}/gopro/camera/shutter/${action}`);
    const data = await response.json();
    res.json(data);
  } catch (err) {
    res.status(502).json({ error: "Camera not reachable", detail: String(err) });
  }
});

// Preset group (1000=video, 1001=photo, 1002=timelapse)
router.get("/presets/set_group", async (req, res) => {
  const id = req.query.id;
  if (!id) {
    res.status(400).json({ error: "Missing id query param" });
    return;
  }
  try {
    const response = await fetch(
      `${GOPRO_BASE}/gopro/camera/presets/set_group?id=${id}`
    );
    const data = await response.json();
    res.json(data);
  } catch (err) {
    res.status(502).json({ error: "Camera not reachable", detail: String(err) });
  }
});

// Stream start/stop
router.get("/stream/:action", async (req, res) => {
  const action = req.params.action;
  if (action !== "start" && action !== "stop") {
    res.status(400).json({ error: "Invalid action, use start or stop" });
    return;
  }
  try {
    const response = await fetch(`${GOPRO_BASE}/gopro/camera/stream/${action}`);
    const data = await response.json();
    res.json(data);
  } catch (err) {
    res.status(502).json({ error: "Camera not reachable", detail: String(err) });
  }
});

// Keep alive
router.get("/keep_alive", async (_req, res) => {
  try {
    const response = await fetch(`${GOPRO_BASE}/gopro/camera/keep_alive`);
    const data = await response.json();
    res.json(data);
  } catch (err) {
    res.status(502).json({ error: "Camera not reachable", detail: String(err) });
  }
});

export { router as goProRouter };
```

**Step 2: Wire router into index.ts**

Add to `server/src/index.ts`:
```ts
import { goProRouter } from "./gopro-proxy.js";

// After health endpoint:
app.use("/api/gopro", goProRouter);
```

**Step 3: Verify routes register**

Run: `cd server && npx tsx src/index.ts &` then `curl http://localhost:3001/api/gopro/state`
Expected: `{"error":"Camera not reachable",...}` (502 since no GoPro connected)

**Step 4: Commit**

```
feat(server): add GoPro HTTP control proxy routes
```

---

## Task 3: FFmpeg Stream Manager + WebSocket Relay

**Files:**
- Create: `server/src/stream-manager.ts`
- Modify: `server/src/index.ts`

**Step 1: Create server/src/stream-manager.ts**

```ts
import { spawn, type ChildProcess } from "node:child_process";
import { WebSocketServer, WebSocket } from "ws";
import type { Server } from "node:http";

const GOPRO_IP = process.env.GOPRO_IP ?? "10.5.5.9";
const STREAM_WS_PORT = parseInt(process.env.STREAM_WS_PORT ?? "9002", 10);
const UDP_PORT = parseInt(process.env.GOPRO_UDP_PORT ?? "8554", 10);

export class StreamManager {
  private ffmpeg: ChildProcess | null = null;
  private wss: WebSocketServer | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = 1000;
  private readonly maxReconnectDelay = 30000;
  private running = false;

  /**
   * Start the WebSocket server and (optionally) the FFmpeg pipeline.
   * Call `startStream()` separately to tell the GoPro to begin streaming
   * and launch FFmpeg.
   */
  init(httpServer?: Server) {
    this.wss = new WebSocketServer({ port: STREAM_WS_PORT });
    console.log(`[stream] WebSocket server listening on ws://0.0.0.0:${STREAM_WS_PORT}`);
    return this;
  }

  /** Tell the GoPro to start its UDP preview, then launch FFmpeg. */
  async startStream() {
    if (this.running) return;
    this.running = true;

    // Tell GoPro to start streaming
    try {
      await fetch(`http://${GOPRO_IP}:8080/gopro/camera/stream/start`);
    } catch {
      console.warn("[stream] Could not reach GoPro to start stream");
    }

    this.spawnFFmpeg();
  }

  /** Stop the FFmpeg process and tell the GoPro to stop streaming. */
  async stopStream() {
    this.running = false;
    this.clearReconnect();
    if (this.ffmpeg) {
      this.ffmpeg.kill("SIGTERM");
      this.ffmpeg = null;
    }
    try {
      await fetch(`http://${GOPRO_IP}:8080/gopro/camera/stream/stop`);
    } catch {
      // Camera may already be off
    }
  }

  /** Shut everything down. */
  async destroy() {
    await this.stopStream();
    this.wss?.close();
    this.wss = null;
  }

  private spawnFFmpeg() {
    if (!this.wss) return;

    const args = [
      "-i", `udp://@0.0.0.0:${UDP_PORT}`,
      "-f", "mpegts",
      "-codec:v", "mpeg1video",
      "-b:v", "1500k",
      "-r", "30",
      "-s", "640x480",
      "-bf", "0",
      "-q:v", "5",
      "pipe:1",
    ];

    console.log("[stream] Spawning FFmpeg:", "ffmpeg", args.join(" "));
    this.ffmpeg = spawn("ffmpeg", args, { stdio: ["ignore", "pipe", "pipe"] });

    this.ffmpeg.stdout?.on("data", (chunk: Buffer) => {
      this.broadcast(chunk);
    });

    this.ffmpeg.stderr?.on("data", (data: Buffer) => {
      // FFmpeg logs to stderr; only log errors
      const msg = data.toString();
      if (msg.includes("Error") || msg.includes("error")) {
        console.error("[ffmpeg]", msg.trim());
      }
    });

    this.ffmpeg.on("exit", (code) => {
      console.warn(`[stream] FFmpeg exited with code ${code}`);
      this.ffmpeg = null;
      if (this.running) {
        this.scheduleReconnect();
      }
    });

    // Reset reconnect delay on successful start
    this.reconnectDelay = 1000;
  }

  private broadcast(data: Buffer) {
    if (!this.wss) return;
    for (const client of this.wss.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(data);
      }
    }
  }

  private scheduleReconnect() {
    this.clearReconnect();
    console.log(`[stream] Reconnecting in ${this.reconnectDelay}ms...`);
    this.reconnectTimer = setTimeout(async () => {
      try {
        await fetch(`http://${GOPRO_IP}:8080/gopro/camera/stream/start`);
      } catch {
        // Camera may be unavailable
      }
      this.spawnFFmpeg();
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
    }, this.reconnectDelay);
  }

  private clearReconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}
```

**Step 2: Integrate into server/src/index.ts**

Add stream manager initialization and route to start/stop:
```ts
import { StreamManager } from "./stream-manager.js";

const streamManager = new StreamManager().init();

// Add stream control endpoints
app.post("/api/stream/start", async (_req, res) => {
  await streamManager.startStream();
  res.json({ status: "started" });
});

app.post("/api/stream/stop", async (_req, res) => {
  await streamManager.stopStream();
  res.json({ status: "stopped" });
});

// Graceful shutdown
process.on("SIGTERM", async () => {
  await streamManager.destroy();
  process.exit(0);
});
```

**Step 3: Verify server starts without FFmpeg running**

Run: `cd server && npx tsx src/index.ts`
Expected: Prints WebSocket server listening message, no crash

**Step 4: Commit**

```
feat(server): add FFmpeg stream manager with WebSocket relay
```

---

## Task 4: GoPro Keep-Alive Service

**Files:**
- Create: `server/src/keep-alive.ts`
- Modify: `server/src/index.ts`

**Step 1: Create server/src/keep-alive.ts**

```ts
const GOPRO_IP = process.env.GOPRO_IP ?? "10.5.5.9";
const GOPRO_BASE = `http://${GOPRO_IP}:8080`;
const INTERVAL_MS = 3000;

export class KeepAliveService {
  private timer: ReturnType<typeof setInterval> | null = null;
  private _connected = false;

  get connected() {
    return this._connected;
  }

  start() {
    if (this.timer) return;
    this.timer = setInterval(() => this.ping(), INTERVAL_MS);
    this.ping(); // immediate first ping
    console.log("[keep-alive] Started (every 3s)");
  }

  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    this._connected = false;
  }

  private async ping() {
    try {
      const res = await fetch(`${GOPRO_BASE}/gopro/camera/keep_alive`, {
        signal: AbortSignal.timeout(2000),
      });
      this._connected = res.ok;
    } catch {
      this._connected = false;
    }
  }
}
```

**Step 2: Integrate into server/src/index.ts**

```ts
import { KeepAliveService } from "./keep-alive.js";

const keepAlive = new KeepAliveService();
keepAlive.start();

app.get("/api/gopro/connection", (_req, res) => {
  res.json({ connected: keepAlive.connected, ip: process.env.GOPRO_IP ?? "10.5.5.9" });
});
```

**Step 3: Commit**

```
feat(server): add GoPro keep-alive service
```

---

## Task 5: Frontend - Install jsmpeg + useGoPro Hook

**Files:**
- Modify: `web/package.json` (install @cycjimmy/jsmpeg-player)
- Create: `web/src/hooks/useGoPro.ts`
- Create: `web/src/types/gopro.ts`

**Step 1: Install jsmpeg player**

Run: `cd web && npm install @cycjimmy/jsmpeg-player`

**Step 2: Create web/src/types/gopro.ts**

```ts
export type GoProConnectionStatus = "disconnected" | "connecting" | "connected" | "error";

export type GoProPreset = "video" | "photo" | "timelapse";

export const PRESET_GROUP_IDS: Record<GoProPreset, number> = {
  video: 1000,
  photo: 1001,
  timelapse: 1002,
};

export interface GoProState {
  connectionStatus: GoProConnectionStatus;
  isRecording: boolean;
  activePreset: GoProPreset;
  batteryPercent: number | null;
  remainingStorageGB: number | null;
}
```

**Step 3: Create web/src/hooks/useGoPro.ts**

```ts
import { useState, useEffect, useCallback, useRef } from "react";
import type { GoProState, GoProPreset } from "../types/gopro";
import { PRESET_GROUP_IDS } from "../types/gopro";

const API_BASE = import.meta.env.VITE_GOPRO_API_URL ?? "http://localhost:3001";
const POLL_INTERVAL = 5000;

export function useGoPro() {
  const [state, setState] = useState<GoProState>({
    connectionStatus: "disconnected",
    isRecording: false,
    activePreset: "video",
    batteryPercent: null,
    remainingStorageGB: null,
  });

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll camera connection + state
  useEffect(() => {
    const poll = async () => {
      try {
        // Check backend connection to camera
        const connRes = await fetch(`${API_BASE}/api/gopro/connection`);
        const connData = await connRes.json();

        if (!connData.connected) {
          setState((prev) => ({ ...prev, connectionStatus: "disconnected" }));
          return;
        }

        // Get camera state
        const stateRes = await fetch(`${API_BASE}/api/gopro/state`);
        if (!stateRes.ok) {
          setState((prev) => ({ ...prev, connectionStatus: "error" }));
          return;
        }

        const cameraState = await stateRes.json();
        const status = cameraState.status ?? {};

        setState({
          connectionStatus: "connected",
          isRecording: status["8"] === 1, // Status ID 8 = is recording
          activePreset: detectPreset(status),
          batteryPercent: status["2"] ?? null, // Status ID 2 = battery
          remainingStorageGB: status["54"] != null
            ? Math.round((status["54"] / 1024) * 10) / 10 // KB to GB
            : null,
        });
      } catch {
        setState((prev) => ({ ...prev, connectionStatus: "disconnected" }));
      }
    };

    poll();
    pollRef.current = setInterval(poll, POLL_INTERVAL);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const toggleRecord = useCallback(async () => {
    const action = state.isRecording ? "stop" : "start";
    try {
      await fetch(`${API_BASE}/api/gopro/shutter/${action}`);
      setState((prev) => ({ ...prev, isRecording: !prev.isRecording }));
    } catch {
      // Will be corrected on next poll
    }
  }, [state.isRecording]);

  const setPreset = useCallback(async (preset: GoProPreset) => {
    try {
      await fetch(`${API_BASE}/api/gopro/presets/set_group?id=${PRESET_GROUP_IDS[preset]}`);
      setState((prev) => ({ ...prev, activePreset: preset }));
    } catch {
      // Will be corrected on next poll
    }
  }, []);

  const startStream = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/api/stream/start`, { method: "POST" });
    } catch {
      console.warn("Failed to start stream");
    }
  }, []);

  const stopStream = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/api/stream/stop`, { method: "POST" });
    } catch {
      console.warn("Failed to stop stream");
    }
  }, []);

  return { ...state, toggleRecord, setPreset, startStream, stopStream };
}

function detectPreset(status: Record<string, number>): GoProPreset {
  // Status ID 43 = active preset group
  const group = status["43"];
  if (group === 1001) return "photo";
  if (group === 1002) return "timelapse";
  return "video";
}
```

**Step 4: Commit**

```
feat(web): add useGoPro hook and GoPro type definitions
```

---

## Task 6: Frontend - GoProView + GoProControls Components

**Files:**
- Create: `web/src/components/GoProView.tsx`
- Create: `web/src/components/GoProControls.tsx`

**Step 1: Create web/src/components/GoProView.tsx**

```tsx
import { useEffect, useRef } from "react";
import JSMpeg from "@cycjimmy/jsmpeg-player";
import { GoProControls } from "./GoProControls";
import type { GoProState, GoProPreset } from "../types/gopro";

interface GoProViewProps extends GoProState {
  streamWsUrl: string;
  onToggleRecord: () => void;
  onSetPreset: (preset: GoProPreset) => void;
}

export function GoProView({
  streamWsUrl,
  connectionStatus,
  isRecording,
  activePreset,
  batteryPercent,
  remainingStorageGB,
  onToggleRecord,
  onSetPreset,
}: GoProViewProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const playerRef = useRef<any>(null);

  useEffect(() => {
    if (!canvasRef.current || connectionStatus !== "connected") return;

    playerRef.current = new JSMpeg.VideoElement(
      canvasRef.current.parentElement!,
      streamWsUrl,
      { canvas: canvasRef.current },
      { audio: false, videoBufferSize: 512 * 1024 }
    );

    return () => {
      playerRef.current?.destroy();
      playerRef.current = null;
    };
  }, [streamWsUrl, connectionStatus]);

  if (connectionStatus !== "connected") {
    return (
      <div className="gopro-view gopro-disconnected">
        <div className="gopro-placeholder">
          <span className="gopro-placeholder-icon">📷</span>
          <span className="gopro-placeholder-text">
            {connectionStatus === "connecting"
              ? "Connecting to GoPro..."
              : "No Camera Connected"}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="gopro-view">
      <canvas ref={canvasRef} className="gopro-canvas" />
      <GoProControls
        isRecording={isRecording}
        activePreset={activePreset}
        batteryPercent={batteryPercent}
        remainingStorageGB={remainingStorageGB}
        onToggleRecord={onToggleRecord}
        onSetPreset={onSetPreset}
      />
    </div>
  );
}
```

**Step 2: Create web/src/components/GoProControls.tsx**

```tsx
import { useState, useEffect, useCallback } from "react";
import type { GoProPreset } from "../types/gopro";

interface GoProControlsProps {
  isRecording: boolean;
  activePreset: GoProPreset;
  batteryPercent: number | null;
  remainingStorageGB: number | null;
  onToggleRecord: () => void;
  onSetPreset: (preset: GoProPreset) => void;
}

export function GoProControls({
  isRecording,
  activePreset,
  batteryPercent,
  remainingStorageGB,
  onToggleRecord,
  onSetPreset,
}: GoProControlsProps) {
  const [visible, setVisible] = useState(true);
  const [hideTimer, setHideTimer] = useState<ReturnType<typeof setTimeout> | null>(null);

  const resetHideTimer = useCallback(() => {
    setVisible(true);
    if (hideTimer) clearTimeout(hideTimer);
    const timer = setTimeout(() => setVisible(false), 4000);
    setHideTimer(timer);
  }, [hideTimer]);

  useEffect(() => {
    resetHideTimer();
    return () => {
      if (hideTimer) clearTimeout(hideTimer);
    };
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className={`gopro-controls ${visible ? "gopro-controls-visible" : "gopro-controls-hidden"}`}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => resetHideTimer()}
      onTouchStart={() => resetHideTimer()}
    >
      <div className="gopro-controls-row">
        <button
          className={`gopro-record-btn ${isRecording ? "recording" : ""}`}
          onClick={onToggleRecord}
          aria-label={isRecording ? "Stop recording" : "Start recording"}
        >
          <span className="gopro-record-dot" />
          {isRecording ? "STOP" : "REC"}
        </button>

        <div className="gopro-presets">
          {(["video", "photo", "timelapse"] as GoProPreset[]).map((preset) => (
            <button
              key={preset}
              className={`gopro-preset-btn ${activePreset === preset ? "active" : ""}`}
              onClick={() => onSetPreset(preset)}
              aria-label={`Switch to ${preset}`}
            >
              {preset === "video" ? "VID" : preset === "photo" ? "PIC" : "TL"}
            </button>
          ))}
        </div>
      </div>

      <div className="gopro-status-row">
        {batteryPercent != null && (
          <span className="gopro-status-item">
            BAT {batteryPercent}%
          </span>
        )}
        {remainingStorageGB != null && (
          <span className="gopro-status-item">
            SD {remainingStorageGB}G
          </span>
        )}
      </div>
    </div>
  );
}
```

**Step 3: Commit**

```
feat(web): add GoProView and GoProControls components
```

---

## Task 7: GoPro CSS Styles

**Files:**
- Modify: `web/src/App.css`

**Step 1: Add GoPro styles to App.css**

Append after the Gauge Panel section:

```css
/* ── GoPro View ───────────────────────────────────────────── */
.gopro-view {
  width: 100%;
  height: 100%;
  position: relative;
  background: #000;
  overflow: hidden;
}

.gopro-canvas {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.gopro-disconnected {
  display: flex;
  align-items: center;
  justify-content: center;
}

.gopro-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--text-dim);
}

.gopro-placeholder-icon {
  font-size: 32px;
}

.gopro-placeholder-text {
  font-size: 14px;
}

/* ── GoPro Controls Overlay ───────────────────────────────── */
.gopro-controls {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 8px 12px;
  background: rgba(15, 23, 42, 0.75);
  transition: opacity 0.3s ease;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.gopro-controls-visible {
  opacity: 1;
}

.gopro-controls-hidden {
  opacity: 0.15;
}

.gopro-controls:hover {
  opacity: 1;
}

.gopro-controls-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.gopro-record-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: transparent;
  color: var(--text);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  font-family: inherit;
}

.gopro-record-btn.recording {
  border-color: var(--red);
  color: var(--red);
}

.gopro-record-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-dim);
}

.gopro-record-btn.recording .gopro-record-dot {
  background: var(--red);
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.gopro-presets {
  display: flex;
  gap: 4px;
}

.gopro-preset-btn {
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}

.gopro-preset-btn.active {
  background: var(--accent);
  color: var(--text);
  border-color: var(--accent);
}

.gopro-status-row {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--text-dim);
  font-family: monospace;
}

.gopro-status-item {
  white-space: nowrap;
}
```

**Step 2: Commit**

```
feat(web): add GoPro view and controls CSS styles
```

---

## Task 8: Layout Restructure (2x2 Grid)

**Files:**
- Modify: `web/src/components/Layout.tsx`
- Modify: `web/src/App.css` (layout section)

**Step 1: Update Layout.tsx to accept gopro prop and render 2x2 grid**

Replace `Layout.tsx` content:

```tsx
import type { ReactNode } from "react";

interface LayoutProps {
  statusBar: ReactNode;
  gopro: ReactNode;
  map: ReactNode;
  gauges: ReactNode;
}

/**
 * Page layout shell.
 *
 * 2x2 grid: GoPro (top-left), Map (bottom-left), Gauges (right column).
 * StatusBar spans the top.
 */
export function Layout({ statusBar, gopro, map, gauges }: LayoutProps) {
  return (
    <div className="layout">
      <header className="layout-header">{statusBar}</header>

      <main className="layout-main">
        <div className="layout-left">
          <section className="layout-gopro">{gopro}</section>
          <section className="layout-map">{map}</section>
        </div>
        <aside className="layout-gauges">{gauges}</aside>
      </main>
    </div>
  );
}
```

**Step 2: Update layout CSS in App.css**

Replace the Layout section (`.layout` through `.layout-footer`):

```css
/* ── Layout ───────────────────────────────────────────────── */
.layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
}

.layout-header {
  flex-shrink: 0;
}

.layout-main {
  flex: 1;
  display: flex;
  min-height: 0;
}

.layout-left {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.layout-gopro {
  flex: 1;
  min-height: 0;
  position: relative;
  border-bottom: 1px solid var(--border);
}

.layout-map {
  flex: 1;
  min-height: 0;
  position: relative;
}

.layout-gauges {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border-left: 1px solid var(--border);
}
```

**Step 3: Update responsive breakpoints**

Replace `@media (max-width: 768px)`:

```css
@media (max-width: 768px) {
  .layout-main {
    flex-direction: column;
  }

  .layout-left {
    flex: none;
    min-height: 300px;
  }

  .layout-gopro {
    flex: 1;
    min-height: 150px;
  }

  .layout-map {
    flex: 1;
    min-height: 200px;
  }

  .layout-gauges {
    flex: none;
    border-left: none;
    border-top: 1px solid var(--border);
    max-height: 50vh;
  }

  .gauge-panel {
    grid-template-columns: repeat(3, 1fr);
  }

  .status-bar-center {
    display: none;
  }
}
```

**Step 4: Commit**

```
feat(web): restructure layout to 2x2 grid for GoPro integration
```

---

## Task 9: Wire GoPro into App.tsx

**Files:**
- Modify: `web/src/App.tsx`

**Step 1: Update App.tsx to use GoPro hook and pass to Layout**

```tsx
import { Layout } from "./components/Layout";
import { StatusBar } from "./components/StatusBar";
import { MapView } from "./components/MapView";
import { GaugePanel } from "./components/GaugePanel";
import { GoProView } from "./components/GoProView";
import { useTelemetry } from "./hooks/useTelemetry";
import { useGoPro } from "./hooks/useGoPro";
import "./App.css";

const STREAM_WS_URL =
  import.meta.env.VITE_GOPRO_STREAM_URL ?? "ws://localhost:9002";

function App() {
  const { metrics, gps, trail, dtcs, connectionStatus } = useTelemetry();
  const gopro = useGoPro();

  const hasGpsFix = gps.latitude !== null && gps.longitude !== null;

  return (
    <Layout
      statusBar={
        <StatusBar
          connectionStatus={connectionStatus}
          hasGpsFix={hasGpsFix}
          dtcs={dtcs}
        />
      }
      gopro={
        <GoProView
          streamWsUrl={STREAM_WS_URL}
          connectionStatus={gopro.connectionStatus}
          isRecording={gopro.isRecording}
          activePreset={gopro.activePreset}
          batteryPercent={gopro.batteryPercent}
          remainingStorageGB={gopro.remainingStorageGB}
          onToggleRecord={gopro.toggleRecord}
          onSetPreset={gopro.setPreset}
        />
      }
      map={<MapView gps={gps} trail={trail} />}
      gauges={<GaugePanel metrics={metrics} />}
    />
  );
}

export default App;
```

**Step 2: Add env vars to .env.example or document**

The frontend needs these env vars:
- `VITE_GOPRO_API_URL` - backend URL (default: `http://localhost:3001`)
- `VITE_GOPRO_STREAM_URL` - WebSocket stream URL (default: `ws://localhost:9002`)

**Step 3: Verify build**

Run: `cd web && npm run build`
Expected: Successful build with no type errors

**Step 4: Commit**

```
feat(web): wire GoPro view into App with useGoPro hook
```

---

## Task 10: Update Existing E2E Tests

**Files:**
- Modify: `web/e2e/dashboard.spec.ts`

The existing e2e tests don't know about the GoPro panel. Update them so they
still pass with the new 2x2 layout. The GoPro panel will show the disconnected
placeholder in tests (no real camera).

**Step 1: Verify existing tests still pass**

Run: `cd web && npx playwright test`

If any tests break due to layout changes, fix selector/assertion issues.
The GoPro panel should be in disconnected state (placeholder), which is fine.

**Step 2: Add GoPro-specific e2e tests**

Add to `dashboard.spec.ts`:

```ts
test("GoPro panel shows disconnected placeholder when no camera", async ({ page }) => {
  // The GoPro panel should show placeholder since there's no camera
  const placeholder = page.locator(".gopro-placeholder");
  await expect(placeholder).toBeVisible({ timeout: 5000 });
  await expect(placeholder).toContainText("No Camera Connected");
});

test("2x2 layout has gopro, map, and gauges panels", async ({ page }) => {
  await expect(page.locator(".layout-gopro")).toBeVisible();
  await expect(page.locator(".layout-map")).toBeVisible();
  await expect(page.locator(".layout-gauges")).toBeVisible();
});
```

**Step 3: Run full test suite**

Run: `cd web && npx playwright test`
Expected: All tests pass (existing + new)

**Step 4: Commit**

```
test(web): update e2e tests for 2x2 layout with GoPro panel
```

---

## Task 11: Build Verification + Final Commit

**Step 1: Run full build**

Run: `cd web && npm run build`
Expected: Clean build

**Step 2: Run full e2e suite**

Run: `cd web && npx playwright test`
Expected: All tests pass

**Step 3: Manual test checklist**

With the backend running (`cd server && npm run dev`):
1. Dashboard loads with GoPro placeholder in top-left
2. Map is in bottom-left
3. Gauges are on the right, unchanged
4. Mock telemetry data still works
5. If a GoPro is connected: stream appears, controls work

**Step 4: Final commit if any loose ends**

```
chore: final cleanup for GoPro integration
```
