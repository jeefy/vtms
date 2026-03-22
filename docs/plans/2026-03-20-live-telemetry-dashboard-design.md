# Live Telemetry Dashboard Design

**Date:** 2026-03-20
**Status:** Approved

## Problem

The existing Grafana UI for visualizing live OBDII and GPS telemetry is insufficient. We need a purpose-built single-page web application that provides a better live view of the vehicle, with an architecture that supports future historical playback.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Live data source | MQTT via WebSockets | Reuses existing MQTT bus, lowest latency, no new backend |
| Layout | Map-centric with gauge panel | GPS position is primary, engine metrics secondary |
| Frontend stack | React + TypeScript (Vite) | Strong ecosystem, good for future playback features |
| Map | Leaflet + OpenStreetMap | Free, no API key, lightweight |
| Gauges | Analog/radial, config-driven | Familiar car-cluster aesthetic, easy to add/remove |
| Default gauges | Core 6 (RPM, Speed, Coolant Temp, Oil Temp, Throttle, Engine Load) | Essential monitoring set, expandable via config |
| Deployment | Static files, MQTT WebSocket direct | No backend needed for live view |

## Architecture

```
MQTT Broker (WebSocket)  <---->  React SPA (browser)
       ^                            |
       |  MQTT/TCP                  Leaflet Map + Radial Gauges + Status
       |
  client.py (OBD + GPS)
```

The browser subscribes directly to `lemons/#` on the MQTT broker's WebSocket endpoint. No new backend is required for the live view. The existing `client.py` and `server.py` are unchanged.

## Frontend Structure

```
web/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── public/
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── config/
    │   └── gauges.ts          # Gauge definitions (configurable list)
    ├── hooks/
    │   ├── useMqtt.ts         # MQTT connection + subscription
    │   └── useTelemetry.ts    # State management for all metrics
    ├── components/
    │   ├── MapView.tsx         # Leaflet map with live position marker
    │   ├── GaugePanel.tsx      # Container for gauge grid
    │   ├── RadialGauge.tsx     # Individual analog gauge component
    │   ├── StatusBar.tsx       # Connection status, DTC alerts
    │   └── Layout.tsx          # Overall page layout
    └── types/
        └── telemetry.ts       # TypeScript types for metrics
```

## Layout

```
┌──────────────────────────────────────────────┐
│  StatusBar (MQTT connected, GPS fix, DTCs)   │
├────────────────────────┬─────────────────────┤
│                        │   ┌───┐  ┌───┐      │
│                        │   │RPM│  │SPD│      │
│       Map (Leaflet)    │   └───┘  └───┘      │
│                        │   ┌───┐  ┌───┐      │
│     ~60% width         │   │CLT│  │OIL│      │
│                        │   └───┘  └───┘      │
│                        │   ┌───┐  ┌───┐      │
│                        │   │TPS│  │LOD│      │
│                        │   └───┘  └───┘      │
├────────────────────────┴─────────────────────┤
│  (Future: playback controls / timeline bar)  │
└──────────────────────────────────────────────┘
```

- Map takes ~60% width, gauge panel ~40%
- Responsive: stacks vertically on narrow screens (map on top)
- Bottom bar reserved for future playback controls (placeholder only for now)

## Key Components

### `useMqtt` hook

Connects to MQTT broker via WebSocket using `mqtt` (MQTT.js npm package). Subscribes to `lemons/#`. Dispatches incoming messages to a telemetry state store. Handles reconnection and exposes connection status.

### `useTelemetry` hook

Maintains a `Map<string, TelemetryValue>` of the latest value for each metric topic. Components subscribe to specific keys. Decoupled from data source to support future playback.

### `gauges.ts` config

Defines which gauges to render:

```ts
export const gaugeConfig = [
  { topic: "lemons/RPM", label: "RPM", min: 0, max: 8000, unit: "rpm", zones: [...] },
  { topic: "lemons/SPEED", label: "Speed", min: 0, max: 200, unit: "km/h" },
  { topic: "lemons/COOLANT_TEMP", label: "Coolant", min: 0, max: 130, unit: "°C", zones: [...] },
  { topic: "lemons/OIL_TEMP", label: "Oil Temp", min: 0, max: 150, unit: "°C", zones: [...] },
  { topic: "lemons/THROTTLE_POS", label: "Throttle", min: 0, max: 100, unit: "%" },
  { topic: "lemons/ENGINE_LOAD", label: "Load", min: 0, max: 100, unit: "%" },
];
```

To add a gauge, add an entry. No component changes needed.

### `MapView`

Leaflet map centered on latest GPS position. Marker follows the car. Trail line shows recent path (last N points). Auto-pans to follow position.

### `RadialGauge`

SVG-based analog gauge. Configurable min/max/zones (green/yellow/red). Smooth CSS transitions on value changes.

### `StatusBar`

Shows MQTT connection state, GPS fix status, and active DTCs as alerts.

## MQTT Topic Mapping

| MQTT Topic | State Key | Used By |
|-----------|-----------|---------|
| `lemons/RPM` | `RPM` | Gauge |
| `lemons/SPEED` | `SPEED` | Gauge |
| `lemons/COOLANT_TEMP` | `COOLANT_TEMP` | Gauge |
| `lemons/OIL_TEMP` | `OIL_TEMP` | Gauge |
| `lemons/THROTTLE_POS` | `THROTTLE_POS` | Gauge |
| `lemons/ENGINE_LOAD` | `ENGINE_LOAD` | Gauge |
| `lemons/gps/latitude` | `gps.latitude` | Map |
| `lemons/gps/longitude` | `gps.longitude` | Map |
| `lemons/gps/speed` | `gps.speed` | Map overlay |
| `lemons/DTC/*` | `dtc.*` | StatusBar |

## Future Playback Considerations

The architecture separates data consumption (`useMqtt`) from state management (`useTelemetry`). For playback:

- A `usePlayback` hook queries PostgreSQL via a REST API and feeds the same `useTelemetry` store
- Components don't need to know if data is live or replayed
- Bottom bar placeholder becomes a timeline scrubber
- `server.py` gains a REST endpoint to serve historical data

## Dependencies

- `react`, `react-dom`
- `mqtt` (MQTT.js)
- `react-leaflet`, `leaflet`
- Gauge rendering: SVG-based custom component or `react-gauge-component`
- `vite` (build/dev)
