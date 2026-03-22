"""
GPS service for VTMS

Handles GPS port discovery, serial connection, NMEA sentence parsing,
and publishing GPS telemetry via a provided publish callback.
"""

import asyncio
import logging
import time
from typing import Callable, Optional

import pygeohash

try:
    import pynmea2
    import serial
    import serial.tools.list_ports

    GPS_AVAILABLE = True
except ImportError:
    pynmea2 = None
    serial = None
    GPS_AVAILABLE = False
    logging.warning("pynmea2 or pyserial not available — GPS functionality disabled")

from .config import config as vtms_config

logger = logging.getLogger(__name__)

# Common GPS device name patterns (USB CDC-ACM)
GPS_PORT_PATTERNS = ["ttyACM"]


class GPSService:
    """Discovers, connects to, and streams data from a GPS receiver."""

    def __init__(self, publisher: Callable[..., object]):
        """
        Args:
            publisher: callable(topic, payload) used to emit telemetry
        """
        self.publisher = publisher
        self.gps_serial = None
        self.gps_port: Optional[str] = vtms_config.gps_port
        self.gps_baudrate: int = vtms_config.gps_baudrate

    # ------------------------------------------------------------------
    # Port discovery
    # ------------------------------------------------------------------

    @staticmethod
    def discover_ports() -> list[str]:
        """Return serial ports that look like GPS devices."""
        if not GPS_AVAILABLE:
            return []

        ports = serial.tools.list_ports.comports()
        found = []
        for port in ports:
            for pattern in GPS_PORT_PATTERNS:
                if pattern in port.device:
                    found.append(port.device)
                    logger.info(
                        f"Found potential GPS port: {port.device} — {port.description}"
                    )
        return found

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Try to open and validate a GPS serial connection."""
        if not GPS_AVAILABLE:
            logger.warning("GPS disabled — pynmea2 or pyserial not available")
            return False

        logger.info("Setting up GPS connection…")

        candidates = [self.gps_port] if self.gps_port else self.discover_ports()
        if not candidates:
            logger.warning("No potential GPS ports found")
            return False

        for port in candidates:
            try:
                logger.info(f"Attempting GPS connection on {port}")
                self.gps_serial = serial.Serial(
                    port,
                    self.gps_baudrate,
                    timeout=2,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    bytesize=serial.EIGHTBITS,
                )

                valid_lines = 0
                for _ in range(10):
                    try:
                        line = (
                            self.gps_serial.readline()
                            .decode("ascii", errors="ignore")
                            .strip()
                        )
                        if line.startswith("$") and "," in line:
                            valid_lines += 1
                            if valid_lines >= 2:
                                self.gps_port = port
                                logger.info(f"GPS connected on {port}")
                                return True
                    except (OSError, UnicodeDecodeError):
                        continue

                self.gps_serial.close()
                self.gps_serial = None
                logger.warning(f"No valid NMEA data on {port}")

            except (OSError, ValueError) as e:
                logger.warning(f"Failed to connect GPS on {port}: {e}")
                if self.gps_serial:
                    try:
                        self.gps_serial.close()
                    except OSError:
                        pass
                    self.gps_serial = None

        logger.error("Failed to establish GPS connection on any port")
        return False

    # ------------------------------------------------------------------
    # Monitoring loop
    # ------------------------------------------------------------------

    async def monitor(self):
        """Long-running task: read NMEA, publish GPS topics."""
        logger.info("Starting GPS monitoring")

        if not GPS_AVAILABLE:
            logger.warning("GPS monitoring disabled — libraries unavailable")
            while True:
                await asyncio.sleep(60)

        if not await self.connect():
            logger.error("GPS setup failed, monitoring disabled")
            while True:
                await asyncio.sleep(60)

        logger.info("GPS monitoring started")

        last: dict = {
            "latitude": None,
            "longitude": None,
            "altitude": None,
            "speed": None,
            "track": None,
            "timestamp": None,
        }

        while True:
            try:
                if not self.gps_serial or not self.gps_serial.is_open:
                    logger.warning("GPS connection lost, reconnecting…")
                    if not await self.connect():
                        await asyncio.sleep(5)
                        continue

                try:
                    line = (
                        self.gps_serial.readline()
                        .decode("ascii", errors="ignore")
                        .strip()
                    )
                    if not line.startswith("$"):
                        continue

                    try:
                        msg = pynmea2.parse(line)
                        self._update_last(last, msg)
                    except (pynmea2.ParseError, ValueError) as e:
                        if vtms_config.debug:
                            logger.debug(f"NMEA parse error: {line} — {e}")
                        continue

                except OSError as e:
                    logger.error(f"Error reading GPS: {e}")
                    await asyncio.sleep(5)
                    continue

                self._publish_position(last)

            except Exception as e:
                logger.error(f"GPS error: {e}")
                await asyncio.sleep(5)
                continue

            await asyncio.sleep(5)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _update_last(last: dict, msg) -> None:
        """Update the last-known GPS state from a parsed NMEA message."""
        if hasattr(msg, "latitude") and hasattr(msg, "longitude"):
            if msg.latitude and msg.longitude:
                last["latitude"] = float(msg.latitude)
                last["longitude"] = float(msg.longitude)
                last["timestamp"] = time.time()

        if hasattr(msg, "altitude") and msg.altitude:
            last["altitude"] = float(msg.altitude)

        if hasattr(msg, "spd_over_grnd") and msg.spd_over_grnd:
            last["speed"] = float(msg.spd_over_grnd) * 0.514444  # knots → m/s

        if hasattr(msg, "true_course") and msg.true_course:
            last["track"] = float(msg.true_course)

    def _publish_position(self, last: dict) -> None:
        """Publish GPS data if we have a valid fix."""
        if last["latitude"] is None or last["longitude"] is None:
            return

        geohash = pygeohash.encode(last["latitude"], last["longitude"], precision=12)

        topics = {
            "lemons/gps/pos": f"{last['latitude']},{last['longitude']}",
            "lemons/gps/latitude": str(last["latitude"]),
            "lemons/gps/longitude": str(last["longitude"]),
            "lemons/gps/geohash": geohash,
        }

        if last["speed"] is not None:
            topics["lemons/gps/speed"] = str(last["speed"])
        if last["altitude"] is not None:
            topics["lemons/gps/altitude"] = str(last["altitude"])
        if last["track"] is not None:
            topics["lemons/gps/track"] = str(last["track"])

        count = 0
        for topic, value in topics.items():
            if value and value != "None":
                self.publisher(topic, value)
                count += 1

        if vtms_config.debug:
            logger.debug(
                f"GPS: {count} topics, pos={last['latitude']},{last['longitude']}"
            )

    def close(self):
        """Close the GPS serial port."""
        if self.gps_serial and self.gps_serial.is_open:
            self.gps_serial.close()
            logger.info("GPS connection closed")
