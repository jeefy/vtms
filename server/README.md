# VTMS Server

Node/TypeScript Express backend for the Vehicle Telemetry Monitoring System. Persists dashboard configuration to a local JSON file, proxies GoPro HTTP API calls so the browser avoids CORS issues, manages GoPro keep-alive polling, and relays the GoPro video stream through FFmpeg into a WebSocket that the frontend consumes. In production it also serves the built `web/` frontend as static files.

## Prerequisites

- Node 18+
- pnpm (workspace managed from repo root)
- `ffmpeg` binary on `$PATH` (required for stream relay)

## Commands

All commands are run from the repository root via the Makefile:

| Task | Command |
|------|---------|
| Install dependencies | `make node-install` |
| Build (TypeScript -> `dist/`) | `make server-build` |
| Dev (tsx watch, auto-reload) | `make server-dev` |
| Production start | `node server/dist/index.js` |

You can also run from inside `server/` directly:

```sh
pnpm dev       # tsx watch src/index.ts
pnpm build     # tsc
pnpm start     # node dist/index.js
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3001` | HTTP server listen port |
| `HOST` | `0.0.0.0` | HTTP server bind address |
| `STREAM_WS_PORT` | `9002` | WebSocket port for the video stream relay |
| `GOPRO_IP` | `10.5.5.9` | GoPro camera IP (used to build `http://<ip>:8080` base URL) |

## API Routes

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Returns `{ "status": "ok" }` |

### Configuration

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/config` | Load current config (falls back to defaults if file missing) |
| PUT | `/api/config` | Replace config (validates and writes to disk) |
| GET | `/api/config/defaults` | Return the built-in default config |

Config body shape (`AppConfig`):

```jsonc
{
  "mqtt": { "url": "ws://192.168.50.24:9001", "topicPrefix": "lemons/" },
  "gopro": { "apiUrl": "http://localhost:3001", "streamWsUrl": "ws://localhost:9002" },
  "gauges": [
    { "id": "rpm", "topic": "lemons/RPM", "label": "RPM", "min": 0, "max": 8000, "unit": "rpm", "zones": [...] }
  ]
}
```

### GoPro Proxy

All routes proxy to the GoPro HTTP API at `http://<GOPRO_IP>:8080`. Requests time out after 5 seconds. If the camera is unreachable the server returns `502`.

| Method | Path | Proxied To |
|--------|------|------------|
| GET | `/api/gopro/state` | `/gopro/camera/state` |
| GET | `/api/gopro/shutter/:action` | `/gopro/camera/shutter/{start\|stop}` |
| GET | `/api/gopro/presets/set_group?id=N` | `/gopro/camera/presets/set_group?id=N` |
| GET | `/api/gopro/stream/:action` | `/gopro/camera/stream/{start\|stop}` |
| GET | `/api/gopro/keep_alive` | `/gopro/camera/keep_alive` |
| GET | `/api/gopro/connection` | Returns `{ "connected": bool, "ip": "..." }` (local, not proxied) |

### Stream Control

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/stream/start` | Tell GoPro to start streaming and launch FFmpeg relay |
| POST | `/api/stream/stop` | Kill FFmpeg and stop relaying |

## GoPro Stream Relay

The stream pipeline works as follows:

1. **Start**: `POST /api/stream/start` sends `/gopro/camera/stream/start` to the camera.
2. **Ingest**: The GoPro pushes a UDP/TS stream to `udp://@0.0.0.0:8554`.
3. **Transcode**: FFmpeg reads that UDP stream, re-encodes to MPEG1 video (`mpeg1video`, 1500 kbps, 640x480, 30 fps), and pipes raw MPEG-TS to stdout.
4. **Broadcast**: The server reads FFmpeg stdout and broadcasts each chunk to all connected WebSocket clients on port `STREAM_WS_PORT` (default 9002).
5. **Reconnect**: If FFmpeg exits while streaming is active, the server retries with exponential backoff (1s initial, capped at 30s).

The frontend uses a library like JSMpeg to decode the MPEG1 stream in a `<canvas>` element.

## Keep-Alive Service

A background service pings `/gopro/camera/keep_alive` on the GoPro every 3 seconds. The connection status (connected/disconnected) is exposed via `GET /api/gopro/connection`. The service starts automatically when the server boots and logs transitions between connected and disconnected states.

## Data Persistence

Dashboard configuration is stored at `server/data/config.json` (relative to the compiled output directory). The `data/` directory is created automatically on the first `PUT /api/config` call. If the file is missing or unreadable, the server falls back to built-in defaults.

## Static Frontend

In production, the server looks for a `public/` directory adjacent to the compiled `dist/` folder (i.e., `server/public/`). If it exists, Express serves it as static files with an SPA catch-all that returns `index.html` for any non-API route. In development this directory does not exist and the Vite dev server handles the frontend instead.

## Deployment

The server is packaged together with the web frontend in `Dockerfile.web` (multi-stage build). The Docker image copies the built frontend into `server/public/` so the server can serve everything from a single container. See the root-level Dockerfile and Makefile for details.

## Graceful Shutdown

The server handles `SIGTERM` and `SIGINT` by stopping the keep-alive service, destroying the stream manager (kills FFmpeg, closes the WebSocket server), and exiting cleanly.
