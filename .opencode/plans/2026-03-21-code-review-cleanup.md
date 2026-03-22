# VTMS Code Review Cleanup & Optimization Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Address technical debt, eliminate code duplication, decompose monolithic modules, add test coverage, and harden the build/deploy pipeline across the VTMS codebase.

**Architecture:** The refactor decomposes `client.py` into focused service modules, unifies config management with server as single source of truth, adds test coverage to the untested Node server and React frontend, and extracts shared Arduino networking code. Each task is independent after Task 1–2 are complete (lint + config modernization are prerequisites).

**Tech Stack:** Python 3.13 (pytest, dataclasses), TypeScript (Express, Vitest, React, Playwright), Arduino/C++ (PlatformIO-style headers), Docker, Make

---

## Task 1: Lint Cleanup (Quick Wins)

**Files:**
- Modify: `client.py:9` — remove unused `sys` import
- Modify: `server.py:3` — remove unused `time` import
- Modify: `src/led.py:2` — remove unused `sleep` import
- Modify: `src/mqtt_handlers.py:6` — remove unused `Any` import
- Modify: `tests/conftest.py:5,7` — remove unused `MagicMock`, `mqtt` imports
- Modify: `tests/test_client.py:6,9,11,12,13,19` — remove unused imports/vars
- Modify: `tests/test_config.py:8` — remove unused `io` import
- Modify: `tests/test_diagram.py:2` — remove unused `os` import
- Modify: `tests/test_integration.py:8,160` — remove unused `MagicMock`, `threading`
- Modify: `web/e2e/global-setup.ts:11,12,14` — remove unused imports

**Step 1: Remove all unused imports listed above**

Each file: delete the unused import line or remove the unused name from the import statement.

**Step 2: Run Python linter to verify**

Run: `make lint`
Expected: No unused import warnings

**Step 3: Run Python tests to verify no breakage**

Run: `make test`
Expected: All tests pass

**Step 4: Run TypeScript build to verify**

Run: `cd web && npm run build && cd ../server && npm run build`
Expected: No errors

**Step 5: Commit**

```bash
git add -A && git commit -m "chore: remove unused imports across Python and TypeScript"
```

---

## Task 2: Python Config Modernization

**Files:**
- Modify: `src/config.py` (full rewrite from 142-line class to ~40-line dataclass)
- Modify: `tests/test_config.py` (update to match new config shape)

**Step 1: Write failing test for new config behavior**

Add test that verifies:
- Config reads from environment variables
- Config raises `EnvironmentError` when required `POSTGRES_USER`/`POSTGRES_PASSWORD` are missing
- `is_raspberrypi()` still works as staticmethod
- All properties are accessible as attributes

```python
# tests/test_config.py - add these tests
def test_config_requires_postgres_user(monkeypatch):
    monkeypatch.delenv("POSTGRES_USER", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    with pytest.raises(EnvironmentError):
        Config()

def test_config_reads_env_vars(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test_pass")
    c = Config()
    assert c.postgres_user == "test_user"
    assert c.postgres_password == "test_pass"
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: New tests FAIL (current Config uses default fallbacks, not EnvironmentError)

**Step 3: Rewrite Config as dataclass**

Replace the 142-line `Config` class with:

```python
import os
from dataclasses import dataclass, field
from typing import Optional
import io

@dataclass
class Config:
    debug: bool = False
    mqtt_server: str = "192.168.50.24"
    mqtt_port: int = 1883
    mqtt_keepalive: int = 60
    obd_retry_delay: int = 15
    gps_update_interval: int = 1
    gps_port: Optional[str] = None
    gps_baudrate: int = 9600
    gps_enabled: bool = True
    postgres_host: str = "my-release-postgresql.monitoring.svc.cluster.local"
    postgres_port: int = 5432
    postgres_database: str = "vtms"
    postgres_user: str = field(default_factory=lambda: os.environ.get("POSTGRES_USER", ""))
    postgres_password: str = field(default_factory=lambda: os.environ.get("POSTGRES_PASSWORD", ""))

    def __post_init__(self):
        if not self.postgres_user:
            raise EnvironmentError("POSTGRES_USER environment variable is required")
        if not self.postgres_password:
            raise EnvironmentError("POSTGRES_PASSWORD environment variable is required")

    @staticmethod
    def is_raspberrypi() -> bool:
        try:
            with io.open("/sys/firmware/devicetree/base/model", "r") as m:
                if "raspberry pi" in m.read().lower():
                    return True
        except Exception:
            pass
        return False

config = Config()
```

**Step 4: Update existing tests to set env vars**

All tests that create `Config()` instances need `POSTGRES_USER` and `POSTGRES_PASSWORD` env vars set. Use `monkeypatch.setenv()` or set them in `conftest.py`.

**Step 5: Run all tests**

Run: `make test`
Expected: All tests pass

**Step 6: Commit**

```bash
git add src/config.py tests/test_config.py tests/conftest.py
git commit -m "refactor: convert Config to dataclass, require postgres credentials via env"
```

---

## Task 3: client.py Decomposition

**Files:**
- Create: `src/gps_service.py` (~130 lines, extracted from client.py:125-351)
- Create: `src/mqtt_transport.py` (~160 lines, extracted from client.py:101-124, 353-504, 715-757)
- Create: `src/obd_service.py` (~100 lines, extracted from client.py:505-597, 677-714)
- Modify: `client.py` (reduce from 834 to ~150 lines — orchestration only)
- Modify: `src/myobd.py:107,117,131` (accept a `publish` callable instead of `mqttc` object)
- Remove: `MQTTWrapper` class (client.py:816-825) — replaced by `MQTTTransport.publish` method
- Create: `tests/test_gps_service.py`
- Create: `tests/test_mqtt_transport.py`
- Create: `tests/test_obd_service.py`

### Step 1: Create `src/mqtt_transport.py`

Extract MQTT client setup, connect/disconnect callbacks, message publishing, buffering, flushing, and connection monitoring into a standalone class `MQTTTransport`:

```python
class MQTTTransport:
    def __init__(self, config, on_message_callback=None):
        self.config = config
        self.on_message_callback = on_message_callback
        self.mqttc = None
        self.connected = False
        self.message_buffer = deque(maxlen=1000)
        # ... (move all buffer/retry state here)

    def connect(self) -> bool: ...
    def start(self): self.mqttc.loop_start()
    def stop(self): ...
    def publish(self, topic, payload, qos=0, retain=False) -> bool: ...
    # ... all _on_connect, _on_disconnect, _on_publish, _on_message callbacks
    # ... _buffer_message, _flush_message_buffer
    # ... connection_monitor (async)
```

**BUG FIX:** In the current `_mqtt_connection_monitor` (client.py:736), `self.setup_mqtt()` creates a new MQTT client but never calls `loop_start()`. Fix this in the new `MQTTTransport.reconnect()` method by calling `self.mqttc.loop_start()` after successful reconnection.

### Step 2: Create `src/gps_service.py`

Extract GPS port discovery, serial connection, NMEA parsing, and GPS data publishing:

```python
class GPSService:
    def __init__(self, config, publisher: Callable[[str, str], None]):
        # publisher is mqtt_transport.publish
        ...

    def discover_ports(self) -> list[str]: ...
    async def connect(self) -> bool: ...
    async def monitor(self): ...  # main monitoring loop
```

### Step 3: Create `src/obd_service.py`

Extract OBD connection setup, watch registration, message handling, and monitoring:

```python
class OBDService:
    def __init__(self, config, publisher: Callable[[str, str], None]):
        ...

    async def connect(self) -> bool: ...
    def setup_watches(self): ...
    def handle_message(self, topic: str, payload: str): ...
    async def monitor(self): ...
```

### Step 4: Update `src/myobd.py` to accept a publish callable

Change function signatures from `mqttc` parameter to `publish` callable:

```python
def new_metric(r, publish):   # was: mqttc
    if r.is_null(): return
    publish(f"lemons/{r.command.name}", str(r.value))
```

### Step 5: Simplify client.py to orchestration only

`VTMSClient` becomes a thin coordinator (~150 lines):

```python
class VTMSClient:
    def __init__(self):
        self.mqtt = MQTTTransport(config.config, on_message_callback=self._route_message)
        self.gps = GPSService(config.config, self.mqtt.publish)
        self.obd = OBDService(config.config, self.mqtt.publish)
        self.message_router = MQTTMessageRouter()
        self._setup_message_handlers()

    async def run(self):
        self.mqtt.connect()
        self.mqtt.start()
        tasks = []
        if config.config.gps_enabled:
            tasks.append(asyncio.create_task(self.gps.monitor()))
        tasks.append(asyncio.create_task(self.obd.monitor()))
        tasks.append(asyncio.create_task(self.mqtt.connection_monitor()))
        tasks.append(asyncio.create_task(self._health_check()))
        # ... gather + shutdown
```

### Step 6: Write tests for each new module

- `tests/test_mqtt_transport.py`: test connect, publish, buffering, flush, reconnection (with loop_start fix)
- `tests/test_gps_service.py`: test port discovery, NMEA parsing, publish calls
- `tests/test_obd_service.py`: test watch setup, message handling, reconnection

### Step 7: Run all tests

Run: `make test`
Expected: All pass, including new tests

### Step 8: Commit

```bash
git add src/gps_service.py src/mqtt_transport.py src/obd_service.py client.py src/myobd.py tests/
git commit -m "refactor: decompose client.py into gps_service, mqtt_transport, obd_service modules

Fix MQTT reconnection bug where loop_start() was not called after re-setup."
```

---

## Task 4: Config Deduplication (Server as Source of Truth)

**Files:**
- Modify: `server/src/config-store.ts:109-111` — return deep clone from `getDefaultConfig()`
- Modify: `web/src/config/gauges.ts` — remove `defaultGaugeConfig` array, keep only minimal offline fallback
- Modify: `web/src/hooks/useConfig.ts:5` — rename env var from `VITE_GOPRO_API_URL` to `VITE_API_BASE_URL`
- Modify: `web/src/hooks/useGoPro.ts` — use config's `gopro.apiUrl` instead of separate env var
- Modify: `web/src/types/config.ts` — keep type definitions (these become the canonical contract)

### Step 1: Fix mutable default return in config-store.ts

```typescript
// config-store.ts:109-111
export function getDefaultConfig(): AppConfig {
  return structuredClone(DEFAULT_CONFIG);
}
```

### Step 2: Simplify web/src/config/gauges.ts

Remove the duplicated gauge definitions. Keep only a minimal empty-state fallback:

```typescript
import type { AppConfig } from "../types/config";

// Minimal fallback used only while loading config from server.
// Server is the source of truth for all defaults.
export const fallbackConfig: AppConfig = {
  mqtt: { url: "", topicPrefix: "lemons/" },
  gopro: { apiUrl: "", streamWsUrl: "" },
  gauges: [],
};
```

### Step 3: Fix useConfig.ts env var naming

```typescript
// useConfig.ts:5
const CONFIG_API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:3001";
```

### Step 4: Update useGoPro.ts to use config apiUrl

Modify the hook to accept `apiUrl` from the config object rather than hardcoding.

### Step 5: Update any other references to `defaultAppConfig`/`defaultGaugeConfig`

Search all web sources and E2E tests for references to removed exports and update them.

### Step 6: Run builds + E2E tests

Run: `cd web && npm run build && npm run test:e2e`
Expected: Build succeeds, E2E tests pass

### Step 7: Commit

```bash
git add server/src/config-store.ts web/src/
git commit -m "refactor: make server the single source of truth for config defaults

Remove duplicated gauge config from web client. Fix mutable default return.
Rename VITE_GOPRO_API_URL to VITE_API_BASE_URL."
```

---

## Task 5: Security Fixes (Minimal — LAN Context)

**Files:**
- Modify: `server/src/index.ts:51,66,76` — remove `detail` from error responses
- Modify: `server/src/gopro-proxy.ts:49-55` — validate `id` as numeric
- Modify: `server/src/config-store.ts:113-141` — validate URL schemes in config save

### Step 1: Stop leaking error details

```typescript
// index.ts — all three error responses
// Before: res.status(500).json({ error: "Failed to start stream", detail: String(err) });
// After:
console.error("Failed to start stream:", err);
res.status(500).json({ error: "Failed to start stream" });
```

Apply to all three error responses (lines 51, 66, 76).

### Step 2: Validate GoPro preset id

```typescript
// gopro-proxy.ts:49-55
router.get("/presets/set_group", async (req, res) => {
  const id = req.query.id;
  if (id === undefined || typeof id !== "string" || !/^\d+$/.test(id)) {
    res.status(400).json({ error: "id must be a numeric value" });
    return;
  }
  await proxyGet(`/gopro/camera/presets/set_group?id=${id}`, req, res);
});
```

### Step 3: Add URL scheme validation to config save

Add to `validateConfig()` in `config-store.ts`:

```typescript
if (!/^wss?:\/\//.test(mqtt.url as string)) throw new Error("mqtt.url must use ws:// or wss://");
if (!/^https?:\/\//.test(gopro.apiUrl as string)) throw new Error("gopro.apiUrl must use http:// or https://");
if (!/^wss?:\/\//.test(gopro.streamWsUrl as string)) throw new Error("gopro.streamWsUrl must use ws:// or wss://");
```

### Step 4: Run server build

Run: `cd server && npm run build`
Expected: No errors

### Step 5: Commit

```bash
git add server/src/
git commit -m "fix: stop leaking error details, validate GoPro preset id and config URLs"
```

---

## Task 6: Node Server Tests + Web Unit Tests

**Files:**
- Create: `server/vitest.config.ts`
- Create: `server/src/__tests__/config-store.test.ts`
- Create: `server/src/__tests__/gopro-proxy.test.ts`
- Create: `server/src/__tests__/keep-alive.test.ts`
- Create: `server/src/__tests__/stream-manager.test.ts`
- Modify: `server/package.json` — add vitest + test script
- Create: `web/vitest.config.ts`
- Create: `web/src/hooks/__tests__/useConfig.test.ts`
- Create: `web/src/hooks/__tests__/useTelemetry.test.ts`
- Modify: `web/package.json` — add vitest + @testing-library/react + test script
- Modify: `Makefile` — add `test-server` and `test-web` targets
- Modify: `.github/workflows/ci.yml` — add server test and web unit test jobs

### Step 1: Set up vitest in server/

```bash
cd server && npm install -D vitest
```

Add to `server/package.json` scripts:
```json
"test": "vitest run",
"test:watch": "vitest"
```

Create `server/vitest.config.ts`:
```typescript
import { defineConfig } from "vitest/config";
export default defineConfig({
  test: { globals: true },
});
```

### Step 2: Write config-store tests

Test `loadConfig`, `saveConfig`, `getDefaultConfig`, `validateConfig` with valid/invalid inputs.

### Step 3: Write gopro-proxy tests

Test route parameter validation (`shutter/:action`, `presets/set_group?id=N`, `stream/:action`). Mock `fetch` for GoPro responses.

### Step 4: Write keep-alive tests

Test `start`/`stop`, connected state changes on ping success/failure. Mock `fetch`.

### Step 5: Write stream-manager tests

Test `startStream`/`stopStream` lifecycle. Mock `spawn` and WebSocketServer.

### Step 6: Set up vitest in web/

```bash
cd web && npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

Add to `web/package.json` scripts:
```json
"test": "vitest run",
"test:watch": "vitest"
```

Create `web/vitest.config.ts`:
```typescript
import { defineConfig } from "vitest/config";
export default defineConfig({
  test: { environment: "jsdom", globals: true },
});
```

### Step 7: Write hook unit tests

- `useConfig.test.ts`: test initial load, save, reset, error handling (mock fetch)
- `useTelemetry.test.ts`: test MQTT message parsing and state updates (mock MQTT client)

### Step 8: Add Makefile targets

```makefile
test-server:
	cd server && npm test

test-web:
	cd web && npm test
```

### Step 9: Update CI to run new tests

Add `npm test` step to the server and web CI jobs in `.github/workflows/ci.yml`.

### Step 10: Run all tests

Run: `cd server && npm test && cd ../web && npm test`
Expected: All pass

### Step 11: Commit

```bash
git add server/ web/ Makefile .github/
git commit -m "test: add vitest suite for Node server and React hook unit tests"
```

---

## Task 7: Arduino Shared Library

**Files:**
- Create: `arduino/lib/vtms_config.h.example` — template with placeholder credentials
- Create: `arduino/lib/vtms_net.h` — shared WiFi + MQTT connection code
- Modify: `arduino/led.cpp` — use shared library
- Modify: `arduino/temp.cpp` — use shared library
- Modify: `arduino/thermoprobe.cpp` — use shared library
- Modify: `arduino/wheel.cpp` — use shared library
- Modify: `.gitignore` — add `arduino/lib/vtms_config.h`

### Step 1: Create config header template

```cpp
// arduino/lib/vtms_config.h.example
// Copy to vtms_config.h and fill in your values.
// vtms_config.h is gitignored.
#ifndef VTMS_CONFIG_H
#define VTMS_CONFIG_H

const char* WIFI_SSID = "YOUR_SSID";
const char* WIFI_PASSWORD = "YOUR_PASSWORD";
const char* MQTT_BROKER = "192.168.50.24";
const int   MQTT_PORT = 1883;
const char* MQTT_USERNAME = "";
const char* MQTT_PASSWORD = "";

#endif
```

### Step 2: Create shared networking header

```cpp
// arduino/lib/vtms_net.h
#ifndef VTMS_NET_H
#define VTMS_NET_H

#include <WiFi.h>
#include <PubSubClient.h>
#include "vtms_config.h"

WiFiClient espClient;
PubSubClient mqttClient(espClient);

void vtms_wifi_connect() {
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.println("Connecting to WiFi...");
    }
    Serial.println("Connected to WiFi");
}

void vtms_mqtt_connect(const char* clientPrefix, MQTT_CALLBACK_SIGNATURE) {
    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
    mqttClient.setCallback(callback);
    while (!mqttClient.connected()) {
        String clientId = String(clientPrefix) + "-" + WiFi.macAddress();
        Serial.printf("Connecting MQTT as %s...\n", clientId.c_str());
        if (mqttClient.connect(clientId.c_str(), MQTT_USERNAME, MQTT_PASSWORD)) {
            Serial.println("MQTT connected");
        } else {
            Serial.printf("MQTT failed, state=%d, retrying...\n", mqttClient.state());
            delay(2000);
        }
    }
}

#endif
```

### Step 3: Refactor each Arduino file

Replace duplicated WiFi/MQTT setup code with:
```cpp
#include "lib/vtms_net.h"

void setup() {
    Serial.begin(115200);
    vtms_wifi_connect();
    vtms_mqtt_connect("vtms-led", callback);
    mqttClient.subscribe("lemons/#");
    // ... device-specific setup
}
```

### Step 4: Add vtms_config.h to .gitignore

```
arduino/lib/vtms_config.h
```

### Step 5: Commit

```bash
git add arduino/ .gitignore
git commit -m "refactor: extract shared Arduino WiFi/MQTT library, gitignore credentials"
```

---

## Task 8: Docker & Makefile Cleanup

**Files:**
- Modify: `Dockerfile:3` — clean apt cache, add non-root user
- Modify: `Dockerfile.web:20-44` — add HEALTHCHECK, non-root user
- Modify: `Makefile` — fix `.PHONY`, add `help` target, remove legacy `server-py`, add `dev` target
- Modify: `install.sh:36-41` — remove duplicate `--privileged`

### Step 1: Harden Python Dockerfile

```dockerfile
FROM python:3.13-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

RUN useradd -r -s /bin/false vtms
COPY . /app/
RUN chown -R vtms:vtms /app
USER vtms

ENTRYPOINT ["python3", "-u", "client.py"]
```

### Step 2: Add HEALTHCHECK and non-root user to Dockerfile.web

Add before `CMD`:
```dockerfile
RUN addgroup -S vtms && adduser -S vtms -G vtms
RUN chown -R vtms:vtms /app
USER vtms

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget -q --spider http://localhost:3001/api/health || exit 1
```

### Step 3: Fix install.sh duplicate --privileged

Remove the second `--privileged` flag at line 40.

### Step 4: Clean up Makefile

```makefile
.PHONY: help venv requirements requirements-dev pip-compile lint format \
        test test-cov client \
        server-install server-build server-dev \
        web-install web-build web-dev \
        test-server test-web \
        image image-run image-push image-web image-web-run \
        ci-python ci-node ci

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ... (add ## comments to each target for help output)
```

Remove `server-py` target (legacy Flask reference) or rename to clarify it runs `server.py` ingestion.

### Step 5: Run builds to verify

Run: `docker build -t vtms-test . && docker build -f Dockerfile.web -t vtms-web-test .`
Expected: Both build successfully

### Step 6: Commit

```bash
git add Dockerfile Dockerfile.web Makefile install.sh
git commit -m "chore: harden Dockerfiles (non-root, healthcheck), clean up Makefile"
```

---

## Execution Notes

- **Task 1-2** are prerequisites (lint cleanup and config modernization unblock later refactors)
- **Tasks 3-8** can be done in any order after 1-2, but the recommended order minimizes merge conflicts
- **Task 3** (client.py decomposition) is the highest-risk refactor — run the full test suite after each substep
- **Task 6** (tests) should ideally run after Tasks 3-5 so the new modules are testable
- Each task should be a separate commit (or PR if preferred)
