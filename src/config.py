"""
Configuration module for VTMS
"""

import io
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

def is_raspberrypi() -> bool:
    """Check if running on Raspberry Pi (legacy function)"""
    return Config.is_raspberrypi()

# Export the mqtt_server for backward compatibility
mqtt_server = _config.mqtt_server

# Export the config instance
config = _config