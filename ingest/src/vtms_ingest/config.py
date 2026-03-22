"""
Configuration for VTMS Ingest server.
"""

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    """Configuration for the MQTT → PostgreSQL ingest pipeline."""

    mqtt_server: str = "192.168.50.24"
    mqtt_port: int = 1883
    mqtt_keepalive: int = 60
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
        """Validate that Postgres credentials are set via env vars."""
        if not self.postgres_user:
            raise EnvironmentError("POSTGRES_USER environment variable is required")
        if not self.postgres_password:
            raise EnvironmentError("POSTGRES_PASSWORD environment variable is required")


config = Config()
