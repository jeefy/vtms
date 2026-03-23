"""
Unit tests for the VTMSClient orchestrator (__main__.py)

The heavy lifting (MQTT, GPS, OBD) is now tested in the individual
service-module test files. These tests verify the thin wiring layer.
"""

from unittest.mock import Mock, patch

from vtms_client.config import Config


class TestVTMSClientInit:
    """Test VTMSClient construction and wiring."""

    @patch.object(Config, "is_raspberrypi", return_value=False)
    def test_init_creates_services(self, mock_is_pi):
        from vtms_client import VTMSClient

        client = VTMSClient()

        assert client.mqtt is not None
        assert client.gps is not None
        assert client.obd is not None
        assert client.message_router is not None
        assert client.is_pi is False
        assert client.led_handler is None

    @patch.object(Config, "is_raspberrypi", return_value=True)
    def test_init_raspberry_pi_with_led(self, mock_is_pi):
        with patch.dict("sys.modules", {"vtms_client.led": Mock()}):
            from vtms_client import VTMSClient

            client = VTMSClient()
            assert client.is_pi is True
            assert client.led_handler is not None

    @patch.object(Config, "is_raspberrypi", return_value=True)
    def test_init_raspberry_pi_without_led(self, mock_is_pi):
        """When the LED module can't be imported, led_handler stays None."""
        import importlib
        import vtms_client as client_mod

        # Temporarily make 'vtms_client.led' unimportable
        with patch.dict("sys.modules", {"vtms_client.led": None}):
            importlib.reload(client_mod)
            client = client_mod.VTMSClient()
            assert client.is_pi is True
            assert client.led_handler is None

        # Reload to restore normal state
        importlib.reload(client_mod)


class TestVTMSClientMessageHandlers:
    """Test message handler registration."""

    @patch.object(Config, "is_raspberrypi", return_value=False)
    def test_handlers_registered(self, mock_is_pi):
        from vtms_client import VTMSClient

        client = VTMSClient()

        assert "lemons/debug" in client.message_router.handlers
        assert "lemons/message" in client.message_router.handlers
        assert "lemons/pit" in client.message_router.handlers
        assert "lemons/box" in client.message_router.handlers
        assert "lemons/flag/" in client.message_router.pattern_handlers


class TestVTMSClientOnMessage:
    """Test the top-level _on_message callback."""

    @patch("vtms_client.config.config")
    @patch.object(Config, "is_raspberrypi", return_value=False)
    def test_on_message_routes_to_handler(self, mock_is_pi, mock_config):
        from vtms_client import VTMSClient

        mock_config.debug = False

        client = VTMSClient()
        # Replace the router with a mock so we can observe routing
        client.message_router = Mock()
        client.message_router.route_message.return_value = True

        msg = Mock()
        msg.topic = "lemons/debug"
        msg.payload.decode.return_value = "true"

        client._on_message(Mock(), None, msg)

        client.message_router.route_message.assert_called_once_with(
            "lemons/debug", "true"
        )

    @patch("vtms_client.config.config")
    @patch.object(Config, "is_raspberrypi", return_value=False)
    def test_on_message_falls_back_to_obd(self, mock_is_pi, mock_config):
        from vtms_client import VTMSClient

        mock_config.debug = False

        client = VTMSClient()
        # Router returns False (no handler matched) → should try OBD
        client.message_router = Mock()
        client.message_router.route_message.return_value = False
        client.obd = Mock()

        msg = Mock()
        msg.topic = "lemons/obd2/watch"
        msg.payload.decode.return_value = "RPM"

        client._on_message(Mock(), None, msg)

        client.obd.handle_message.assert_called_once_with("lemons/obd2/watch", "RPM")

    @patch("vtms_client.config.config")
    @patch.object(Config, "is_raspberrypi", return_value=False)
    def test_on_message_handles_exception(self, mock_is_pi, mock_config):
        """Errors in message handling should be caught, not crash the loop."""
        from vtms_client import VTMSClient

        mock_config.debug = False

        client = VTMSClient()

        msg = Mock()
        msg.payload.decode.side_effect = Exception("decode error")

        # Should not raise
        client._on_message(Mock(), None, msg)


class TestVTMSClientGPSOBDWiring:
    """Verify that GPS and OBD services receive mqtt.publish as publisher."""

    @patch.object(Config, "is_raspberrypi", return_value=False)
    def test_gps_publisher_is_mqtt_publish(self, mock_is_pi):
        from vtms_client import VTMSClient

        client = VTMSClient()
        # Bound-method identity changes per access; compare underlying function + object
        assert client.gps.publisher.__func__ is client.mqtt.publish.__func__
        assert client.gps.publisher.__self__ is client.mqtt

    @patch.object(Config, "is_raspberrypi", return_value=False)
    def test_obd_publisher_is_mqtt_publish(self, mock_is_pi):
        from vtms_client import VTMSClient

        client = VTMSClient()
        assert client.obd.publisher.__func__ is client.mqtt.publish.__func__
        assert client.obd.publisher.__self__ is client.mqtt
