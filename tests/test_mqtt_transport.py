"""
Unit tests for MQTTTransport
"""

import time
from collections import deque
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.mqtt_transport import MQTTTransport


class TestMQTTTransportInit:
    """Test MQTTTransport initialisation."""

    def test_defaults(self):
        transport = MQTTTransport()
        assert transport.connected is False
        assert transport.mqttc is None
        assert isinstance(transport.message_buffer, deque)
        assert transport.on_message_callback is None

    def test_custom_callback(self):
        cb = MagicMock()
        transport = MQTTTransport(on_message_callback=cb)
        assert transport.on_message_callback is cb


class TestMQTTTransportConnect:
    """Test connect / start / stop lifecycle."""

    @patch("src.mqtt_transport.mqtt.Client")
    def test_connect_success(self, MockClient):
        mock_client = MockClient.return_value
        transport = MQTTTransport()

        result = transport.connect()

        assert result is True
        assert transport.mqttc is mock_client
        mock_client.connect.assert_called_once()

    @patch("src.mqtt_transport.mqtt.Client")
    def test_connect_failure(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.connect.side_effect = ConnectionRefusedError("refused")
        transport = MQTTTransport()

        result = transport.connect()

        assert result is False

    @patch("src.mqtt_transport.mqtt.Client")
    def test_start_calls_loop_start(self, MockClient):
        mock_client = MockClient.return_value
        transport = MQTTTransport()
        transport.connect()

        transport.start()

        mock_client.loop_start.assert_called_once()

    @patch("src.mqtt_transport.mqtt.Client")
    def test_stop_calls_loop_stop_and_disconnect(self, MockClient):
        mock_client = MockClient.return_value
        transport = MQTTTransport()
        transport.connect()

        transport.stop()

        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()


class TestMQTTTransportReconnect:
    """Test reconnect with loop_start bug fix."""

    @patch("src.mqtt_transport.mqtt.Client")
    def test_reconnect_calls_loop_start(self, MockClient):
        """Verify the bug fix: reconnect must call loop_start()."""
        mock_client = MockClient.return_value
        transport = MQTTTransport()

        result = transport.reconnect()

        assert result is True
        # connect() is called internally, then loop_start()
        mock_client.loop_start.assert_called()

    @patch("src.mqtt_transport.mqtt.Client")
    def test_reconnect_stops_old_client(self, MockClient):
        mock_client = MockClient.return_value
        transport = MQTTTransport()
        transport.connect()

        # Reset mocks so we can track reconnect calls
        mock_client.reset_mock()

        transport.reconnect()

        # Old client should be stopped before new connection
        mock_client.loop_stop.assert_called()


class TestMQTTTransportPublish:
    """Test publish with buffering."""

    @patch("src.mqtt_transport.mqtt.Client")
    def test_publish_when_connected(self, MockClient):
        mock_client = MockClient.return_value
        mock_result = MagicMock()
        mock_result.rc = 0
        mock_client.publish.return_value = mock_result

        transport = MQTTTransport()
        transport.connect()
        transport.connected = True

        result = transport.publish("test/topic", "payload")

        assert result is True
        mock_client.publish.assert_called_once_with("test/topic", "payload", 0, False)

    @patch("src.mqtt_transport.mqtt.Client")
    def test_publish_dict_payload_serialized(self, MockClient):
        mock_client = MockClient.return_value
        mock_result = MagicMock()
        mock_result.rc = 0
        mock_client.publish.return_value = mock_result

        transport = MQTTTransport()
        transport.connect()
        transport.connected = True

        transport.publish("test/topic", {"key": "value"})

        call_args = mock_client.publish.call_args
        assert '"key"' in call_args[0][1]  # JSON serialized

    def test_publish_buffers_when_disconnected(self):
        transport = MQTTTransport()
        transport.connected = False

        result = transport.publish("test/topic", "payload")

        assert result is False
        assert len(transport.message_buffer) == 1
        assert transport.message_buffer[0]["topic"] == "test/topic"

    @patch("src.mqtt_transport.mqtt.Client")
    def test_publish_buffers_on_failure(self, MockClient):
        mock_client = MockClient.return_value
        mock_result = MagicMock()
        mock_result.rc = 1  # failure
        mock_client.publish.return_value = mock_result

        transport = MQTTTransport()
        transport.connect()
        transport.connected = True

        result = transport.publish("test/topic", "payload")

        assert result is False
        assert len(transport.message_buffer) == 1


class TestMQTTTransportBuffering:
    """Test message buffering and flushing."""

    def test_buffer_message_adds_to_deque(self):
        transport = MQTTTransport()

        transport._buffer_message("topic1", "payload1")
        transport._buffer_message("topic2", "payload2")

        assert len(transport.message_buffer) == 2

    def test_buffer_drops_oldest_when_full(self):
        transport = MQTTTransport()
        transport.max_buffer_size = 2

        transport._buffer_message("topic1", "p1")
        transport._buffer_message("topic2", "p2")
        transport._buffer_message("topic3", "p3")

        # Oldest should have been dropped
        assert len(transport.message_buffer) == 2
        topics = [m["topic"] for m in transport.message_buffer]
        assert "topic1" not in topics

    @patch("src.mqtt_transport.mqtt.Client")
    def test_flush_sends_buffered_messages(self, MockClient):
        mock_client = MockClient.return_value
        mock_result = MagicMock()
        mock_result.rc = 0
        mock_client.publish.return_value = mock_result

        transport = MQTTTransport()
        transport.connect()
        transport.connected = True

        # Buffer some messages
        transport.message_buffer.append(
            {
                "topic": "t1",
                "payload": "p1",
                "qos": 0,
                "retain": False,
                "timestamp": time.time(),
            }
        )
        transport.message_buffer.append(
            {
                "topic": "t2",
                "payload": "p2",
                "qos": 0,
                "retain": False,
                "timestamp": time.time(),
            }
        )

        transport._flush_message_buffer()

        assert len(transport.message_buffer) == 0
        assert mock_client.publish.call_count == 2

    @patch("src.mqtt_transport.mqtt.Client")
    def test_flush_drops_expired_messages(self, MockClient):
        mock_client = MockClient.return_value

        transport = MQTTTransport()
        transport.connect()
        transport.connected = True

        # Buffer an expired message (> 5 minutes old)
        transport.message_buffer.append(
            {
                "topic": "old",
                "payload": "p",
                "qos": 0,
                "retain": False,
                "timestamp": time.time() - 400,
            }
        )

        transport._flush_message_buffer()

        assert len(transport.message_buffer) == 0
        mock_client.publish.assert_not_called()

    def test_flush_does_nothing_when_disconnected(self):
        transport = MQTTTransport()
        transport.connected = False
        transport.message_buffer.append(
            {
                "topic": "t",
                "payload": "p",
                "qos": 0,
                "retain": False,
                "timestamp": time.time(),
            }
        )

        transport._flush_message_buffer()

        assert len(transport.message_buffer) == 1  # unchanged


class TestMQTTTransportCallbacks:
    """Test paho callback methods."""

    def test_on_connect_success(self):
        transport = MQTTTransport()
        mock_client = MagicMock()

        transport._on_connect(mock_client, None, None, 0, None)

        assert transport.connected is True
        mock_client.subscribe.assert_called_once_with("lemons/#")

    def test_on_connect_failure(self):
        transport = MQTTTransport()
        mock_client = MagicMock()

        transport._on_connect(mock_client, None, None, 5, None)

        assert transport.connected is False

    def test_on_disconnect_unexpected(self):
        transport = MQTTTransport()
        transport.connected = True

        transport._on_disconnect(MagicMock(), None, 1, None)

        assert transport.connected is False

    def test_on_disconnect_normal(self):
        transport = MQTTTransport()
        transport.connected = True

        transport._on_disconnect(MagicMock(), None, 0, None)

        assert transport.connected is False

    def test_on_message_routes_to_callback(self):
        cb = MagicMock()
        transport = MQTTTransport(on_message_callback=cb)
        mock_msg = MagicMock()

        transport._on_message(MagicMock(), None, mock_msg)

        cb.assert_called_once()

    def test_on_message_no_callback(self):
        transport = MQTTTransport()
        # Should not raise
        transport._on_message(MagicMock(), None, MagicMock())


class TestMQTTTransportConnectionMonitor:
    """Test the async connection monitor."""

    @pytest.mark.asyncio
    async def test_monitor_cancellation(self):
        """Monitor should exit cleanly on CancelledError."""
        transport = MQTTTransport()
        transport.connected = True

        import asyncio

        task = asyncio.create_task(transport.connection_monitor())
        await asyncio.sleep(0.05)
        task.cancel()

        # connection_monitor catches CancelledError and breaks cleanly
        await task  # should complete without raising
