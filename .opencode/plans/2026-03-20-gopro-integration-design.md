# GoPro WiFi Integration Design

## Goal

Add live GoPro camera view and basic controls to the VTMS dashboard. The GoPro
stream appears in the top-left quadrant, the map moves to the bottom-left, and
gauges remain on the right -- creating a 2x2 dashboard layout.

## Constraints & Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Target cameras | Hero 9-12 | Solid Open GoPro HTTP API support |
| Network mode | STA (same LAN) | Avoids stealing the host's WiFi; GoPro gets a DHCP address on the existing network |
| Stream protocol | FFmpeg -> MPEG1 -> WebSocket -> jsmpeg | Sub-second latency (~200-500ms), no disk I/O, good enough quality for monitoring |
| Control scope | Basic | Start/stop recording, preset switching (video/photo/timelapse), battery + storage status |
| Backend | Node.js + Express | Matches existing stack (Vite/React/TS); proxies GoPro HTTP API, manages FFmpeg |
| GoPro IP | Configurable via `GOPRO_IP` env var | STA mode gives the camera a DHCP address that varies per network |

## Layout

```
+----------------------+----------------------+
|   GoPro Live View    |                      |
|   (jsmpeg canvas +   |      Gauges          |
|    control overlay)  |   (3x2, unchanged)   |
+----------------------+                      |
|       Map            |                      |
|   (Leaflet, as-is)   |                      |
+----------------------+----------------------+
```

- Left column splits vertically: GoPro (top) / Map (bottom), ~50/50.
- Right column: gauges, unchanged.
- When camera is disconnected, GoPro panel shows placeholder; map can expand.
- Mobile (< 768px): vertical stack -- GoPro, Map, Gauges. GoPro collapsible.

## Architecture

```
Browser (React)
  +-- GoProView.tsx          jsmpeg <canvas> connected to ws://<host>:9002
  +-- GoProControls.tsx      record, presets, battery/storage overlay
  +-- useGoPro.ts hook       connection state, status polling, control functions
  +-- MapView.tsx            (unchanged)
  +-- GaugePanel.tsx         (unchanged)

Node.js Backend (Express)
  +-- GoPro Control Proxy    /api/gopro/* -> forward to GoPro HTTP API
  +-- FFmpeg Stream Manager  GoPro UDP TS -> MPEG1 pipe -> WebSocket (:9002)
  +-- Keep-alive loop        GET /gopro/camera/keep_alive every 3s
  +-- MQTT Broker            (existing Aedes on :9001, unchanged)
```

### GoPro HTTP API Endpoints Used

| Action | Endpoint |
|--------|----------|
| Start recording | `GET /gopro/camera/shutter/start` |
| Stop recording | `GET /gopro/camera/shutter/stop` |
| Load preset | `GET /gopro/camera/presets/load?id=<id>` |
| Set preset group | `GET /gopro/camera/presets/set_group?id=1000\|1001\|1002` |
| Camera state | `GET /gopro/camera/state` |
| Start preview | `GET /gopro/camera/stream/start` |
| Stop preview | `GET /gopro/camera/stream/stop` |
| Keep alive | `GET /gopro/camera/keep_alive` |

### FFmpeg Pipeline

```bash
ffmpeg -i udp://@0.0.0.0:8554 \
  -f mpegts -codec:v mpeg1video \
  -b:v 1500k -r 30 -s 640x480 \
  -bf 0 -q:v 5 \
  pipe:1
```

Output piped to a WebSocket server (port 9002) using the `ws` package. jsmpeg
on the client connects and renders frames to a `<canvas>`.

## GoPro Control UI

Controls overlay the video canvas, semi-transparent, auto-hide after inactivity:

- **Record button**: red dot when recording, toggles shutter start/stop
- **Preset tabs**: Video / Photo / Timelapse (preset groups 1000/1001/1002)
- **Status bar**: battery %, remaining storage (GB)
- **Connection indicator**: Connected / Connecting / Camera Not Found

## Error Handling

- **Camera not connected**: placeholder panel with configured IP + Retry button;
  map expands to fill left column.
- **Stream drops**: backend detects FFmpeg exit, restarts with exponential backoff
  (1s -> 2s -> 4s -> max 30s); re-sends `/gopro/camera/stream/start` first.
  Frontend shows frozen last frame + "Reconnecting..." overlay.
- **Camera sleep**: keep-alive failure shows "Camera Sleeping" status. Wake
  requires physical button (BLE wake out of scope).
- **Backend down**: useGoPro hook shows "Backend Unavailable", other dashboard
  features (map, gauges, MQTT) continue independently.

## New Dependencies

| Package | Purpose | Side |
|---------|---------|------|
| `express` | HTTP server for control proxy | Backend |
| `ws` | WebSocket server for video stream | Backend |
| `@cycjimmy/jsmpeg-player` | MPEG1 video decoder + canvas renderer | Frontend |
| FFmpeg (system) | Stream transcoding | Host |

## File Structure

```
server/
  src/
    index.ts              Express app entry point
    gopro-proxy.ts         Control proxy routes
    stream-manager.ts      FFmpeg process + WebSocket relay
    keep-alive.ts          GoPro keep-alive loop
  package.json
  tsconfig.json

web/src/
  components/
    GoProView.tsx           jsmpeg canvas wrapper
    GoProControls.tsx       overlay controls
  hooks/
    useGoPro.ts             connection + control hook
```

## Testing

- **Unit**: useGoPro hook (mock fetch), GoProControls (render states)
- **E2e (Playwright)**: mock backend WebSocket + API; test panel rendering,
  "No Camera" state, control interactions, 2x2 layout grid
- **Integration**: backend proxy with mocked GoPro responses, FFmpeg manager
  with mocked child_process
- **Manual**: documented setup with real GoPro on LAN
