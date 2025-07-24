"""
Test configuration and fixtures for VTMS tests
"""

from unittest.mock import Mock, MagicMock, patch
from obd import OBDStatus
import paho.mqtt.client as mqtt


class MockOBDResponse:
    """Mock OBD response object"""
    
    def __init__(self, command_name, value=None, is_null=False):
        self.command = Mock()
        self.command.name = command_name
        self.value = value
        self._is_null = is_null
    
    def is_null(self):
        return self._is_null


class MockOBDAsync:
    """Mock OBD Async connection"""
    
    def __init__(self, port=None, **kwargs):
        self.port = port
        self._status = OBDStatus.CAR_CONNECTED
        self.watched_commands = {}
        self.supported_commands = set()
        
    def status(self):
        return self._status
    
    def set_status(self, status):
        self._status = status
    
    def supports(self, command):
        return command in self.supported_commands
    
    def add_supported_command(self, command):
        self.supported_commands.add(command)
    
    def watch(self, command, callback):
        self.watched_commands[command] = callback
    
    def unwatch(self, command):
        if command in self.watched_commands:
            del self.watched_commands[command]
    
    def query(self, command):
        # Return a mock response
        return MockOBDResponse(command.name, "test_value")
    
    def start(self):
        pass
    
    def stop(self):
        pass
    
    def paused(self):
        return MockContextManager()


class MockContextManager:
    """Mock context manager for OBD paused operations"""
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockMQTTClient:
    """Mock MQTT client"""
    
    def __init__(self, api_version=None):
        self.connected = False
        self.subscriptions = []
        self.published_messages = []
        self.on_connect = None
        self.on_message = None
        
    def connect(self, host, port, keepalive):
        self.connected = True
        if self.on_connect:
            # Simulate successful connection
            self.on_connect(self, None, None, 0, None)
    
    def disconnect(self):
        self.connected = False
    
    def subscribe(self, topic):
        self.subscriptions.append(topic)
    
    def publish(self, topic, payload):
        self.published_messages.append((topic, payload))
    
    def loop_start(self):
        pass
    
    def loop_stop(self):
        pass
    
    def loop_forever(self):
        pass
    
    def simulate_message(self, topic, payload):
        """Simulate receiving a message"""
        if self.on_message:
            msg = Mock()
            msg.topic = topic
            msg.payload = Mock()
            msg.payload.decode.return_value = payload
            self.on_message(self, None, msg)


class MockGPSPacket:
    """Mock GPS packet"""
    
    def __init__(self, pos=(40.7128, -74.0060), speed=25.5, altitude=100.0, track=180.0):
        self._position = pos
        self._speed = speed
        self._altitude = altitude
        self._track = track
    
    def position(self):
        return self._position
    
    def speed(self):
        return self._speed
    
    def altitude(self):
        return self._altitude
    
    def track(self):
        return self._track


# Factory functions for creating test objects (can be used with or without pytest)
def create_mock_obd_async():
    """Factory function for mock OBD async connection"""
    return MockOBDAsync()


def create_mock_mqtt_client():
    """Factory function for mock MQTT client"""
    return MockMQTTClient()


def create_mock_gps_packet():
    """Factory function for mock GPS packet"""
    return MockGPSPacket()


def create_mock_config():
    """Factory function for mock config"""
    mock_cfg = Mock()
    mock_cfg.mqtt_port = 1883
    mock_cfg.mqtt_keepalive = 60
    mock_cfg.obd_retry_delay = 15
    mock_cfg.gps_update_interval = 1
    return mock_cfg


# Optional pytest fixtures (only available if pytest is installed)
try:
    import pytest
    
    @pytest.fixture
    def mock_obd_async():
        """Fixture for mock OBD async connection"""
        return MockOBDAsync()

    @pytest.fixture
    def mock_mqtt_client():
        """Fixture for mock MQTT client"""
        return MockMQTTClient()

    @pytest.fixture
    def mock_gps_packet():
        """Fixture for mock GPS packet"""
        return MockGPSPacket()

    @pytest.fixture
    def mock_config():
        """Fixture for mock config"""
        with patch('src.config.config') as mock_cfg:
            mock_cfg.mqtt_port = 1883
            mock_cfg.mqtt_keepalive = 60
            mock_cfg.obd_retry_delay = 15
            mock_cfg.gps_update_interval = 1
            yield mock_cfg
            
except ImportError:
    # pytest not available, fixtures won't be available
    pass
