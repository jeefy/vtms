#!/usr/bin/env python3
"""
Vehicle Telemetry Management System (VTMS) Client

Thin orchestrator that wires together MQTTTransport, GPSService,
OBDService, and MQTTMessageRouter, then runs them concurrently.
"""

import asyncio
import logging
import time

from src import config
from src.mqtt_transport import MQTTTransport
from src.gps_service import GPSService
from src.obd_service import OBDService
from src.mqtt_handlers import (
    MQTTMessageRouter,
    create_debug_handler,
    create_flag_handler,
    create_pit_handler,
    create_message_handler,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class VTMSClient:
    """Main VTMS client — coordinates services, does no I/O itself."""

    def __init__(self):
        self.is_pi = config.Config.is_raspberrypi()
        self.led_handler = None

        # Message router
        self.message_router = MQTTMessageRouter()
        self._setup_message_handlers()

        # Services
        self.mqtt = MQTTTransport(on_message_callback=self._on_message)
        self.gps = GPSService(publisher=self.mqtt.publish)
        self.obd = OBDService(publisher=self.mqtt.publish)

        # LED support on Raspberry Pi
        if self.is_pi:
            try:
                from src import led

                self.led_handler = led
                self.led_handler.init()
                logger.info("LED support enabled for Raspberry Pi")
            except ImportError:
                logger.warning("LED module not available")

    # ------------------------------------------------------------------
    # Message routing
    # ------------------------------------------------------------------

    def _setup_message_handlers(self):
        """Register MQTT message handlers."""
        self.message_router.register_handler("lemons/debug", create_debug_handler())
        self.message_router.register_handler("lemons/message", create_message_handler())
        self.message_router.register_pattern_handler(
            "lemons/flag/", create_flag_handler()
        )

        pit_handler = create_pit_handler()
        self.message_router.register_handler("lemons/pit", pit_handler)
        self.message_router.register_handler("lemons/box", pit_handler)

    def _on_message(self, client, userdata, msg):
        """Top-level MQTT message callback — routes to handlers."""
        try:
            payload = str(msg.payload.decode("utf-8"))

            if config.config.debug:
                logger.info(f"{msg.topic}: {payload}")

            if self.is_pi and self.led_handler:
                self.led_handler.handler(msg, mqttc=client)

            # Try registered handlers first, fall back to OBD routing
            if not self.message_router.route_message(msg.topic, payload):
                self.obd.handle_message(msg.topic, payload)
        except Exception as e:
            logger.error(f"Error in MQTT message callback: {e}")

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def _health_check(self):
        """Periodic health-status publisher."""
        logger.info("Starting health check task")
        while True:
            try:
                await asyncio.sleep(60)
                if self.mqtt.connected:
                    health = {
                        "mqtt_connected": self.mqtt.connected,
                        "obd_connected": (
                            self.obd.connection is not None
                            and self.obd.connection.status().name == "CAR_CONNECTED"
                        ),
                        "timestamp": time.time(),
                    }
                    self.mqtt.publish("lemons/health", health)
            except asyncio.CancelledError:
                logger.info("Health check task cancelled")
                raise
            except Exception as e:
                logger.error(f"Health check error: {e}")

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    async def run(self):
        """Start all services and wait for completion or interruption."""
        logger.info("Starting VTMS Client…")

        if not self.mqtt.connect():
            logger.error("Failed to setup MQTT connection")
            return False

        self.mqtt.start()

        tasks = []

        if config.config.gps_enabled:
            tasks.append(asyncio.create_task(self.gps.monitor()))
            logger.info("GPS monitoring task started")
        else:
            logger.info("GPS monitoring disabled by configuration")

        tasks.append(asyncio.create_task(self.obd.monitor()))
        logger.info("OBD-II monitoring task started")

        tasks.append(asyncio.create_task(self.mqtt.connection_monitor()))
        logger.info("MQTT connection monitor task started")

        tasks.append(asyncio.create_task(self._health_check()))
        logger.info("Health check task started")

        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except KeyboardInterrupt:
            logger.info("Shutting down VTMS Client…")
        finally:
            logger.info("Cleaning up resources…")

            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            self.obd.stop()
            self.gps.close()
            self.mqtt.stop()


def main():
    """Main entry point."""
    client = VTMSClient()
    asyncio.run(client.run())


if __name__ == "__main__":
    main()
