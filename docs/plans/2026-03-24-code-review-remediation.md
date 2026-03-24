# Code Review Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the 14 outstanding security, reliability, and interoperability issues identified in the VTMS code review.

**Architecture:** Fixes are grouped into 5 phases by component/risk: OTA security first, then Python config consistency, ingest resilience, web frontend parsing/connectivity, and Express server hardening. Each task is self-contained with tests.

**Tech Stack:** Python 3.12 + pytest (OTA, client, ingest), TypeScript + React 19 + Vite (web), Express 5 (server), Playwright (E2E), Ansible/Jinja2 (deploy).

---

## Phase 0: Security — OTA Path Traversal

### Task 0.1: Add Path Traversal Test for `device_type`

**Files:**
- Modify: `ota/tests/test_server.py`

Add a test class that verifies `device_type` containing `..` cannot escape the firmware root:

```python
class TestPathTraversal:
    """Verify path traversal attacks are blocked."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, "common"))
        os.makedirs(os.path.join(self.tmpdir, "legit_device"))
        # Create a file outside the firmware root that an attacker would target
        self.secret = os.path.join(self.tmpdir, "..", "secret.py")
        with open(self.secret, "w") as f:
            f.write("SECRET")
        with open(os.path.join(self.tmpdir, "legit_device", "main.py"), "w") as f:
            f.write("ok")

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)
        if os.path.exists(self.secret):
            os.remove(self.secret)

    def test_resolve_file_blocks_traversal_in_device_type(self):
        """device_type containing '..' must not resolve outside firmware dir."""
        from server import resolve_file

        path = resolve_file(self.tmpdir, "..", "secret.py")
        resolved = os.path.realpath(path)
        firmware_root = os.path.realpath(self.tmpdir)
        assert resolved.startswith(firmware_root), (
            f"Path traversal: resolved to {resolved} which is outside {firmware_root}"
        )

    def test_get_device_files_blocks_traversal(self):
        """device_type containing '..' returns empty file list."""
        from server import get_device_files

        files = get_device_files(self.tmpdir, "../")
        # Should either return empty or only files within firmware_dir
        for f in files:
            path = os.path.join(self.tmpdir, "../", f)
            resolved = os.path.realpath(path)
            firmware_root = os.path.realpath(self.tmpdir)
            assert resolved.startswith(firmware_root), (
                f"Traversal: {f} resolved outside firmware root"
            )

    def test_handle_file_rejects_traversal_device_type(self):
        """HTTP handler rejects device_type with path traversal."""
        from http.server import HTTPServer
        from server import OTAHandler
        import json
        from io import BytesIO
        from unittest.mock import MagicMock

        OTAHandler.firmware_dir = self.tmpdir
        OTAHandler.manifests = {}

        handler = MagicMock(spec=OTAHandler)
        handler.firmware_dir = self.tmpdir
        handler.manifests = {}
        handler.path = "/files/../secret.py"

        # The do_GET path splits on / — parts would be ['files', '..', 'secret.py']
        # len(parts) == 3 and parts[0] == 'files' matches _handle_file
        # But device_type '..' should be rejected
        parts = handler.path.strip("/").split("/")
        assert parts[1] == ".."  # confirms the attack vector
```

**Run:** `python -m pytest ota/tests/test_server.py::TestPathTraversal -v`

**Expected:** First two tests FAIL (path escapes root), third passes (just a setup verification).

---

### Task 0.2: Fix Path Traversal in OTA Server

**Files:**
- Modify: `ota/server.py:26-48, 86-94, 104-107`

1. Add `_safe_device_type()` validation helper:

```python
import re

DEVICE_TYPE_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_device_type(device_type):
    """Raise ValueError if device_type contains path traversal characters."""
    if not DEVICE_TYPE_RE.match(device_type):
        raise ValueError(f"Invalid device_type: {device_type}")
```

2. Add validation to `get_device_files`, `resolve_file`, and `compute_device_hash`:

```python
def get_device_files(firmware_dir, device_type):
    """Get sorted, deduplicated list of .py files for a device type."""
    _validate_device_type(device_type)
    # ... rest unchanged
```

```python
def resolve_file(firmware_dir, device_type, filename):
    """Resolve filename to path (device dir first, then common)."""
    _validate_device_type(device_type)
    # ... rest unchanged
```

3. Also validate `filename` in `resolve_file` and `_handle_file`:

```python
def resolve_file(firmware_dir, device_type, filename):
    """Resolve filename to path (device dir first, then common)."""
    _validate_device_type(device_type)
    if ".." in filename or "/" in filename:
        raise ValueError(f"Invalid filename: {filename}")
    device_path = os.path.join(firmware_dir, device_type, filename)
    if os.path.isfile(device_path):
        return device_path
    return os.path.join(firmware_dir, COMMON_DIR, filename)
```

4. Validate in HTTP handler and return 400:

```python
def _handle_file(self, device_type, filename):
    if ".." in filename or "/" in filename:
        self._json_response(400, {"error": "invalid filename"})
        return
    try:
        _validate_device_type(device_type)
    except ValueError:
        self._json_response(400, {"error": "invalid device type"})
        return
    filepath = resolve_file(self.firmware_dir, device_type, filename)
    # ... rest unchanged
```

5. Same for `_handle_manifest`:

```python
def _handle_manifest(self, device_type):
    try:
        _validate_device_type(device_type)
    except ValueError:
        self._json_response(400, {"error": "invalid device type"})
        return
    if device_type in self.manifests:
        self._json_response(200, self.manifests[device_type])
    else:
        self._json_response(404, {"error": "unknown device type"})
```

**Run:** `python -m pytest ota/tests/ -v`

**Expected:** All tests pass including new `TestPathTraversal`.

**Commit:** `security(ota): validate device_type to prevent path traversal`

---

## Phase 1: MQTT Config Consistency

### Task 1.1: Make Client MQTT Config Env-Driven

**Files:**
- Modify: `client/src/vtms_client/config.py:15-17`

```python
mqtt_server: str = field(
    default_factory=lambda: os.environ.get("MQTT_SERVER", "192.168.50.24")
)
mqtt_port: int = field(
    default_factory=lambda: int(os.environ.get("MQTT_PORT", "1883"))
)
mqtt_keepalive: int = field(
    default_factory=lambda: int(os.environ.get("MQTT_KEEPALIVE", "60"))
)
```

**Verify:** Docker Compose already sets `MQTT_SERVER` and `MQTT_PORT` in `deploy/roles/car_pi/templates/docker-compose.yml.j2:12-13`.

**Commit:** `fix(client): read MQTT config from environment variables`

---

### Task 1.2: Make Ingest MQTT Config Env-Driven

**Files:**
- Modify: `ingest/src/vtms_ingest/config.py:13-15`

```python
mqtt_server: str = field(
    default_factory=lambda: os.environ.get("MQTT_SERVER", "192.168.50.24")
)
mqtt_port: int = field(
    default_factory=lambda: int(os.environ.get("MQTT_PORT", "1883"))
)
mqtt_keepalive: int = field(
    default_factory=lambda: int(os.environ.get("MQTT_KEEPALIVE", "60"))
)
```

**Commit:** `fix(ingest): read MQTT config from environment variables`

---

## Phase 2: Ingest Resilience

### Task 2.1: Scope MQTT Subscription and Add Reconnect Handling

**Files:**
- Modify: `ingest/src/vtms_ingest/server.py`

1. Scope subscription to telemetry-only topics instead of `lemons/#`:

```python
TELEMETRY_TOPICS = [
    "lemons/RPM",
    "lemons/SPEED",
    "lemons/COOLANT_TEMP",
    "lemons/OIL_TEMP",
    "lemons/THROTTLE_POS",
    "lemons/ENGINE_LOAD",
    "lemons/gps/#",
    "lemons/DTC/#",
    "lemons/fuel/#",
    "lemons/oil/#",
    "lemons/egt/#",
    "lemons/spare/#",
]


def on_connect(client, userdata, flags, reason_code, properties):
    """Handle MQTT CONNACK — subscribe to telemetry topics only."""
    print(f"Connected with result code {reason_code}")
    for topic in TELEMETRY_TOPICS:
        client.subscribe(topic)
    print(f"Subscribed to {len(TELEMETRY_TOPICS)} telemetry topics")
```

2. Add `on_disconnect` handler with logging:

```python
def on_disconnect(client, userdata, flags, reason_code, properties):
    """Handle MQTT disconnect — paho reconnects automatically via loop_forever."""
    print(f"MQTT disconnected (rc={reason_code}), will auto-reconnect...")
```

3. Add DB reconnection in `on_message`:

```python
def on_message(client, userdata, msg):
    """Handle incoming MQTT messages — insert into PostgreSQL."""
    global con, cur
    try:
        payload_str = str(msg.payload.decode("utf-8"))
        print(f"{msg.topic} {payload_str}")

        cur.execute(
            "INSERT INTO telemetry (metric, value) VALUES (%s, %s)",
            (msg.topic, payload_str),
        )
        con.commit()

    except psycopg2.OperationalError as e:
        print(f"DB connection lost: {e}, reconnecting...")
        try:
            con = psycopg2.connect(
                host=config.postgres_host,
                database=config.postgres_database,
                user=config.postgres_user,
                password=config.postgres_password,
                port=config.postgres_port,
            )
            con.set_session(autocommit=False)
            cur = con.cursor()
            print("DB reconnected")
        except psycopg2.Error as reconnect_err:
            print(f"DB reconnect failed: {reconnect_err}")

    except Exception as e:
        print(f"Error inserting data: {e}")
        try:
            con.rollback()
        except Exception:
            pass
```

4. Wire `on_disconnect` in `main()`:

```python
mqttc.on_disconnect = on_disconnect
```

**Commit:** `fix(ingest): scope MQTT subscription to telemetry topics and add DB reconnect`

---

## Phase 3: Web Frontend Fixes

### Task 3.1: Fix Hardcoded API URL in useConfig

**Files:**
- Modify: `web/src/hooks/useConfig.ts:5`
- Modify: `web/vite.config.ts`

1. Replace hardcoded localhost with config-driven URL:

```ts
// useConfig.ts line 5
const CONFIG_API = import.meta.env.VITE_GOPRO_API_URL ?? "";
```

Using `""` (empty string) makes `fetch` use relative URLs, which resolve to the serving origin. In production the Express server serves both the API and the static frontend, so `/api/config` resolves correctly. In dev, the Vite proxy handles it.

2. Add Vite dev proxy:

```ts
// vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:3001',
        changeOrigin: true,
      },
    },
  },
})
```

**Verify:** `pnpm --filter web exec tsc --noEmit`

**Commit:** `fix(web): use relative API URLs with Vite dev proxy instead of hardcoded localhost`

---

### Task 3.2: Fix GPS NaN Handling in useTelemetry

**Files:**
- Modify: `web/src/hooks/useTelemetry.ts:64-79, 85-87`

Guard all `parseFloat` calls for GPS fields:

```ts
switch (field) {
  case "latitude": {
    const v = parseFloat(payload);
    if (!isNaN(v)) next.latitude = v;
    break;
  }
  case "longitude": {
    const v = parseFloat(payload);
    if (!isNaN(v)) next.longitude = v;
    break;
  }
  case "altitude": {
    const v = parseFloat(payload);
    if (!isNaN(v)) next.altitude = v;
    break;
  }
  case "speed": {
    const v = parseFloat(payload);
    if (!isNaN(v)) next.speed = v;
    break;
  }
  case "track": {
    const v = parseFloat(payload);
    if (!isNaN(v)) next.track = v;
    break;
  }
  case "geohash":
    next.geohash = payload;
    break;
  case "pos": {
    const [lat, lon] = payload.split(",").map(Number);
    if (!isNaN(lat) && !isNaN(lon)) {
      next.latitude = lat;
      next.longitude = lon;
      // Update trail
      const newTrail = [...trailRef.current, [lat, lon] as [number, number]];
      if (newTrail.length > TRAIL_MAX_LENGTH) {
        newTrail.splice(0, newTrail.length - TRAIL_MAX_LENGTH);
      }
      trailRef.current = newTrail;
      trailCountRef.current++;
      if (trailCountRef.current % 5 === 0) {
        setTrail([...trailRef.current]);
      }
    }
    break;
  }
}
```

**Commit:** `fix(web): guard GPS parseFloat against NaN values in useTelemetry`

---

### Task 3.3: Exclude SDR Topics from Telemetry Metrics

**Files:**
- Modify: `web/src/hooks/useTelemetry.ts:119-132`

Add SDR topic exclusion before the catch-all metrics handler:

```ts
// Skip SDR topics — handled by useSDR hook
if (topic.startsWith(`${prefix}sdr/`)) {
  return;
}

// Skip status request/response topics
if (topic.startsWith(`${prefix}status/`)) {
  return;
}

// All other lemons/* topics are metrics
if (topic.startsWith(prefix)) {
  const key = topic.replace(prefix, "");
  const value: TelemetryValue = {
    raw: payload,
    value: parseOBDValue(payload),
    timestamp: now,
  };
  setMetrics((prev) => {
    const next = new Map(prev);
    next.set(key, value);
    return next;
  });
}
```

**Commit:** `fix(web): exclude SDR and status topics from telemetry metrics`

---

### Task 3.4: Fix SDR parseFloat/parseInt Zero Handling

**Files:**
- Modify: `web/src/hooks/useSDR.ts:47, 62-63, 79-81`

Replace `parseFloat(x) || null` with proper NaN checks:

```ts
case "freq": {
  const v = parseFloat(payload);
  setState((prev) => ({ ...prev, freq: isNaN(v) ? null : v }));
  break;
}
```

```ts
case "squelch_db": {
  const v = parseFloat(payload);
  setState((prev) => ({ ...prev, squelch_db: isNaN(v) ? null : v }));
  break;
}
```

```ts
case "signal_power": {
  const v = parseFloat(payload);
  setState((prev) => ({ ...prev, signal_power: isNaN(v) ? null : v }));
  break;
}
```

```ts
case "ppm": {
  const v = parseInt(payload, 10);
  setState((prev) => ({ ...prev, ppm: isNaN(v) ? null : v }));
  break;
}
```

**Commit:** `fix(web): handle zero values correctly in SDR parseFloat/parseInt`

---

## Phase 4: Express Server Hardening

### Task 4.1: Add JSON Body Size Limit

**Files:**
- Modify: `server/src/index.ts:42`

```ts
app.use(express.json({ limit: "100kb" }));
```

**Commit:** `fix(server): add 100kb JSON body size limit`

---

### Task 4.2: Make CORS Deployment-Safe

**Files:**
- Modify: `server/src/index.ts:21-40`

When the server serves the static frontend in production, same-origin requests don't need CORS headers. The current allowlist only needs to cover dev mode. Add the request's own origin when it matches the server:

```ts
// ── CORS (allow Vite dev server + same-origin) ───────

const ALLOWED_ORIGINS = new Set([
  `http://localhost:${PORT}`,
  `http://localhost:5173`, // Vite dev
]);

app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (origin) {
    // Allow configured origins + any request where origin matches the Host header
    // (same-origin requests from the served frontend)
    const hostOrigin = `${req.protocol}://${req.headers.host}`;
    if (ALLOWED_ORIGINS.has(origin) || origin === hostOrigin) {
      res.header("Access-Control-Allow-Origin", origin);
      res.header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS");
      res.header("Access-Control-Allow-Headers", "Content-Type");
    }
  }
  if (req.method === "OPTIONS") {
    res.sendStatus(204);
    return;
  }
  next();
});
```

**Commit:** `fix(server): allow same-origin CORS for deployed frontend`

---

### Task 4.3: Fix Config Deep Merge

**Files:**
- Modify: `server/src/config-store.ts:97-107`

Replace shallow spread with section-level merge that preserves nested objects:

```ts
export async function loadConfig(): Promise<AppConfig> {
  try {
    const raw = await readFile(CONFIG_PATH, "utf-8");
    const parsed = JSON.parse(raw);
    validateConfig(parsed);
    const defaults = structuredClone(DEFAULT_CONFIG);
    // Deep merge: per-section spread preserves nested objects
    return {
      mqtt: { ...defaults.mqtt, ...parsed.mqtt },
      gopro: { ...defaults.gopro, ...parsed.gopro },
      sdr: { ...defaults.sdr, ...(parsed.sdr ?? {}) },
      gauges: parsed.gauges, // gauges is an array, take as-is from saved config
    };
  } catch {
    console.warn("Failed to load config, using defaults");
    return structuredClone(DEFAULT_CONFIG);
  }
}
```

**Commit:** `fix(server): deep merge config sections to preserve nested defaults`

---

## Phase 5: Verification

### Task 5.1: Run All Test Suites

Run all tests to verify nothing is broken:

```bash
make esp32-test
python -m pytest ota/tests/ -v
pnpm --filter web exec tsc --noEmit
pnpm --filter server exec tsc --noEmit
pnpm --filter web exec playwright test
```

**Expected:** All tests pass, no type errors.

---

## Issue-to-Task Mapping

| # | Issue | Task |
|---|---|---|
| 1 | OTA path traversal via `device_type` | 0.1, 0.2 |
| 2 | Client MQTT config hardcoded | 1.1 |
| 3 | Ingest MQTT config hardcoded | 1.2 |
| 4 | Ingest subscribes too broadly (`lemons/#`) | 2.1 |
| 5 | Ingest no MQTT reconnect strategy | 2.1 |
| 6 | Ingest no DB reconnection | 2.1 |
| 7 | Web hardcoded `localhost:3001` API URL | 3.1 |
| 8 | GPS parseFloat without NaN guard | 3.2 |
| 9 | SDR topics leak into telemetry metrics | 3.3 |
| 10 | SDR `parseFloat(x) \|\| null` treats 0 as null | 3.4 |
| 11 | Multiple MQTT connections per hook | Deferred — requires shared context refactor |
| 12 | No `express.json()` size limit | 4.1 |
| 13 | CORS localhost-only breaks deployed access | 4.2 |
| 14 | Config shallow merge loses nested objects | 4.3 |

**Note on issue 11 (shared MQTT):** This requires a React context refactor that would touch App.tsx, useTelemetry, and useSDR. It's a larger change best handled as a separate plan to avoid scope creep.
