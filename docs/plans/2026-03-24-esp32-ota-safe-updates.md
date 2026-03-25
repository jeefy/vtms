# ESP32 OTA Safe Updates Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make ESP32 OTA work from any network (not just hotspot), and replace the dangerous MQTT blind-reboot with safe in-place OTA triggered from the main loop.

**Architecture:** Three changes: (1) switch OTA_SERVER from hotspot IP to car-pi's Tailscale IP so OTA works from any network, (2) remove the `is_on_hotspot()` gate in boot.py so OTA is attempted on every boot regardless of network, (3) replace `machine.reset()` in the MQTT OTA handler with a flag that the main loop checks and acts on safely.

**Tech Stack:** MicroPython, ESP32, MQTT (umqtt.robust), pytest

---

### Task 1: Update OTA_SERVER address to Tailscale IP

**Files:**
- Modify: `.env:26`
- Modify: `.env.example:23`
- Modify: `arduino/analog_sensors/config.py:11`
- Modify: `arduino/led_controller/config.py:11`
- Modify: `arduino/temp_sensor/config.py:11`
- Modify: `arduino/thermoprobe/config.py:11`

**Step 1: Update .env**

Change line 26 from:
```
OTA_SERVER=10.42.0.1:8266
```
to:
```
OTA_SERVER=100.84.179.100:8266
```

**Step 2: Update .env.example**

Change line 23 from:
```
OTA_SERVER=10.42.0.1:8266
```
to:
```
OTA_SERVER=100.84.179.100:8266
```

Update the comment on line 22 from:
```
# OTA server (car-pi hotspot gateway)
```
to:
```
# OTA server (car-pi Tailscale IP)
```

**Step 3: Update fallback defaults in all 4 device config.py files**

In each of `arduino/{analog_sensors,led_controller,temp_sensor,thermoprobe}/config.py`, change the fallback:
```python
OTA_SERVER = "10.42.0.1:8266"
```
to:
```python
OTA_SERVER = "100.84.179.100:8266"
```

**Step 4: Regenerate secrets.py**

Run: `make generate-secrets`
Expected: `arduino/common/secrets.py` now contains `OTA_SERVER = "100.84.179.100:8266"`

**Step 5: Commit**

```bash
git add .env.example arduino/analog_sensors/config.py arduino/led_controller/config.py \
  arduino/temp_sensor/config.py arduino/thermoprobe/config.py
git commit -m "fix: change OTA_SERVER from hotspot IP to car-pi Tailscale IP"
```

Note: `.env` and `arduino/common/secrets.py` are gitignored.

---

### Task 2: Remove `is_on_hotspot()` gate from boot and OTA module

**Files:**
- Modify: `arduino/common/boot.py:45-68`
- Modify: `arduino/common/ota_update.py:272-282`

**Step 1: Update boot.py `_run_ota_check()`**

Remove `is_on_hotspot` from the import and remove the gate. Change:

```python
def _run_ota_check():
    """Run OTA update check and rollback detection."""
    from ota_update import (
        is_on_hotspot,
        check_and_update,
        increment_boot_count,
        needs_rollback,
        perform_rollback,
    )

    count = increment_boot_count()
    print("Boot count:", count)

    if needs_rollback():
        print("OTA: crash loop detected, rolling back...")
        perform_rollback()
        from machine import reset

        reset()

    if not is_on_hotspot():
        print("OTA: not on hotspot, skipping update check")
        return

    result = check_and_update(OTA_SERVER, DEVICE_TYPE)
```

to:

```python
def _run_ota_check():
    """Run OTA update check and rollback detection."""
    from ota_update import (
        check_and_update,
        increment_boot_count,
        needs_rollback,
        perform_rollback,
    )

    count = increment_boot_count()
    print("Boot count:", count)

    if needs_rollback():
        print("OTA: crash loop detected, rolling back...")
        perform_rollback()
        from machine import reset

        reset()

    result = check_and_update(OTA_SERVER, DEVICE_TYPE)
```

**Step 2: Delete `is_on_hotspot()` from ota_update.py**

Remove lines 272-282 entirely (the `is_on_hotspot` function).

**Step 3: Run tests**

Run: `pytest arduino/common/tests/ -v`
Expected: All existing tests pass (no tests reference `is_on_hotspot`).

**Step 4: Commit**

```bash
git add arduino/common/boot.py arduino/common/ota_update.py
git commit -m "fix: remove hotspot gate so OTA works from any network"
```

---

### Task 3: Replace MQTT blind-reboot with flag-based OTA

**Files:**
- Modify: `arduino/common/mqtt_client.py:82-111`
- Modify: `arduino/common/config.py` (test stub)
- Test: `arduino/common/tests/test_mqtt_client.py`

**Step 1: Add `OTA_SERVER` to test config stub**

In `arduino/common/config.py`, add:
```python
OTA_SERVER = "127.0.0.1:8266"
```

**Step 2: Update `_handle_ota_notification` to set flag instead of rebooting**

Add module-level flag after the existing `_cached_client_id = None` line:

```python
_ota_pending = False
```

Replace the `_handle_ota_notification` function:

```python
def _handle_ota_notification(topic, msg):
    """Check OTA hash notification and flag for update if firmware has changed.

    Compares the announced hash against the locally stored hash.
    If they differ (and a local hash exists), sets _ota_pending flag
    so the main loop can safely apply the OTA update.

    Errors are caught and printed — OTA notification should never crash
    the main loop.
    """
    global _ota_pending
    try:
        payload = ujson.loads(msg)
        server_hash = payload.get("hash", "")
        if not server_hash:
            return

        from ota_update import HASH_FILE

        local_hash = ota_update.read_file(HASH_FILE)
        if not local_hash:
            # First boot or no hash file — boot.py already ran OTA check
            return

        if server_hash != local_hash:
            print("OTA: new firmware detected, flagging for update")
            _ota_pending = True
    except Exception as e:
        print("OTA notification error:", e)
```

**Step 3: Add `ota_pending()` and `run_pending_ota()` functions**

Add after `publish_firmware_hash`:

```python
def ota_pending():
    """Check if an OTA update has been flagged by MQTT notification."""
    return _ota_pending


def run_pending_ota():
    """If OTA is pending, attempt the update.

    Returns "updated", "current", "error", or None if no OTA was pending.
    Clears the pending flag regardless of outcome.
    """
    global _ota_pending
    if not _ota_pending:
        return None
    _ota_pending = False
    from config import OTA_SERVER, DEVICE_TYPE

    print("OTA: running pending update check")
    return ota_update.check_and_update(OTA_SERVER, DEVICE_TYPE)
```

**Step 4: Update existing OTA notification tests**

Rename `TestOtaNotificationReboot` to `TestOtaNotificationFlag` and update tests:

```python
class TestOtaNotificationFlag:
    """Test _handle_ota_notification sets flag on hash mismatch."""

    def setup_method(self):
        import mqtt_client
        mqtt_client._ota_pending = False

    def teardown_method(self):
        import mqtt_client
        mqtt_client._ota_pending = False

    def test_sets_flag_when_hash_differs(self):
        """OTA notification with a new hash sets _ota_pending flag."""
        import mqtt_client

        with patch("mqtt_client.ota_update") as mock_ota:
            mock_ota.read_file.return_value = "oldhash123"

            mqtt_client._handle_ota_notification(
                b"vtms/ota/test_device/notify",
                b'{"hash": "newhash456"}',
            )

        assert mqtt_client._ota_pending is True

    def test_no_flag_when_hash_matches(self):
        """OTA notification with the same hash does not set flag."""
        import mqtt_client

        with patch("mqtt_client.ota_update") as mock_ota:
            mock_ota.read_file.return_value = "samehash"

            mqtt_client._handle_ota_notification(
                b"vtms/ota/test_device/notify",
                b'{"hash": "samehash"}',
            )

        assert mqtt_client._ota_pending is False

    def test_no_flag_when_no_local_hash(self):
        """First boot with no local hash — don't flag (boot.py already ran OTA)."""
        import mqtt_client

        with patch("mqtt_client.ota_update") as mock_ota:
            mock_ota.read_file.return_value = ""

            mqtt_client._handle_ota_notification(
                b"vtms/ota/test_device/notify",
                b'{"hash": "newhash456"}',
            )

        assert mqtt_client._ota_pending is False

    def test_bad_json_does_not_crash(self, capsys):
        """Malformed OTA notification payload is caught, not propagated."""
        import mqtt_client

        with patch("mqtt_client.ota_update") as mock_ota:
            mock_ota.read_file.return_value = "somehash"

            mqtt_client._handle_ota_notification(
                b"vtms/ota/test_device/notify",
                b"not-json",
            )

        assert mqtt_client._ota_pending is False
        captured = capsys.readouterr()
        assert "OTA notification error" in captured.out

    def test_empty_server_hash_does_not_flag(self):
        """OTA notification with empty hash does not set flag."""
        import mqtt_client

        with patch("mqtt_client.ota_update") as mock_ota:
            mock_ota.read_file.return_value = "localhash"

            mqtt_client._handle_ota_notification(
                b"vtms/ota/test_device/notify",
                b'{"hash": ""}',
            )

        assert mqtt_client._ota_pending is False
```

**Step 5: Add tests for `ota_pending()` and `run_pending_ota()`**

```python
class TestRunPendingOta:
    """Test ota_pending() and run_pending_ota() flag-based OTA."""

    def setup_method(self):
        import mqtt_client
        mqtt_client._ota_pending = False

    def teardown_method(self):
        import mqtt_client
        mqtt_client._ota_pending = False

    def test_ota_pending_false_by_default(self):
        """ota_pending() returns False when no notification received."""
        import mqtt_client
        assert mqtt_client.ota_pending() is False

    def test_ota_pending_true_after_notification(self):
        """ota_pending() returns True after hash-mismatch notification."""
        import mqtt_client
        mqtt_client._ota_pending = True
        assert mqtt_client.ota_pending() is True

    def test_run_pending_returns_none_when_not_pending(self):
        """run_pending_ota() returns None and skips OTA when not pending."""
        import mqtt_client

        with patch("mqtt_client.ota_update") as mock_ota:
            result = mqtt_client.run_pending_ota()

        assert result is None
        mock_ota.check_and_update.assert_not_called()

    def test_run_pending_calls_check_and_update(self):
        """run_pending_ota() calls check_and_update when OTA is pending."""
        import mqtt_client
        mqtt_client._ota_pending = True

        with patch("mqtt_client.ota_update") as mock_ota:
            mock_ota.check_and_update.return_value = "updated"
            result = mqtt_client.run_pending_ota()

        assert result == "updated"
        mock_ota.check_and_update.assert_called_once_with(
            "127.0.0.1:8266", "test_device"
        )

    def test_run_pending_clears_flag(self):
        """run_pending_ota() clears _ota_pending regardless of result."""
        import mqtt_client
        mqtt_client._ota_pending = True

        with patch("mqtt_client.ota_update") as mock_ota:
            mock_ota.check_and_update.return_value = "error"
            mqtt_client.run_pending_ota()

        assert mqtt_client._ota_pending is False

    def test_run_pending_returns_error(self):
        """run_pending_ota() propagates error result from check_and_update."""
        import mqtt_client
        mqtt_client._ota_pending = True

        with patch("mqtt_client.ota_update") as mock_ota:
            mock_ota.check_and_update.return_value = "error"
            result = mqtt_client.run_pending_ota()

        assert result == "error"

    def test_run_pending_returns_current(self):
        """run_pending_ota() returns current if firmware already matches."""
        import mqtt_client
        mqtt_client._ota_pending = True

        with patch("mqtt_client.ota_update") as mock_ota:
            mock_ota.check_and_update.return_value = "current"
            result = mqtt_client.run_pending_ota()

        assert result == "current"
```

**Step 6: Run tests**

Run: `pytest arduino/common/tests/test_mqtt_client.py -v`
Expected: All tests pass.

**Step 7: Commit**

```bash
git add arduino/common/mqtt_client.py arduino/common/config.py \
  arduino/common/tests/test_mqtt_client.py
git commit -m "fix: replace MQTT blind-reboot with flag-based OTA from main loop"
```

---

### Task 4: Add OTA check to all 4 main.py main loops

**Files:**
- Modify: `arduino/analog_sensors/main.py:120-121`
- Modify: `arduino/led_controller/main.py:110-111`
- Modify: `arduino/temp_sensor/main.py:87-88`
- Modify: `arduino/thermoprobe/main.py:84-85`

**Step 1: Add OTA check block after `mqtt.check_msg()` in each main.py**

In each file, after the `mqtt.check_msg()` line, add:

```python
            # Check for MQTT-triggered OTA update
            ota_result = mqtt_client.run_pending_ota()
            if ota_result == "updated":
                print("OTA: update applied, rebooting...")
                reset()
```

This goes right after `mqtt.check_msg()` and before any sensor reads. Example for `analog_sensors/main.py` the block at line 120 becomes:

```python
            # Process any pending status requests
            mqtt.check_msg()

            # Check for MQTT-triggered OTA update
            ota_result = mqtt_client.run_pending_ota()
            if ota_result == "updated":
                print("OTA: update applied, rebooting...")
                reset()

            # Read ADC (voltage after HiLetgo 5:1 divider)
```

**Step 2: Commit**

```bash
git add arduino/analog_sensors/main.py arduino/led_controller/main.py \
  arduino/temp_sensor/main.py arduino/thermoprobe/main.py
git commit -m "feat: add MQTT-triggered OTA check to all device main loops"
```

---

### Task 5: Make firmware hash publication retained

**Files:**
- Modify: `arduino/common/mqtt_client.py` (`publish` and `publish_firmware_hash`)
- Test: `arduino/common/tests/test_mqtt_client.py`

**Step 1: Write test for retained publish**

Add to `test_mqtt_client.py`:

```python
class TestPublishFirmwareHash:
    """Test publish_firmware_hash publishes retained hash."""

    def test_publishes_hash_with_retain(self):
        """publish_firmware_hash publishes hash as retained message."""
        import mqtt_client

        mock_client = MagicMock()

        with patch("mqtt_client.ota_update") as mock_ota:
            mock_ota.read_file.return_value = "abc123hash"

            mqtt_client.publish_firmware_hash(mock_client)

        mock_client.publish.assert_called_once_with(
            b"lemons/firmware/test_device",
            b"abc123hash",
            retain=True,
        )

    def test_publishes_unknown_when_no_hash(self):
        """publish_firmware_hash publishes 'unknown' when no hash file."""
        import mqtt_client

        mock_client = MagicMock()

        with patch("mqtt_client.ota_update") as mock_ota:
            mock_ota.read_file.return_value = ""

            mqtt_client.publish_firmware_hash(mock_client)

        mock_client.publish.assert_called_once_with(
            b"lemons/firmware/test_device",
            b"unknown",
            retain=True,
        )
```

**Step 2: Run test to verify it fails**

Run: `pytest arduino/common/tests/test_mqtt_client.py::TestPublishFirmwareHash -v`
Expected: FAIL (currently publish doesn't pass retain=True)

**Step 3: Update `publish()` to accept optional retain parameter**

Change:
```python
def publish(client, topic, value):
    """Publish a value to an MQTT topic.

    topic: full topic string (e.g. "lemons/temp/oil_F")
    value: will be converted to string
    """
    msg = str(value)
    client.publish(topic.encode(), msg.encode())
```

to:
```python
def publish(client, topic, value, retain=False):
    """Publish a value to an MQTT topic.

    topic: full topic string (e.g. "lemons/temp/oil_F")
    value: will be converted to string
    retain: if True, broker stores the message for new subscribers
    """
    msg = str(value)
    client.publish(topic.encode(), msg.encode(), retain=retain)
```

**Step 4: Update `publish_firmware_hash()` to use retain=True**

Change:
```python
    publish(client, topic, fw_hash)
```
to:
```python
    publish(client, topic, fw_hash, retain=True)
```

**Step 5: Run tests**

Run: `pytest arduino/common/tests/test_mqtt_client.py -v`
Expected: All tests pass.

**Step 6: Commit**

```bash
git add arduino/common/mqtt_client.py arduino/common/tests/test_mqtt_client.py
git commit -m "feat: make firmware hash publication retained for remote verification"
```

---

### Task 6: Final verification

**Step 1: Run full test suite**

Run: `pytest arduino/common/tests/ -v`
Expected: All tests pass.

**Step 2: Verify no references to `is_on_hotspot` remain**

Run: `grep -r "is_on_hotspot" arduino/`
Expected: No matches.

**Step 3: Verify no `machine.reset()` in mqtt_client.py**

Run: `grep "machine.reset\|machine\.reset" arduino/common/mqtt_client.py`
Expected: No matches.
