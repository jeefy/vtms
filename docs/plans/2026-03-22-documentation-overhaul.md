# Documentation Overhaul Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace stale/placeholder READMEs and create missing ones so every VTMS monorepo component has accurate, onboarding-quality documentation.

**Architecture:** Top-level README serves as monorepo map. Each component README covers purpose, setup, usage, and relation to the system. Historical design docs in `docs/plans/` are untouched.

**Audience:** Personal use + onboarding a second developer/operator.

---

## Task 1: Rewrite top-level `README.md`

**Files:**
- Modify: `README.md`

**Content outline:**
- Project name + one-line description (racing team vehicle telemetry system)
- System architecture diagram (text): car-pi ↔ MQTT ↔ base-pi, ESP32 sensors, web dashboard
- Component table: name, language, purpose, one-liner
- Prerequisites (pnpm, uv, Docker, make)
- Quick start: `make node-install`, `make client-install`, dev commands
- Docker build: `make image-client image-web image-sdr image-ota`
- Deployment overview pointing to `deploy/README.md`
- Links to each component README
- Link to `docs/plans/` for historical design docs

**Verification:** Read the file after writing and confirm it covers all components and has no broken links to directories.

---

## Task 2: Create `client/README.md`

**Files:**
- Create: `client/README.md`

**Content outline:**
- Purpose: OBD-II + GPS edge client publishing telemetry to MQTT
- Architecture: main loop → OBD service + GPS service → MQTT transport
- Key MQTT topics published (`lemons/RPM`, `lemons/gps/*`, `lemons/DTC/*`, etc.)
- Prerequisites (uv, Python 3.10+)
- Install/run/test/lint commands (all via `make` or `uv`)
- Configuration: `config.py` defaults, MQTT broker address, env vars for Postgres
- Docker: `make image-client`, runs on car-pi
- Hardware notes: runs on Raspberry Pi, optional LED GPIO support

**Verification:** Confirm `make client-test` command reference is accurate by checking Makefile.

---

## Task 3: Create `server/README.md`

**Files:**
- Create: `server/README.md`

**Content outline:**
- Purpose: Node/Express backend for dashboard config persistence + GoPro proxy/stream relay
- API routes: `/api/config` GET/POST, `/api/gopro/*` proxy, WebSocket stream relay
- Prerequisites (pnpm, ffmpeg for streaming)
- Install/build/dev/start commands
- Environment variables: `PORT`, `HOST`, `STREAM_WS_PORT`, `GOPRO_IP`
- Data persistence: `server/data/config.json`
- Deployment: combined with `web` in `Dockerfile.web`

**Verification:** Cross-check env var defaults against `server/src/index.ts` and `server/src/config-store.ts`.

---

## Task 4: Rewrite `web/README.md`

**Files:**
- Modify: `web/README.md`

**Content outline:**
- Purpose: React/Vite live telemetry dashboard (gauges, map, GoPro, settings)
- Features list: radial gauges, Leaflet GPS trail, DTC alerts, GoPro control/preview, config editor
- Prerequisites (pnpm)
- Dev/build/lint commands
- Environment variables: `VITE_MQTT_URL`, `VITE_GOPRO_API_URL`, `VITE_GOPRO_STREAM_URL`
- E2E tests: `pnpm --filter web test:e2e` (Playwright + Aedes mock broker)
- Mock data: `pnpm --filter web mock-data`
- Architecture: hooks (`useMqtt`, `useTelemetry`, `useConfig`, `useGoPro`) → components
- Deployment: built into `Dockerfile.web` and served by `server`

**Verification:** Confirm script names match `web/package.json`.

---

## Task 5: Rewrite `arduino/README.md`

**Files:**
- Modify: `arduino/README.md`

**Content outline:**
- Purpose: ESP32 firmware for sensor peripherals (MicroPython) + CAN gauge cluster (Arduino/C++)
- Device table: analog_sensors, thermoprobe, temp_sensor, led_controller, canbus_gauge
- Shared modules: `common/boot.py` (WiFi + OTA), `common/mqtt_client.py`, `common/ota_update.py`
- Flash workflow: `make flash-micropython` (one-time), `make flash-<device>` per device
- OTA updates: devices check at boot when on `vtms` hotspot, served by `ota` container
- Testing: `make esp32-test` (host-side pytest)
- Links to device-specific READMEs (`analog_sensors/README.md`, `canbus_gauge/README.md`)

**Verification:** Confirm Makefile flash targets exist.

---

## Task 6: Update `arduino/analog_sensors/README.md`

**Files:**
- Modify: `arduino/analog_sensors/README.md`

**Content outline — changes only:**
- Update file table: add `common/boot.py`, `common/mqtt_client.py`, `common/ota_update.py` as shared modules (remove old local `boot.py` and `mqtt_client.py` references if they now come from common)
- Add OTA update section: explain boot-time OTA check, `_ota_hash`/`_boot_count` marker files
- Update monitor command to `make monitor-analog` (confirm target name)
- Keep hardware wiring, calibration, and MQTT topics sections as-is (they are accurate)

**Verification:** Check that `common/boot.py` is the actual boot file used (not a local `boot.py` in analog_sensors).

---

## Task 7: Create `ota/README.md`

**Files:**
- Create: `ota/README.md`

**Content outline:**
- Purpose: HTTP OTA server for ESP32 MicroPython firmware + MQTT hash announcements
- How it works: builds per-device manifests from `arduino/` firmware files, serves via HTTP, publishes hashes to MQTT
- HTTP endpoints: `/health`, `/manifest/<device>`, `/files/<device>/<file>`
- MQTT topics: `vtms/ota/<device>/notify` (retained)
- Configuration: env vars `FIRMWARE_DIR`, `MQTT_BROKER`, `MQTT_PORT`, `HTTP_PORT`, `ANNOUNCE_INTERVAL`
- Docker: `make image-ota`, `Dockerfile.ota` bundles firmware from `arduino/`
- Testing: `make ota-test`
- Deployment: runs on car-pi stack

**Verification:** Cross-check endpoints against `ota/server.py`.

---

## Task 8: Create `deploy/README.md`

**Files:**
- Create: `deploy/README.md`

**Content outline:**
- Purpose: Ansible playbooks + Docker Compose for two-Pi deployment
- Architecture: car-pi (telemetry client + OTA + WiFi hotspot) and base-pi (web dashboard + SDR + kiosk)
- Prerequisites: Ansible, SSH access to Pis, Tailscale auth key
- Provisioning: `ansible-playbook deploy/playbooks/site.yml`
- What each role does: common (Docker, Tailscale, Cockpit), car_pi (hotspot, NAT, compose), base_pi (kiosk, compose)
- Docker Compose files: `docker-compose.car-pi.yml`, `docker-compose.base-pi.yml`
- Image registry: local `192.168.50.46:5000`, push via `make deploy-push`
- Network topology: car-pi hotspot `vtms` (10.42.0.0/24), MQTT broker at `192.168.50.24:1883`

**Verification:** Confirm playbook paths and inventory structure match `deploy/` contents.

---

## Task 9: Update `client/tests/README.md`

**Files:**
- Modify: `client/tests/README.md`

**Content outline — changes only:**
- Replace `pip install -r requirements-dev.txt` with `uv sync` or `make client-install`
- Replace `python run_tests.py` with `make client-test` or `uv run pytest tests/ -v`
- Replace `pytest tests/ --cov=src --cov=client` with `uv run pytest tests/ --cov -v`
- Remove references to `requirements-dev.txt` and `run_tests.py`
- Keep test structure descriptions, mock object docs, and best practices as-is

**Verification:** Confirm `run_tests.py` no longer exists. Confirm `uv run pytest` is the correct test command from `client/pyproject.toml`.

---

## Task 10: Light update to `sdr/README.md`

**Files:**
- Modify: `sdr/README.md`

**Content outline — changes only:**
- Update installation section: replace standalone `git clone` + `pip install` with monorepo context (`make sdr-install` or `uv sync` from `sdr/`)
- Add note that this is part of the VTMS monorepo (not a standalone repo)
- Update development section to reference `make sdr-test` and `make sdr-lint`
- Keep all command documentation, architecture, and preset sections as-is (they are thorough and accurate)

**Verification:** Confirm `make sdr-install`, `make sdr-test`, `make sdr-lint` targets exist in root Makefile.

---

## Execution Order

Tasks 1-10 are independent and can be executed in any order. Recommended batches:

- **Batch 1:** Tasks 1, 2, 3 (top-level + core services)
- **Batch 2:** Tasks 4, 5, 6 (web + arduino)
- **Batch 3:** Tasks 7, 8, 9, 10 (ota + deploy + updates)
