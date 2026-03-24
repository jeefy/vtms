"""Tests for MQTT client wrapper.

Run on host with CPython/pytest.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


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
