# ESP32 MicroPython Firmware Hardening

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix bugs and harden all four ESP32 MicroPython device firmwares based on code review findings.

**Architecture:** Fix common library bugs first (mqtt_client, ota_update, boot), then consolidate configuration, deduplicate shared code, and harden main loops. Each task includes test updates.

**Tech Stack:** MicroPython (ESP32), CPython pytest (host tests), Makefile (flash targets)

---

### Task 1: Fix OTA response socket leaks

**Files:**
- Modify: `arduino/common/ota_update.py:162-195`
- Modify: `arduino/common/tests/test_ota_update.py`

**What:** `fetch_manifest()` and `download_file()` leak the HTTP response socket if `json.loads()` or `resp.text` raises. On MicroPython, this exhausts the lwIP socket pool (~4 sockets).

**Step 1:** Fix `fetch_manifest()` — wrap in try/finally so `resp.close()` always runs:

```python
def fetch_manifest(ota_server, device_type):
    url = "http://{}/manifest/{}".format(ota_server, device_type)
    try:
        resp = requests.get(url)
        try:
            if resp.status_code == 200:
                return json.loads(resp.text)
            return None
        finally:
            resp.close()
    except Exception as e:
        print("OTA: manifest fetch failed:", e)
    return None
```

**Step 2:** Fix `download_file()` the same way:

```python
def download_file(ota_server, device_type, filename):
    url = "http://{}/files/{}/{}".format(ota_server, device_type, filename)
    try:
        resp = requests.get(url)
        try:
            if resp.status_code == 200:
                return resp.text
            return None
        finally:
            resp.close()
    except Exception as e:
        print("OTA: download failed for {}: {}".format(filename, e))
    return None
```

**Step 3:** Add test for socket cleanup on JSON parse failure:

```python
def test_manifest_json_error_closes_response(self):
    from ota_update import fetch_manifest
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "not json"
    with patch("ota_update.requests") as mock_req:
        mock_req.get.return_value = mock_resp
        result = fetch_manifest("server", "device")
    assert result is None
    mock_resp.close.assert_called_once()
```

**Step 4:** Run tests: `cd arduino/common && python -m pytest tests/ -v`

---

### Task 2: Fix OTA backup read_file strip and add text-mode docstring

**Files:**
- Modify: `arduino/common/ota_update.py:32-44`
- Modify: `arduino/common/tests/test_ota_update.py`

**What:** `read_file()` calls `.strip()` which mutates backup content. `download_file()` uses text mode which would corrupt `.mpy` binaries.

**Step 1:** Split `read_file` into two functions — keep `.strip()` for metadata files (hash, boot count), add `read_file_raw` for backups:

```python
def read_file(path):
    """Read and strip a file's contents. For metadata files (hash, count)."""
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except OSError:
        return ""


def read_file_raw(path):
    """Read a file's exact contents. For backup/restore (preserves whitespace)."""
    try:
        with open(path, "r") as f:
            return f.read()
    except OSError:
        return ""
```

**Step 2:** Update `backup_files()` and `restore_backup()` to use `read_file_raw()`.

**Step 3:** Add docstring to `download_file` noting text-mode only limitation.

**Step 4:** Update existing strip test, add raw read test:

```python
def test_read_raw_preserves_whitespace(self):
    from ota_update import write_file, read_file_raw
    write_file("test.txt", "  hello  \n")
    assert read_file_raw("test.txt") == "  hello  \n"
```

**Step 5:** Run tests: `cd arduino/common && python -m pytest tests/ -v`

---

### Task 3: Harden mqtt_client.py (None guard, keepalive, subscribe docstring)

**Files:**
- Modify: `arduino/common/mqtt_client.py`
- Create: `arduino/common/tests/test_mqtt_client.py`

**What:** Three issues: (1) `MQTTClient=None` gives confusing TypeError, (2) no keepalive means no half-open TCP detection, (3) `subscribe()` API hides single-callback limitation.

**Step 1:** Add guard in `connect()`:

```python
def connect():
    if MQTTClient is None:
        raise RuntimeError("umqtt.robust not installed — flash micropython-umqtt.robust")
    client_id = _client_id()
    client = MQTTClient(client_id, MQTT_BROKER, port=MQTT_PORT, keepalive=60)
    ...
```

**Step 2:** Add docstring warning to `subscribe()`:

```python
def subscribe(client, topic, callback):
    """Subscribe to an MQTT topic with a message callback.

    WARNING: umqtt supports only one global callback. Calling subscribe()
    again with a different callback replaces the previous one.
    callback signature: callback(topic_bytes, msg_bytes)
    """
```

**Step 3:** Write tests (mock umqtt since it's not available on host):

```python
class TestMqttConnect:
    def test_raises_when_umqtt_missing(self):
        import mqtt_client
        orig = mqtt_client.MQTTClient
        mqtt_client.MQTTClient = None
        try:
            with pytest.raises(RuntimeError, match="umqtt.robust not installed"):
                mqtt_client.connect()
        finally:
            mqtt_client.MQTTClient = orig
```

**Step 4:** Run tests: `cd arduino/common && python -m pytest tests/ -v`

---

### Task 4: Configuration DRY — MQTT_BROKER and OTA_SERVER from .env

**Files:**
- Modify: `.env.example`
- Modify: `Makefile:131-141`
- Modify: `arduino/analog_sensors/config.py`
- Modify: `arduino/led_controller/config.py`
- Modify: `arduino/temp_sensor/config.py`
- Modify: `arduino/thermoprobe/config.py`
- Modify: `arduino/common/mqtt_client.py:12`

**What:** MQTT_BROKER (`192.168.50.24`) and OTA_SERVER (`10.42.0.1:8266`) are hardcoded identically in all 4 config files. Move them to `.env` and generate into `secrets.py`.

**Step 1:** Add to `.env.example`:

```
# MQTT broker (all ESP32 devices connect to this)
MQTT_BROKER=192.168.50.24
MQTT_PORT=1883

# OTA server (car-pi hotspot)
OTA_SERVER=10.42.0.1:8266
```

**Step 2:** Update `generate-secrets` in Makefile to include MQTT_BROKER, MQTT_PORT, OTA_SERVER in `secrets.py`.

**Step 3:** Update all 4 `config.py` to import MQTT_BROKER, MQTT_PORT, OTA_SERVER from secrets (with fallback defaults).

**Step 4:** Run tests: `make esp32-test`

---

### Task 5: Deduplicate adc_to_voltage into common

**Files:**
- Create: `arduino/common/adc_utils.py`
- Modify: `arduino/analog_sensors/sensors.py`
- Modify: `arduino/temp_sensor/sensors.py`
- Modify: `arduino/analog_sensors/tests/test_sensors.py`
- Modify: `arduino/temp_sensor/tests/test_temp_sensor.py`
- Modify: `Makefile` (flash targets to include adc_utils.py)

**What:** `adc_to_voltage` is duplicated between analog_sensors and temp_sensor with slightly different implementations. Extract to common with `v_ref` parameter.

**Step 1:** Create `arduino/common/adc_utils.py`:

```python
"""ADC conversion utilities shared across ESP32 sensor devices.

Pure math — no hardware dependencies.
"""


def adc_to_voltage(raw, bits=12, v_ref=3.3):
    """Convert raw ADC count to voltage.

    ESP32 ADC is 12-bit (0-4095) with 11dB attenuation for ~0-3.3V range.
    """
    max_count = (1 << bits) - 1
    if max_count == 0:
        return 0.0
    return raw / max_count * v_ref
```

**Step 2:** Update `analog_sensors/sensors.py` to import from `adc_utils` and remove local implementation.

**Step 3:** Update `temp_sensor/sensors.py` to import from `adc_utils`, removing `config` import.

**Step 4:** Update flash targets in Makefile to copy `adc_utils.py` to devices that need it.

**Step 5:** Update tests to verify import works correctly.

**Step 6:** Run tests: `make esp32-test`

---

### Task 6: Harden main loop error handlers + add WDT

**Files:**
- Modify: `arduino/analog_sensors/main.py`
- Modify: `arduino/temp_sensor/main.py`
- Modify: `arduino/thermoprobe/main.py`
- Modify: `arduino/led_controller/main.py`

**What:** All 4 devices have the same bug: `OSError` handler keeps stale MQTT client with no backoff. Also none enable the hardware watchdog.

**Step 1:** Fix OSError handler in all 4 `main.py` — set `mqtt = None`, add backoff, skip loop body if `mqtt is None`:

```python
except OSError as e:
    print("Error:", e)
    mqtt = None
    time.sleep(5)
    try:
        mqtt = mqtt_client.connect()
    except Exception:
        print("MQTT reconnect failed, will retry next loop")
```

**Step 2:** Add WDT to each `main()` function:

```python
try:
    from machine import WDT
    wdt = WDT(timeout=30000)
except (ImportError, Exception):
    wdt = None

# in loop:
if wdt:
    wdt.feed()
```

**Step 3:** Add `mqtt is None` check at top of loop to retry connect before doing work.

**Step 4:** Run tests: `make esp32-test`

---

### Task 7: boot.py WiFi disconnect before connect + comment

**Files:**
- Modify: `arduino/common/boot.py`

**What:** WiFi `connect()` while previous attempt is in progress can cause radio state issues. Add `disconnect()` before trying each SSID. Add comment explaining module-level execution.

**Step 1:** Add `wlan.disconnect()` + brief sleep before each `wlan.connect()`.

**Step 2:** Add comment on line 80 explaining module-level execution is intentional and module cache prevents re-execution.

**Step 3:** Run tests: `make esp32-test`

---

### Task 8: LED controller + analog sensor improvements

**Files:**
- Modify: `arduino/led_controller/config.py:26`
- Modify: `arduino/led_controller/led_logic.py:9-18`
- Modify: `arduino/led_controller/tests/test_led_controller.py`
- Modify: `arduino/analog_sensors/config.py:46`

**What:** LED controller subscribes to `lemons/#` but only uses 4 topics (unnecessary traffic). `parse_led_value` is overly strict. Debug mode left on by default.

**Step 1:** Change subscription to specific topics. Since mqtt_client.subscribe() only supports one topic, subscribe to the 4 topics individually in main.py, or use a narrower wildcard like `lemons/flag/#` + individual `lemons/pit` and `lemons/box`.

**Step 2:** Broaden `parse_led_value` to accept case-insensitive values + `1`/`0`/`on`/`off`.

**Step 3:** Update tests for broadened parsing (keep existing tests passing, add new ones).

**Step 4:** Set `DEBUG = False` in `analog_sensors/config.py`.

**Step 5:** Run tests: `make esp32-test`

---

## Execution Order

Tasks 1-3 are independent common library fixes (can be parallelized).
Task 4 depends on no other task.
Task 5 depends on no other task.
Task 6 depends on Task 3 (mqtt_client changes).
Task 7 is independent.
Task 8 is independent.

Recommended sequential order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8, with tests after each.
