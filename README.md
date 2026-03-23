# VTMS -- Vehicle Telemetry Monitoring System

Monorepo for a 24 Hours of Lemons race car telemetry stack: OBD-II + GPS + analog sensors streamed over MQTT to a live dashboard.

## Architecture

```
                           ┌─────────────────────────────────────────────┐
                           │  car-pi  (WiFi hotspot "vtms")              │
                           │                                             │
                           │  ┌──────────┐  ┌──────────┐                │
                           │  │  client   │  │   ota    │                │
                           │  │ OBD+GPS   │  │ HTTP OTA │                │
                           │  └────┬──────┘  └────┬─────┘                │
                           │       │ publish       │ serve firmware       │
                           └───────┼───────────────┼─────────────────────┘
                                   │               │
       ┌───────────────┐    MQTT   │         WiFi  │    ┌───────────────┐
       │  ESP32 devices │◄─────────┼───────────────┼───►│  ESP32 devices │
       │ (analog, temp, │──publish──┐              │    │ (thermo, LED,  │
       │  CAN gauge)    │          │               │    │  CAN gauge)    │
       └───────────────┘           │               │    └───────────────┘
                                   ▼               │
                           ┌───────────────────────┼─────────────────────┐
                           │  MQTT Broker  192.168.50.24:1883            │
                           └───────────────────────┬─────────────────────┘
                                                   │
                           ┌───────────────────────┼─────────────────────┐
                           │  base-pi  (kiosk display)                   │
                           │                       │                     │
                           │  ┌──────────┐  ┌──────┴──┐  ┌───────────┐  │
                           │  │   web    │  │  server  │  │    sdr    │  │
                           │  │ React UI │◄─┤ Express  │  │ RTL-SDR   │  │
                           │  │ dashboard│  │ API      │  │ recorder  │  │
                           │  └──────────┘  └─────────┘  └───────────┘  │
                           │                                             │
                           │  ┌──────────┐                               │
                           │  │  ingest  │  MQTT ─► PostgreSQL           │
                           │  └──────────┘                               │
                           └─────────────────────────────────────────────┘
```

## Components

| Directory | Language | Purpose |
|-----------|----------|---------|
| `client/` | Python | OBD-II + GPS edge client; publishes telemetry to MQTT. Runs on car-pi. |
| `ingest/` | Python | MQTT to PostgreSQL ingestion service |
| `server/` | TypeScript/Node | Express API for dashboard config + GoPro proxy/stream relay |
| `web/` | TypeScript/React | Live telemetry dashboard (gauges, map, GoPro feed, settings) |
| `sdr/` | Python | RTL-SDR radio recorder, scanner, and transcriber |
| `arduino/` | MicroPython/C++ | ESP32 sensor firmware (analog sensors, thermoprobe, temp sensor, LED controller, CAN gauge) |
| `ota/` | Python | HTTP OTA server for ESP32 firmware + MQTT hash announcements |
| `deploy/` | Ansible/YAML | Ansible playbooks + Docker Compose for two-Pi deployment |

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 18+
- [pnpm](https://pnpm.io/)
- Docker (with `buildx` for ARM64 cross-builds)
- GNU Make

## Quick Start

Install all dependencies:

```sh
# Python components
make client-install
make ingest-install
make sdr-install

# Node components (server + web via pnpm workspaces)
make node-install
```

Run in development:

```sh
make client-run       # start OBD-II/GPS client
make ingest-run       # start MQTT-to-Postgres ingester
make server-dev       # start Express API (hot reload)
make web-dev          # start React dashboard (hot reload)
make sdr-run          # show SDR CLI help
```

Run tests and linting:

```sh
make test             # all tests (client, sdr, esp32, ota)
make lint             # ruff check (client, sdr)
make ci               # full CI suite (lint + test + build)
```

## ESP32 Firmware

Flash MicroPython devices over USB:

```sh
make flash-analog-sensors
make flash-thermoprobe
make flash-temp-sensor
make flash-led-controller
make monitor-esp32        # open REPL
```

Run `make flash-micropython` to see instructions for initial MicroPython firmware install.

## Docker Images

All images build for `linux/arm64` (Raspberry Pi). Override the registry with `REGISTRY=...`:

```sh
make image-client     # client/Dockerfile
make image-web        # Dockerfile.web (server + web combined)
make image-sdr        # sdr/Dockerfile
make image-ota        # Dockerfile.ota

make deploy-push      # build and push all images to registry
```

## Deployment

Two-Pi deployment is managed by Ansible playbooks and Docker Compose files in `deploy/`:

- `deploy/docker-compose.car-pi.yml` -- client + OTA server
- `deploy/docker-compose.base-pi.yml` -- web/server + SDR + ingest

See [`deploy/`](deploy/) for inventory, playbooks, and role details.

## Component READMEs

- [client/](client/README.md)
- [server/](server/README.md)
- [web/](web/README.md)
- [sdr/](sdr/README.md)
- [arduino/](arduino/README.md) -- [analog_sensors](arduino/analog_sensors/README.md), [canbus_gauge](arduino/canbus_gauge/README.md)
- [ota/](ota/README.md)
- [deploy/](deploy/README.md)
- [client/tests/](client/tests/README.md)

## Design Documents

Historical design docs and plans live in [`docs/plans/`](docs/plans/).

## License

See [LICENSE](LICENSE).
