"""
MQTT transport layer for VTMS

Handles MQTT client setup, connection lifecycle, message publishing with
automatic buffering during disconnections, and connection monitoring.
"""

import asyncio
import json
import logging
import time
from collections import deque
from typing import Callable, Optional

import paho.mqtt.client as mqtt

from .config import config as vtms_config

logger = logging.getLogger(__name__)


class MQTTTransport:
    """Manages MQTT connectivity, publishing, and message buffering."""

    def __init__(
        self,
        on_message_callback: Optional[Callable] = None,
    ):
        self.mqttc: Optional[mqtt.Client] = None
        self.connected = False
        self.on_message_callback = on_message_callback

        # Buffering
        self.message_buffer: deque = deque(maxlen=1000)
        self.max_buffer_size = 1000

        # Reconnection state
        self.retry_count = 0
        self.max_retries = 10
        self.retry_delay = 5  # seconds

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Create the MQTT client and connect to the broker."""
        try:
            self.mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            self.mqttc.on_connect = self._on_connect
            self.mqttc.on_message = self._on_message
            self.mqttc.on_disconnect = self._on_disconnect
            self.mqttc.on_publish = self._on_publish

            self.mqttc.reconnect_delay_set(min_delay=1, max_delay=120)

            self.mqttc.connect(
                vtms_config.mqtt_server,
                vtms_config.mqtt_port,
                vtms_config.mqtt_keepalive,
            )
            logger.info(f"MQTT client connected to {vtms_config.mqtt_server}")
            return True
        except (ConnectionRefusedError, OSError) as e:
            logger.error(f"Failed to setup MQTT: {e}")
            return False

    def start(self):
        """Start the background network loop."""
        if self.mqttc:
            self.mqttc.loop_start()
            logger.info("MQTT background loop started")

    def stop(self):
        """Cleanly stop the MQTT client."""
        if self.mqttc:
            self.mqttc.loop_stop()
            self.mqttc.disconnect()
            logger.info("MQTT connection stopped")

    def reconnect(self) -> bool:
        """Tear down the existing client and reconnect from scratch.

        BUG FIX: previous code called setup_mqtt() but never called
        loop_start() after reconnection, leaving the client dead.
        """
        if self.mqttc:
            try:
                self.mqttc.loop_stop()
                self.mqttc.disconnect()
            except Exception:
                pass

        if self.connect():
            self.mqttc.loop_start()
            return True
        return False

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish(self, topic: str, payload, qos: int = 0, retain: bool = False) -> bool:
        """Publish a message, buffering automatically when disconnected."""
        try:
            if self.connected and self.mqttc:
                if isinstance(payload, dict):
                    payload = json.dumps(payload)
                elif not isinstance(payload, str):
                    payload = str(payload)

                result = self.mqttc.publish(topic, payload, qos, retain)
                if result.rc != 0:
                    logger.warning(
                        f"MQTT publish failed (rc={result.rc}), buffering message"
                    )
                    self._buffer_message(topic, payload, qos, retain)
                    return False
                return True
            else:
                self._buffer_message(topic, payload, qos, retain)
                return False
        except (ConnectionError, OSError, ValueError) as e:
            logger.error(f"Error publishing MQTT message: {e}")
            self._buffer_message(topic, payload, qos, retain)
            return False

    # ------------------------------------------------------------------
    # Buffering internals
    # ------------------------------------------------------------------

    def _buffer_message(self, topic: str, payload, qos: int = 0, retain: bool = False):
        try:
            while len(self.message_buffer) >= self.max_buffer_size:
                old = self.message_buffer.popleft()
                logger.warning(f"Dropping old buffered message to topic {old['topic']}")

            self.message_buffer.append(
                {
                    "topic": topic,
                    "payload": payload,
                    "qos": qos,
                    "retain": retain,
                    "timestamp": time.time(),
                }
            )
            logger.debug(
                f"Buffered message to {topic}, buffer size: {len(self.message_buffer)}"
            )
        except Exception as e:
            logger.error(f"Error buffering MQTT message: {e}")

    def _flush_message_buffer(self):
        if not self.connected or not self.mqttc or not self.message_buffer:
            return

        flushed = 0
        now = time.time()

        while self.message_buffer:
            msg = self.message_buffer.popleft()

            if now - msg["timestamp"] > 300:
                logger.warning(f"Dropping expired buffered message to {msg['topic']}")
                continue

            try:
                result = self.mqttc.publish(
                    msg["topic"], msg["payload"], msg["qos"], msg["retain"]
                )
                if result.rc == 0:
                    flushed += 1
                else:
                    self.message_buffer.appendleft(msg)
                    logger.warning("Failed to flush message, stopping buffer flush")
                    break
            except (ConnectionError, OSError) as e:
                self.message_buffer.appendleft(msg)
                logger.error(f"Error flushing buffered message: {e}")
                break

        if flushed:
            logger.info(f"Flushed {flushed} buffered messages to MQTT")

    # ------------------------------------------------------------------
    # Paho callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        try:
            if reason_code == 0:
                self.connected = True
                self.retry_count = 0
                logger.info(f"MQTT connected (rc={reason_code})")
                client.subscribe("lemons/#")
                self._flush_message_buffer()
            else:
                self.connected = False
                logger.error(f"MQTT connection failed (rc={reason_code})")
        except Exception as e:
            logger.error(f"Error in MQTT on_connect callback: {e}")

    def _on_disconnect(self, client, userdata, reason_code, properties):
        self.connected = False
        if reason_code != 0:
            logger.warning(f"MQTT disconnected unexpectedly (rc={reason_code})")
        else:
            logger.info("MQTT disconnected normally")

    def _on_publish(self, client, userdata, mid, reason_code, properties):
        if reason_code != 0:
            logger.warning(f"Message publish failed (rc={reason_code})")

    def _on_message(self, client, userdata, msg):
        if self.on_message_callback:
            self.on_message_callback(client, userdata, msg)

    # ------------------------------------------------------------------
    # Async connection monitor
    # ------------------------------------------------------------------

    async def connection_monitor(self):
        """Periodically check MQTT connectivity and reconnect if needed."""
        while True:
            try:
                await asyncio.sleep(30)

                if not self.connected:
                    self.retry_count += 1
                    logger.warning(
                        f"MQTT disconnected, attempting reconnection "
                        f"#{self.retry_count}"
                    )
                    await asyncio.sleep(min(self.retry_count * 2, 30))

                    if self.reconnect():
                        logger.info(
                            f"MQTT reconnected after {self.retry_count} attempts"
                        )
                    else:
                        logger.error("MQTT reconnection failed")
                else:
                    if self.retry_count > 0:
                        self.retry_count = 0

            except asyncio.CancelledError:
                logger.info("MQTT connection monitor cancelled")
                break
            except Exception as e:
                logger.error(f"Error in MQTT connection monitor: {e}")
                await asyncio.sleep(10)
