# web -- VTMS Telemetry Dashboard

A React/Vite single-page app that provides live vehicle telemetry for 24 Hours of Lemons race cars. It connects to an MQTT broker over WebSocket, renders real-time gauges and a GPS map, displays diagnostic trouble codes, and controls a GoPro camera -- all from a browser.

## Features

- **Radial gauges** for RPM, speed, coolant temp, oil temp, throttle position, and engine load (configurable ranges and color zones)
- **Live GPS map** via Leaflet with current position marker and trail history
- **DTC alerts** shown in a persistent status bar
- **GoPro integration** -- start/stop recording, preset switching, battery/storage display, live preview stream via JSMpeg
- **Settings editor** -- adjust MQTT, GoPro, and gauge config in the browser; persisted through the server API
- **MQTT connection status** indicator

## Prerequisites

- Node.js 18+
- pnpm (managed via the root workspace)
- A running MQTT broker with WebSocket transport (or use the mock data script)

## Development

All commands can be run from the monorepo root or directly from `web/`.

```sh
# Start dev server (from root)
make web-dev
# or
pnpm --filter web dev

# Build for production
make web-build
# or
pnpm --filter web build

# Lint
pnpm --filter web lint

# Preview production build locally
pnpm --filter web preview
```

## Environment Variables

Set these in a `.env` file in `web/` or export them before starting the dev server.

| Variable | Default | Description |
|---|---|---|
| `VITE_MQTT_URL` | `ws://192.168.50.24:9001` | MQTT broker WebSocket URL |
| `VITE_GOPRO_API_URL` | `http://localhost:3001` | GoPro control proxy API base URL |
| `VITE_GOPRO_STREAM_URL` | `ws://localhost:9002` | GoPro MPEG stream WebSocket URL |

## E2E Testing

Tests use Playwright with a Chromium-only project. The global setup (`e2e/global-setup.ts`) automatically:

1. Starts an in-process **Aedes MQTT broker** on a random port
2. Launches a **Vite dev server** pointed at that broker
3. Writes connection details to `e2e/.env.test.json` for test fixtures

Tests run serially (single worker) because they share broker state.

```sh
# Run E2E tests
pnpm --filter web test:e2e

# Run with Playwright UI
pnpm --filter web test:e2e:ui
```

CI uses the `github` reporter and retries failed tests twice.

## Mock Data

The mock data script simulates a full drive session -- engine telemetry, temperatures, and GPS movement near Sonoma Raceway -- by publishing to an MQTT broker.

```sh
# Defaults: broker at ws://192.168.50.24:9001, 500ms publish rate, runs forever
pnpm --filter web mock-data

# Custom broker, faster rate, limited duration
npx tsx scripts/mock-data.ts --url ws://localhost:9001 --rate 200 --duration 60
```

The simulation cycles through idle, accelerating, cruising, decelerating, and braking phases with realistic jitter. Messages are published to `lemons/RPM`, `lemons/SPEED`, `lemons/COOLANT_TEMP`, `lemons/OIL_TEMP`, `lemons/THROTTLE_POS`, `lemons/ENGINE_LOAD`, and `lemons/gps/*`.

The `advanceDriveState` and `stateToMessages` functions are exported so E2E tests can import them directly.

## Architecture

```
src/
  hooks/
    useConfig.ts       -- loads/saves app config via server API
    useMqtt.ts         -- MQTT connection lifecycle and message dispatch
    useTelemetry.ts    -- subscribes to lemons/# topics, parses metrics/GPS/DTCs
    useGoPro.ts        -- GoPro HTTP API client (recording, presets, status polling)
  components/
    Layout.tsx         -- grid shell for all panels
    StatusBar.tsx       -- connection status, GPS fix, DTC alerts, settings button
    GaugePanel.tsx     -- renders a RadialGauge for each configured metric
    RadialGauge.tsx    -- SVG radial gauge with color zones
    MapView.tsx        -- Leaflet map with position marker and polyline trail
    GoProView.tsx      -- camera preview stream (JSMpeg) and status overlay
    GoProControls.tsx  -- record toggle, preset selector, battery/storage
    SettingsPanel.tsx  -- modal editor for MQTT, GoPro, and gauge config
  config/
    gauges.ts          -- default gauge definitions, MQTT config, GoPro config
```

Data flows top-down: hooks manage state and side effects, `App.tsx` composes everything, and components are purely presentational.

## Deployment

The production build is created by `Dockerfile.web` in the monorepo root. The built static assets are served by the VTMS server process -- there is no separate web server in production.
