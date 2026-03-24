"""Tests for mqtt_bridge.py: MQTT bridge for SDR StateManager."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch, call

import pytest


class TestMqttBridgeImport:
    """Test MqttBridge is importable."""

    def test_can_import(self):
        from vtms_sdr.mqtt_bridge import MqttBridge


class TestMqttBridgeInit:
    """Test MqttBridge construction."""

    def test_accepts_state_manager(self):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost")
        assert bridge._state_manager is sm

    def test_default_prefix(self):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost")
        assert bridge._prefix == "lemons/"

    def test_custom_prefix(self):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost", prefix="test/")
        assert bridge._prefix == "test/"

    def test_prefix_trailing_slash_added(self):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost", prefix="test")
        assert bridge._prefix == "test/"

    def test_default_port(self):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost")
        assert bridge._port == 1883


class TestMqttBridgeStatePublishing:
    """Test that state changes are published to MQTT topics."""

    @patch("vtms_sdr.mqtt_bridge.mqtt.Client")
    def test_publishes_scalar_as_string(self, MockClient):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        mock_client = MockClient.return_value
        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost", prefix="lemons/")
        bridge.start()

        sm.update("freq", 146_520_000)

        mock_client.publish.assert_called_with(
            "lemons/sdr/state/freq", "146520000", retain=True
        )

    @patch("vtms_sdr.mqtt_bridge.mqtt.Client")
    def test_publishes_dict_as_json(self, MockClient):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        mock_client = MockClient.return_value
        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost", prefix="lemons/")
        bridge.start()

        data = {"text": "hello", "ts": 1.0}
        sm.update("last_transcription", data)

        call_args = mock_client.publish.call_args
        assert call_args[0][0] == "lemons/sdr/state/last_transcription"
        assert json.loads(call_args[0][1]) == data
        assert call_args[1]["retain"] is True

    @patch("vtms_sdr.mqtt_bridge.mqtt.Client")
    def test_publishes_list_as_json(self, MockClient):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        mock_client = MockClient.return_value
        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost", prefix="lemons/")
        bridge.start()

        items = [1, 2, 3]
        sm.update("scan_results", items)

        call_args = mock_client.publish.call_args
        assert json.loads(call_args[0][1]) == items

    @patch("vtms_sdr.mqtt_bridge.mqtt.Client")
    def test_publishes_float_as_string(self, MockClient):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        mock_client = MockClient.return_value
        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost", prefix="lemons/")
        bridge.start()

        sm.update("squelch_db", -25.5)

        mock_client.publish.assert_called_with(
            "lemons/sdr/state/squelch_db", "-25.5", retain=True
        )


class TestMqttBridgeSignalDebounce:
    """Test signal_power debounce to max 5 Hz."""

    @patch("vtms_sdr.mqtt_bridge.mqtt.Client")
    def test_signal_power_debounced(self, MockClient):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        mock_client = MockClient.return_value
        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost", prefix="lemons/")
        bridge.start()

        # Rapid-fire signal_power updates
        for i in range(20):
            sm.update("signal_power", float(-50 + i))

        # Should have published fewer than 20 times due to debounce
        signal_calls = [
            c
            for c in mock_client.publish.call_args_list
            if c[0][0] == "lemons/sdr/state/signal_power"
        ]
        # First call always goes through, rest are debounced
        assert len(signal_calls) < 20
        assert len(signal_calls) >= 1

    @patch("vtms_sdr.mqtt_bridge.mqtt.Client")
    def test_non_signal_power_not_debounced(self, MockClient):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        mock_client = MockClient.return_value
        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost", prefix="lemons/")
        bridge.start()

        for i in range(5):
            sm.update("freq", 146_520_000 + i)

        freq_calls = [
            c
            for c in mock_client.publish.call_args_list
            if c[0][0] == "lemons/sdr/state/freq"
        ]
        assert len(freq_calls) == 5


class TestMqttBridgeControlSubscription:
    """Test control command dispatch from MQTT."""

    @patch("vtms_sdr.mqtt_bridge.mqtt.Client")
    def test_subscribes_to_control_topic(self, MockClient):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        mock_client = MockClient.return_value
        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost", prefix="lemons/")
        bridge.start()

        # Simulate on_connect callback
        bridge._on_connect(mock_client, None, None, MagicMock(), None)

        mock_client.subscribe.assert_called_with("lemons/sdr/control/#")

    @patch("vtms_sdr.mqtt_bridge.mqtt.Client")
    def test_control_message_dispatched(self, MockClient):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        mock_client = MockClient.return_value
        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost", prefix="lemons/")

        received = []
        sm.on_control(lambda a, v: received.append((a, v)))
        bridge.start()

        # Simulate incoming MQTT control message
        msg = MagicMock()
        msg.topic = "lemons/sdr/control/set_freq"
        msg.payload = b"146520000"
        bridge._on_message(mock_client, None, msg)

        assert received == [("set_freq", 146520000)]

    @patch("vtms_sdr.mqtt_bridge.mqtt.Client")
    def test_control_json_payload_parsed(self, MockClient):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        mock_client = MockClient.return_value
        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost", prefix="lemons/")

        received = []
        sm.on_control(lambda a, v: received.append((a, v)))
        bridge.start()

        msg = MagicMock()
        msg.topic = "lemons/sdr/control/set_config"
        msg.payload = json.dumps({"gain": 40, "ppm": 5}).encode()
        bridge._on_message(mock_client, None, msg)

        assert len(received) == 1
        assert received[0][0] == "set_config"
        assert received[0][1] == {"gain": 40, "ppm": 5}

    @patch("vtms_sdr.mqtt_bridge.mqtt.Client")
    def test_ignores_non_control_topics(self, MockClient):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        mock_client = MockClient.return_value
        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost", prefix="lemons/")

        received = []
        sm.on_control(lambda a, v: received.append((a, v)))
        bridge.start()

        msg = MagicMock()
        msg.topic = "lemons/sdr/state/freq"
        msg.payload = b"146520000"
        bridge._on_message(mock_client, None, msg)

        assert received == []


class TestMqttBridgeLifecycle:
    """Test start/stop lifecycle."""

    @patch("vtms_sdr.mqtt_bridge.mqtt.Client")
    def test_start_connects_and_loops(self, MockClient):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        mock_client = MockClient.return_value
        sm = StateManager()
        bridge = MqttBridge(sm, broker="mybroker", port=1884)
        bridge.start()

        mock_client.connect.assert_called_once_with("mybroker", 1884)
        mock_client.loop_start.assert_called_once()

    @patch("vtms_sdr.mqtt_bridge.mqtt.Client")
    def test_stop_disconnects(self, MockClient):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        mock_client = MockClient.return_value
        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost")
        bridge.start()
        bridge.stop()

        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()

    @patch("vtms_sdr.mqtt_bridge.mqtt.Client")
    def test_stop_without_start_is_safe(self, MockClient):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost")
        bridge.stop()  # Should not raise

    @patch("vtms_sdr.mqtt_bridge.mqtt.Client")
    def test_double_start_is_safe(self, MockClient):
        from vtms_sdr.mqtt_bridge import MqttBridge
        from vtms_sdr.state import StateManager

        mock_client = MockClient.return_value
        sm = StateManager()
        bridge = MqttBridge(sm, broker="localhost")
        bridge.start()
        bridge.start()

        # connect should only be called once
        assert mock_client.connect.call_count == 1
