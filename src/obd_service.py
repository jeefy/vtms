"""
OBD-II service for VTMS

Handles OBD port scanning, connection, command watch registration,
incoming MQTT command handling, and connection monitoring.
"""

import asyncio
import logging
from functools import partial
from typing import Callable, Optional

import obd
from obd import OBDStatus

from . import myobd
from .config import config as vtms_config

logger = logging.getLogger(__name__)


class OBDService:
    """Manages the OBD-II connection and telemetry watches."""

    def __init__(self, publisher: Callable[..., object]):
        """
        Args:
            publisher: callable(topic, payload) used to emit telemetry
        """
        self.publisher = publisher
        self.connection: Optional[obd.Async] = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Scan serial ports and connect to the first available OBD adapter."""
        logger.info("Setting up OBD-II connection…")

        while True:
            ports = obd.scan_serial()
            logger.info(f"Possible ports: {ports}")

            if not ports:
                logger.warning("No OBD-II ports found. Sleeping then retrying…")
                await asyncio.sleep(vtms_config.obd_retry_delay)
                continue

            for port in ports:
                self.connection = obd.Async(
                    port,
                    timeout=5,
                    delay_cmds=0,
                    start_low_power=True,
                    fast=True,
                )
                if self.connection.status() is OBDStatus.CAR_CONNECTED:
                    logger.info(f"Connected to OBD-II on {port}")
                    return True
                logger.warning(f"No connection on {port}")

            logger.warning("No OBD-II connection on any port. Retrying…")
            await asyncio.sleep(vtms_config.obd_retry_delay)

    # ------------------------------------------------------------------
    # Watch registration
    # ------------------------------------------------------------------

    def setup_watches(self):
        """Register metric, monitor, and DTC watches on the connection."""
        if not self.connection:
            logger.error("OBD connection not established")
            return

        for cmd_name in myobd.metric_commands:
            if self.connection.supports(obd.commands[cmd_name]):
                logger.info(f"Watching metric: {cmd_name}")
                self.connection.watch(
                    obd.commands[cmd_name],
                    callback=partial(myobd.new_metric, publish=self.publisher),
                )

        for cmd_name in myobd.monitor_commands:
            if self.connection.supports(obd.commands[cmd_name]):
                logger.info(f"Watching monitor: {cmd_name}")
                self.connection.watch(
                    obd.commands[cmd_name],
                    callback=partial(myobd.new_monitor, publish=self.publisher),
                )

        self.connection.watch(
            obd.commands.GET_DTC,
            callback=partial(myobd.new_dtc, publish=self.publisher),
        )

    # ------------------------------------------------------------------
    # Message handling (from MQTT)
    # ------------------------------------------------------------------

    def handle_message(self, topic: str, payload: str):
        """Route an incoming MQTT command to the OBD connection."""
        if not self.connection:
            return

        if topic == "lemons/obd2/watch":
            if payload in obd.commands:
                with self.connection.paused():
                    self.connection.watch(
                        obd.commands[payload],
                        callback=partial(myobd.new_metric, publish=self.publisher),
                    )
        elif topic == "lemons/obd2/unwatch":
            if payload in obd.commands:
                with self.connection.paused():
                    self.connection.unwatch(obd.commands[payload])
        elif topic == "lemons/obd2/query":
            if payload in obd.commands:
                r = self.connection.query(obd.commands[payload])
                self._process_response(payload, r)

    def _process_response(self, command: str, response):
        """Dispatch a query response to the appropriate myobd handler."""
        if command in myobd.metric_commands:
            myobd.new_metric(response, publish=self.publisher)
        elif command in myobd.monitor_commands:
            myobd.new_monitor(response, publish=self.publisher)
        elif command == "GET_DTC":
            myobd.new_dtc(response, publish=self.publisher)
        else:
            if vtms_config.debug:
                logger.warning(
                    f'No handler for query "{command}" — defaulting to metric'
                )
            myobd.new_metric(response, publish=self.publisher)

    # ------------------------------------------------------------------
    # Monitoring loop
    # ------------------------------------------------------------------

    async def monitor(self):
        """Long-running task: connect, watch, and reconnect on failure."""
        try:
            if not await self.connect():
                logger.error("Failed to setup OBD-II connection")
                return

            self.setup_watches()
            self.connection.start()
            logger.info("OBD-II monitoring started")

            while True:
                await asyncio.sleep(10)
                if (
                    self.connection
                    and self.connection.status() != OBDStatus.CAR_CONNECTED
                ):
                    logger.warning("OBD-II connection lost, reconnecting…")
                    if not await self.connect():
                        await asyncio.sleep(30)
                    else:
                        self.setup_watches()
                        self.connection.start()

        except asyncio.CancelledError:
            logger.info("OBD-II monitoring cancelled")
            raise
        except Exception as e:
            logger.error(f"OBD-II monitoring error: {e}")

    def stop(self):
        """Stop the OBD connection."""
        if self.connection:
            self.connection.stop()
            logger.info("OBD-II connection stopped")
