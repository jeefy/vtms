"""
Configuration module for VTMS
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """Configuration for VTMS settings"""

    debug: bool = False
    mqtt_server: str = "192.168.50.24"
    mqtt_port: int = 1883
    mqtt_keepalive: int = 60
    obd_retry_delay: int = 15
    gps_update_interval: int = 1
    gps_port: Optional[str] = None
    gps_baudrate: int = 9600
    gps_enabled: bool = True
    postgres_host: str = "my-release-postgresql.monitoring.svc.cluster.local"
    postgres_port: int = 5432
    postgres_database: str = "vtms"
    postgres_user: str = field(
        default_factory=lambda: os.environ.get("POSTGRES_USER", "")
    )
    postgres_password: str = field(
        default_factory=lambda: os.environ.get("POSTGRES_PASSWORD", "")
    )

    def validate_postgres(self):
        """Validate Postgres config. Call from server.py only."""
        if not self.postgres_user:
            raise EnvironmentError("POSTGRES_USER environment variable is required")
        if not self.postgres_password:
            raise EnvironmentError("POSTGRES_PASSWORD environment variable is required")

    @staticmethod
    def is_raspberrypi() -> bool:
        """Check if running on Raspberry Pi"""
        try:
            with open("/sys/firmware/devicetree/base/model", "r") as m:
                if "raspberry pi" in m.read().lower():
                    return True
        except Exception:
            pass
        return False


# Global configuration instance
config = Config()
