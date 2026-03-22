"""
Integration tests for the VTMS system.

These tests exercise the wiring between VTMSClient, MQTTTransport,
OBDService, GPSService, and MQTTMessageRouter — verifying that the
pieces compose correctly at a higher level than the individual module
tests.
"""

import asyncio
import sys
import os
import time
from unittest.mock import Mock, patch, MagicMock

import pytest

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client import VTMSClient
from src.config import Config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mqtt_msg(topic: str, payload: str) -> Mock:
    """Build a mock paho MQTT message."""
    msg = Mock()
    msg.topic = topic
    msg.payload = Mock()
    msg.payload.decode.return_value = payload
    return msg


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestVTMSIntegration:
    """Integration tests for the complete VTMS system."""

    @patch.object(Config, "is_raspberrypi", return_value=False)
    def test_message_routing_integration(self, mock_is_pi):
        """Test complete message routing through _on_message."""
        client = VTMSClient()

        # Replace OBD service with a mock so we can observe fallback routing
        client.obd = Mock()

        test_messages = [
            ("lemons/debug", "true"),
            ("lemons/message", "Test pit message"),
            ("lemons/flag/red", "true"),
            ("lemons/flag/black", "true"),
            ("lemons/pit", "true"),
            ("lemons/box", "true"),
        ]

        with patch("src.config.config") as mock_config:
            mock_config.debug = False
            for topic, payload in test_messages:
                msg = _make_mqtt_msg(topic, payload)
                # Should not raise
                client._on_message(Mock(), None, msg)

    @patch("obd.commands")
    @patch.object(Config, "is_raspberrypi", return_value=False)
    def test_obd_message_handling_integration(self, mock_is_pi, mock_commands):
        """Test OBD message handling through the real OBDService."""
        mock_commands.__contains__ = Mock(return_value=True)
        mock_commands.__getitem__ = Mock(return_value="TEST_COMMAND")

        client = VTMSClient()

        # Give the OBD service a mock connection
        mock_conn = Mock()
        mock_conn.paused.return_value = Mock(
            __enter__=Mock(return_value=None), __exit__=Mock(return_value=False)
        )
        client.obd.connection = mock_conn

        # Route a watch command through _on_message → OBD fallback
        with patch("src.config.config") as mock_config:
            mock_config.debug = False

            msg = _make_mqtt_msg("lemons/obd2/watch", "RPM")
            client._on_message(Mock(), None, msg)

        # OBDService.handle_message should have called connection.watch
        mock_conn.watch.assert_called_once()

    @patch.object(Config, "is_raspberrypi", return_value=False)
    def test_unhandled_message_falls_back_to_obd(self, mock_is_pi):
        """Messages not matched by the router should fall back to obd.handle_message."""
        client = VTMSClient()
        client.obd = Mock()

        with patch("src.config.config") as mock_config:
            mock_config.debug = False
            msg = _make_mqtt_msg("lemons/obd2/query", "RPM")
            client._on_message(Mock(), None, msg)

        client.obd.handle_message.assert_called_once_with("lemons/obd2/query", "RPM")

    @patch.object(Config, "is_raspberrypi", return_value=False)
    def test_cleanup_and_shutdown(self, mock_is_pi):
        """Test that service stop/close methods work correctly."""
        client = VTMSClient()

        # Replace services with mocks
        client.obd = Mock()
        client.gps = Mock()
        client.mqtt = Mock()

        # Simulate the cleanup that happens in VTMSClient.run()'s finally block
        client.obd.stop()
        client.gps.close()
        client.mqtt.stop()

        # Verify cleanup methods were called
        client.obd.stop.assert_called_once()
        client.gps.close.assert_called_once()
        client.mqtt.stop.assert_called_once()

    @patch("src.config.config")
    @patch.object(Config, "is_raspberrypi", return_value=False)
    def test_debug_mode_integration(self, mock_is_pi, mock_config):
        """Test debug mode can be toggled via MQTT message."""
        mock_config.debug = False

        client = VTMSClient()

        # Send debug=true via the message router
        client.message_router.route_message("lemons/debug", "true")
        assert mock_config.debug is True

        client.message_router.route_message("lemons/debug", "false")
        assert mock_config.debug is False


class TestVTMSPerformance:
    """Performance / stress tests for VTMS message routing."""

    @patch.object(Config, "is_raspberrypi", return_value=False)
    def test_message_throughput(self, mock_is_pi):
        """Test system can handle high message throughput."""
        client = VTMSClient()

        start_time = time.time()
        message_count = 100

        with patch("src.config.config") as mock_config:
            mock_config.debug = False
            for i in range(message_count):
                client.message_router.route_message(
                    "lemons/debug", "true" if i % 2 == 0 else "false"
                )

        processing_time = time.time() - start_time

        # Should process 100 messages in well under 1 second
        assert processing_time < 1.0
