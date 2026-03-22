# E2E Test Suite Design - VTMS Live Dashboard

**Date:** 2026-03-20
**Status:** Approved

## Problem

The VTMS live dashboard web app has no test infrastructure. We need an e2e test suite that validates the full user experience: MQTT connection, gauge rendering, GPS map updates, DTC alerts, and responsive layout. We also need a reusable mock data generator for development and demos.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Mock MQTT strategy | Real in-process Aedes broker | Most realistic, tests actual MQTT.js client path |
| E2E framework | Playwright | Best auto-waiting, multi-browser, built-in assertions |
| Test scope | Critical user journeys (~10 tests) | Covers all major features without over-testing |
| Mock data | Reusable standalone generator + test helpers | Useful for tests, dev, and demos |

## Architecture

```
Playwright Test Process
├── Aedes MQTT Broker (WebSocket on dynamic port)
│   ├── Test helpers publish specific topics per test
│   └── Mock data generator publishes drive sequences
├── Vite Dev Server (dynamic port, VITE_MQTT_URL set)
│   └── React App connects to Aedes broker
└── Playwright Browser
    └── Navigates to Vite, asserts DOM after MQTT messages
```

### Test Infrastructure

- **Global setup**: Start Aedes broker with WebSocket transport + Vite dev server with correct MQTT URL
- **Global teardown**: Stop both servers
- **Per-test**: MqttTestClient helper publishes targeted messages and waits for delivery

### Test Cases

1. App loads with disconnected/connecting state
2. MQTT connection and status indicator turns green
3. Gauge values update from OBD metrics
4. Gauge value clamping and NaN handling
5. GPS position updates map marker and shows fix indicator
6. GPS trail polyline rendering from position sequence
7. DTC alerts appear in status bar
8. Multiple metrics streaming simultaneously
9. GPS speed and altitude in overlay
10. Responsive layout at mobile viewport

### Mock Data Generator

Standalone script (`web/scripts/mock-data.ts`) that simulates a drive:
- Engine start, idle, acceleration, cruising, deceleration
- GPS follows a coordinate loop
- Configurable publish rate
- Runnable standalone or importable by tests

### File Structure

```
web/
├── e2e/
│   ├── global-setup.ts
│   ├── global-teardown.ts
│   ├── helpers/
│   │   └── mqtt-client.ts
│   ├── dashboard.spec.ts
│   └── fixtures.ts
├── scripts/
│   └── mock-data.ts
├── playwright.config.ts
└── package.json  (+devDeps)
```

### Dependencies (devDependencies)

- `@playwright/test`
- `aedes`
- `websocket-stream`
- `tsx`
