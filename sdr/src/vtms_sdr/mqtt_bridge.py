"""MQTT bridge for SDR StateManager.

Publishes state updates to ``{prefix}sdr/state/{key}`` topics with retain,
and subscribes to ``{prefix}sdr/control/#`` for control commands back to
the session.  Debounces ``signal_power`` to max 5 Hz.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import paho.mqtt.client as mqtt

from .state import StateManager

logger = logging.getLogger(__name__)

__all__ = ["MqttBridge"]

# Minimum interval between signal_power publishes (200 ms = 5 Hz)
_SIGNAL_POWER_MIN_INTERVAL = 0.2


class MqttBridge:
    """Bridges a :class:`StateManager` to an MQTT broker.

    - State changes → published to ``{prefix}sdr/state/{key}``
    - Control messages from ``{prefix}sdr/control/{action}`` → dispatched
      to StateManager control handlers
    """

    def __init__(
        self,
        state_manager: StateManager,
        *,
        broker: str,
        port: int = 1883,
        prefix: str = "lemons/",
    ) -> None:
        self._state_manager = state_manager
        self._broker = broker
        self._port = port
        self._prefix = prefix if prefix.endswith("/") else prefix + "/"
        self._client: mqtt.Client | None = None
        self._started = False
        self._unsubscribe: Any = None
        self._last_signal_power_time: float = 0.0

    def start(self) -> None:
        """Connect to the broker and begin bridging state/control."""
        if self._started:
            return

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(self._broker, self._port)
        self._client.loop_start()

        # Subscribe to state changes
        self._unsubscribe = self._state_manager.subscribe(self._on_state_change)
        self._started = True

    def stop(self) -> None:
        """Disconnect from the broker and stop bridging."""
        if not self._started:
            return

        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None

        self._started = False

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        """Subscribe to control topics on (re)connect."""
        control_topic = f"{self._prefix}sdr/control/#"
        client.subscribe(control_topic)
        logger.info("Subscribed to %s", control_topic)

    def _on_message(self, client, userdata, msg) -> None:
        """Handle incoming MQTT control messages."""
        control_prefix = f"{self._prefix}sdr/control/"
        if not msg.topic.startswith(control_prefix):
            return

        action = msg.topic[len(control_prefix) :]
        payload_str = msg.payload.decode("utf-8", errors="replace")

        # Try to parse as JSON for structured payloads
        try:
            value = json.loads(payload_str)
        except (json.JSONDecodeError, ValueError):
            value = payload_str

        logger.debug("Control command: %s = %r", action, value)
        self._state_manager.dispatch_control(action, value)

    def _on_state_change(self, key: str, value: Any) -> None:
        """Publish state change to MQTT, debouncing signal_power."""
        if self._client is None:
            return

        # Debounce signal_power to max 5 Hz
        if key == "signal_power":
            now = time.monotonic()
            if now - self._last_signal_power_time < _SIGNAL_POWER_MIN_INTERVAL:
                return
            self._last_signal_power_time = now

        topic = f"{self._prefix}sdr/state/{key}"

        # Serialize: JSON for complex types, str() for scalars
        if isinstance(value, (dict, list)):
            payload = json.dumps(value)
        else:
            payload = str(value)

        self._client.publish(topic, payload, retain=True)
