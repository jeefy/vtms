"""Tests for MQTT client wrapper.

Run on host with CPython/pytest.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, call


class TestMqttConnect:
    """Test MQTT connect guard."""

    def test_raises_when_umqtt_missing(self):
        import mqtt_client

        orig = mqtt_client.MQTTClient
        mqtt_client.MQTTClient = None
        try:
            with pytest.raises(RuntimeError, match="umqtt.robust not installed"):
                mqtt_client.connect()
        finally:
            mqtt_client.MQTTClient = orig


class TestHandleStatusRequest:
    """Test _handle_status_request builds and publishes diagnostics."""

    def test_publishes_diagnostics_json(self):
        """Status request handler publishes JSON with all diagnostic fields."""
        import mqtt_client

        mock_client = MagicMock()
        mock_wlan = MagicMock()
        mock_wlan.status.return_value = -55
        mock_wlan.config.return_value = "MyNetwork"
        mock_wlan.ifconfig.return_value = ("192.168.1.42", "", "", "")

        with (
            patch("mqtt_client.gc") as mock_gc,
            patch("mqtt_client.time") as mock_time,
            patch("mqtt_client.network") as mock_network,
            patch("mqtt_client._client_id", return_value="test-abc123"),
            patch("mqtt_client.ota_update") as mock_ota,
        ):
            mock_gc.mem_free.return_value = 50000
            mock_time.ticks_ms.return_value = 120000
            mock_network.WLAN.return_value = mock_wlan
            mock_ota.read_file.return_value = "abc123hash"

            mqtt_client._handle_status_request(mock_client)

        # Verify publish was called
        assert mock_client.publish.call_count == 1
        topic_arg = mock_client.publish.call_args[0][0]
        msg_arg = mock_client.publish.call_args[0][1]

        assert topic_arg == b"lemons/status/response/test_device"

        payload = json.loads(msg_arg.decode())
        assert payload["device_type"] == "test_device"
        assert payload["client_id"] == "test-abc123"
        assert payload["firmware_hash"] == "abc123hash"
        assert payload["uptime_s"] == 120
        assert payload["free_mem"] == 50000
        assert payload["wifi_rssi"] == -55
        assert payload["wifi_ssid"] == "MyNetwork"
        assert payload["ip"] == "192.168.1.42"

    def test_firmware_hash_unknown_when_read_fails(self):
        """When ota_update.read_file returns empty, firmware_hash is 'unknown'."""
        import mqtt_client

        mock_client = MagicMock()
        mock_wlan = MagicMock()
        mock_wlan.status.return_value = -70
        mock_wlan.config.return_value = "Net"
        mock_wlan.ifconfig.return_value = ("10.0.0.1", "", "", "")

        with (
            patch("mqtt_client.gc") as mock_gc,
            patch("mqtt_client.time") as mock_time,
            patch("mqtt_client.network") as mock_network,
            patch("mqtt_client._client_id", return_value="test-xyz"),
            patch("mqtt_client.ota_update") as mock_ota,
        ):
            mock_gc.mem_free.return_value = 30000
            mock_time.ticks_ms.return_value = 5000
            mock_network.WLAN.return_value = mock_wlan
            mock_ota.read_file.return_value = ""

            mqtt_client._handle_status_request(mock_client)

        msg_arg = mock_client.publish.call_args[0][1]
        payload = json.loads(msg_arg.decode())
        assert payload["firmware_hash"] == "unknown"

    def test_exception_is_caught_and_printed(self, capsys):
        """Errors in _handle_status_request are caught, not propagated."""
        import mqtt_client

        mock_client = MagicMock()

        with (
            patch("mqtt_client.gc") as mock_gc,
            patch("mqtt_client.network") as mock_network,
            patch("mqtt_client.ota_update") as mock_ota,
        ):
            mock_ota.read_file.side_effect = OSError("disk error")

            # Should NOT raise
            mqtt_client._handle_status_request(mock_client)

        mock_client.publish.assert_not_called()
        captured = capsys.readouterr()
        assert "Status request failed:" in captured.out
        assert "disk error" in captured.out


class TestClientIdCaching:
    """Test _client_id() caches its result."""

    def setup_method(self):
        import mqtt_client

        mqtt_client._cached_client_id = None

    def teardown_method(self):
        import mqtt_client

        mqtt_client._cached_client_id = None

    def test_client_id_caches_result(self):
        """_client_id() only reads MAC once, returns cached value after."""
        import mqtt_client

        mock_wlan = MagicMock()
        mock_wlan.config.return_value = b"\x00\x00\x00\xaa\xbb\xcc"

        mock_ubinascii = MagicMock()
        mock_ubinascii.hexlify.return_value = b"aabbcc"

        with (
            patch("mqtt_client.network") as mock_network,
            patch.dict("sys.modules", {"ubinascii": mock_ubinascii}),
        ):
            mock_network.WLAN.return_value = mock_wlan
            mock_network.STA_IF = 0

            first = mqtt_client._client_id()
            second = mqtt_client._client_id()

        assert first == second
        # WLAN should only be accessed once
        assert mock_network.WLAN.call_count == 1


class TestConnectWithCallback:
    """Test connect() sets up combined callback and subscribes to status topics."""

    def _make_connect_work(self, mqtt_client):
        """Set up mocks so connect() can execute."""
        mock_mqtt_cls = MagicMock()
        mock_client = MagicMock()
        mock_mqtt_cls.return_value = mock_client
        mqtt_client.MQTTClient = mock_mqtt_cls
        return mock_client

    @patch("mqtt_client._client_id", return_value="test-aaa")
    def test_connect_without_callback_still_works(self, _mock_id):
        """connect() with no args is backward compatible."""
        import mqtt_client

        mock_client = self._make_connect_work(mqtt_client)
        try:
            result = mqtt_client.connect()
            assert result is mock_client
            mock_client.connect.assert_called_once()
        finally:
            mqtt_client.MQTTClient = None

    @patch("mqtt_client._client_id", return_value="test-bbb")
    def test_connect_subscribes_to_status_topics(self, _mock_id):
        """connect() subscribes to both status request topics."""
        import mqtt_client

        mock_client = self._make_connect_work(mqtt_client)
        try:
            mqtt_client.connect()

            subscribe_calls = mock_client.subscribe.call_args_list
            topics = [c[0][0] for c in subscribe_calls]
            assert b"lemons/status/request" in topics
            assert b"lemons/status/request/test_device" in topics
        finally:
            mqtt_client.MQTTClient = None

    @patch("mqtt_client._client_id", return_value="test-ccc")
    def test_connect_sets_combined_callback(self, _mock_id):
        """connect() sets a callback on the client."""
        import mqtt_client

        mock_client = self._make_connect_work(mqtt_client)
        try:
            mqtt_client.connect()
            mock_client.set_callback.assert_called_once()
        finally:
            mqtt_client.MQTTClient = None

    @patch("mqtt_client._client_id", return_value="test-ddd")
    def test_combined_callback_routes_status_request(self, _mock_id):
        """Combined callback calls _handle_status_request for status topics."""
        import mqtt_client

        mock_client = self._make_connect_work(mqtt_client)
        try:
            mqtt_client.connect()

            # Get the combined callback that was set
            combined_cb = mock_client.set_callback.call_args[0][0]

            with patch.object(mqtt_client, "_handle_status_request") as mock_handler:
                combined_cb(b"lemons/status/request", b"")
                mock_handler.assert_called_once_with(mock_client)
        finally:
            mqtt_client.MQTTClient = None

    @patch("mqtt_client._client_id", return_value="test-eee")
    def test_combined_callback_routes_device_specific_status(self, _mock_id):
        """Combined callback handles device-specific status request topic."""
        import mqtt_client

        mock_client = self._make_connect_work(mqtt_client)
        try:
            mqtt_client.connect()

            combined_cb = mock_client.set_callback.call_args[0][0]

            with patch.object(mqtt_client, "_handle_status_request") as mock_handler:
                combined_cb(b"lemons/status/request/test_device", b"")
                mock_handler.assert_called_once_with(mock_client)
        finally:
            mqtt_client.MQTTClient = None

    @patch("mqtt_client._client_id", return_value="test-fff")
    def test_combined_callback_forwards_other_topics_to_user_callback(self, _mock_id):
        """Non-status topics are forwarded to user_callback."""
        import mqtt_client

        mock_client = self._make_connect_work(mqtt_client)
        user_cb = MagicMock()
        try:
            mqtt_client.connect(user_callback=user_cb)

            combined_cb = mock_client.set_callback.call_args[0][0]
            combined_cb(b"lemons/temp/oil_F", b"205")

            user_cb.assert_called_once_with(b"lemons/temp/oil_F", b"205")
        finally:
            mqtt_client.MQTTClient = None

    @patch("mqtt_client._client_id", return_value="test-ggg")
    def test_combined_callback_no_user_callback_ignores_other_topics(self, _mock_id):
        """Without user_callback, non-status topics are silently ignored."""
        import mqtt_client

        mock_client = self._make_connect_work(mqtt_client)
        try:
            mqtt_client.connect()

            combined_cb = mock_client.set_callback.call_args[0][0]
            # Should not raise
            combined_cb(b"lemons/temp/oil_F", b"205")
        finally:
            mqtt_client.MQTTClient = None


class TestSubscribeTopic:
    """Test subscribe_topic() subscribes without setting callback."""

    def test_subscribes_without_setting_callback(self):
        """subscribe_topic() only calls client.subscribe, not set_callback."""
        import mqtt_client

        mock_client = MagicMock()
        mqtt_client.subscribe_topic(mock_client, "lemons/led/command")

        mock_client.subscribe.assert_called_once_with(b"lemons/led/command")
        mock_client.set_callback.assert_not_called()

    def test_subscribe_topic_prints_topic(self, capsys):
        """subscribe_topic() prints confirmation."""
        import mqtt_client

        mock_client = MagicMock()
        mqtt_client.subscribe_topic(mock_client, "lemons/led/command")

        captured = capsys.readouterr()
        assert "lemons/led/command" in captured.out


class TestExistingSubscribe:
    """Verify existing subscribe() function still works but warns."""

    def test_subscribe_sets_callback_and_subscribes(self):
        """Original subscribe() still sets callback and subscribes."""
        import mqtt_client

        mock_client = MagicMock()
        mock_cb = MagicMock()
        mqtt_client.subscribe(mock_client, "lemons/temp/oil_F", mock_cb)

        mock_client.set_callback.assert_called_once_with(mock_cb)
        mock_client.subscribe.assert_called_once_with(b"lemons/temp/oil_F")

    def test_subscribe_prints_deprecation_warning(self, capsys):
        """subscribe() prints a deprecation warning about subscribe_topic()."""
        import mqtt_client

        mock_client = MagicMock()
        mock_cb = MagicMock()
        mqtt_client.subscribe(mock_client, "lemons/temp/oil_F", mock_cb)

        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "subscribe_topic()" in captured.out


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

            # Should NOT raise
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


class TestConnectSubscribesOtaNotify:
    """Test connect() subscribes to OTA notification topic."""

    def _make_connect_work(self, mqtt_client):
        mock_mqtt_cls = MagicMock()
        mock_client = MagicMock()
        mock_mqtt_cls.return_value = mock_client
        mqtt_client.MQTTClient = mock_mqtt_cls
        return mock_client

    @patch("mqtt_client._client_id", return_value="test-ota1")
    def test_connect_subscribes_to_ota_notify(self, _mock_id):
        """connect() subscribes to vtms/ota/{DEVICE_TYPE}/notify."""
        import mqtt_client

        mock_client = self._make_connect_work(mqtt_client)
        try:
            mqtt_client.connect()

            subscribe_calls = mock_client.subscribe.call_args_list
            topics = [c[0][0] for c in subscribe_calls]
            assert b"vtms/ota/test_device/notify" in topics
        finally:
            mqtt_client.MQTTClient = None

    @patch("mqtt_client._client_id", return_value="test-ota2")
    def test_combined_callback_routes_ota_notification(self, _mock_id):
        """Combined callback calls _handle_ota_notification for OTA topics."""
        import mqtt_client

        mock_client = self._make_connect_work(mqtt_client)
        try:
            mqtt_client.connect()

            combined_cb = mock_client.set_callback.call_args[0][0]

            with patch.object(mqtt_client, "_handle_ota_notification") as mock_handler:
                combined_cb(
                    b"vtms/ota/test_device/notify",
                    b'{"hash": "abc"}',
                )
                mock_handler.assert_called_once_with(
                    b"vtms/ota/test_device/notify",
                    b'{"hash": "abc"}',
                )
        finally:
            mqtt_client.MQTTClient = None


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
