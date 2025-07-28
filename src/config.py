"""
Configuration module for VTMS
"""

import io, os
from typing import Optional


class Config:
    """Configuration class for VTMS settings"""
    
    def __init__(self):
        self._debug = False
        self._mqtt_server = "192.168.50.24"
        self._mqtt_port = 1883
        self._mqtt_keepalive = 60
        self._obd_retry_delay = 15
        self._gps_update_interval = 1
        self._gps_port = None  # Auto-discover if None
        self._gps_baudrate = 9600
        self._gps_enabled = True
        
        # PostgreSQL configuration
        self._postgres_host = "my-release-postgresql.monitoring.svc.cluster.local"
        self._postgres_port = 5432
        self._postgres_database = "vtms"
        self._postgres_user = os.environ.get("POSTGRES_USER", "default_user")  # Use environment variable or default
        self._postgres_password = os.environ.get("POSTGRES_PASSWORD", "default_password")  # Use environment variable or default
    
    @property
    def debug(self) -> bool:
        return self._debug
    
    @debug.setter
    def debug(self, value: bool):
        self._debug = value
    
    @property
    def mqtt_server(self) -> str:
        return self._mqtt_server
    
    @property
    def mqtt_port(self) -> int:
        return self._mqtt_port
    
    @property
    def mqtt_keepalive(self) -> int:
        return self._mqtt_keepalive
    
    @property
    def obd_retry_delay(self) -> int:
        return self._obd_retry_delay
    
    @property
    def gps_update_interval(self) -> int:
        return self._gps_update_interval
    
    @property
    def gps_port(self) -> Optional[str]:
        return self._gps_port
    
    @gps_port.setter
    def gps_port(self, value: Optional[str]):
        self._gps_port = value
    
    @property
    def gps_baudrate(self) -> int:
        return self._gps_baudrate
    
    @gps_baudrate.setter
    def gps_baudrate(self, value: int):
        self._gps_baudrate = value
    
    @property
    def gps_enabled(self) -> bool:
        return self._gps_enabled
    
    @gps_enabled.setter
    def gps_enabled(self, value: bool):
        self._gps_enabled = value
    
    @property
    def postgres_host(self) -> str:
        return self._postgres_host
    
    @postgres_host.setter
    def postgres_host(self, value: str):
        self._postgres_host = value
    
    @property
    def postgres_port(self) -> int:
        return self._postgres_port
    
    @postgres_port.setter
    def postgres_port(self, value: int):
        self._postgres_port = value
    
    @property
    def postgres_database(self) -> str:
        return self._postgres_database
    
    @postgres_database.setter
    def postgres_database(self, value: str):
        self._postgres_database = value
    
    @property
    def postgres_user(self) -> str:
        return self._postgres_user
    
    @postgres_user.setter
    def postgres_user(self, value: str):
        self._postgres_user = value
    
    @property
    def postgres_password(self) -> str:
        return self._postgres_password
    
    @postgres_password.setter
    def postgres_password(self, value: str):
        self._postgres_password = value

    @staticmethod
    def is_raspberrypi() -> bool:
        """Check if running on Raspberry Pi"""
        try:
            with io.open('/sys/firmware/devicetree/base/model', 'r') as m:
                if 'raspberry pi' in m.read().lower():
                    return True
        except Exception:
            pass
        return False


# Global configuration instance
_config = Config()

# Legacy functions for backward compatibility
def setDebug(val: bool):
    """Set debug mode (legacy function)"""
    _config.debug = val

def getDebug() -> bool:
    """Get debug mode (legacy function)"""
    return _config.debug

def getGpsEnabled() -> bool:
    """Get GPS enabled status (legacy function)"""
    return _config.gps_enabled

def getObdEnabled() -> bool:
    """Get OBD enabled status (legacy function)"""
    return True  # OBD is always enabled by default

def is_raspberrypi() -> bool:
    """Check if running on Raspberry Pi (legacy function)"""
    return Config.is_raspberrypi()

# Export the mqtt_server for backward compatibility
mqtt_server = _config.mqtt_server

# Export the config instance
config = _config