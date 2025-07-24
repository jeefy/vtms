"""
Unit tests for configuration module
"""

import sys
import os
from unittest.mock import patch, mock_open
import io

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config, setDebug, getDebug, is_raspberrypi, config


class TestConfig:
    """Test cases for Config class"""
    
    def test_config_initialization(self):
        """Test Config class initialization with default values"""
        cfg = Config()
        
        assert cfg.debug is False
        assert cfg.mqtt_server == "192.168.50.24"
        assert cfg.mqtt_port == 1883
        assert cfg.mqtt_keepalive == 60
        assert cfg.obd_retry_delay == 15
        assert cfg.gps_update_interval == 1
    
    def test_debug_property(self):
        """Test debug property getter and setter"""
        cfg = Config()
        
        # Test initial value
        assert cfg.debug is False
        
        # Test setter
        cfg.debug = True
        assert cfg.debug is True
        
        cfg.debug = False
        assert cfg.debug is False
    
    def test_readonly_properties(self):
        """Test that configuration properties are read-only (except debug)"""
        cfg = Config()
        
        # These should not raise AttributeError since they're properties
        assert cfg.mqtt_server == "192.168.50.24"
        assert cfg.mqtt_port == 1883
        assert cfg.mqtt_keepalive == 60
        assert cfg.obd_retry_delay == 15
        assert cfg.gps_update_interval == 1
    
    @patch('builtins.open', new_callable=mock_open, read_data='raspberry pi 4 model b')
    def test_is_raspberrypi_true(self, mock_file):
        """Test is_raspberrypi returns True when on Raspberry Pi"""
        result = Config.is_raspberrypi()
        assert result is True
        mock_file.assert_called_once_with('/sys/firmware/devicetree/base/model', 'r')
    
    @patch('builtins.open', new_callable=mock_open, read_data='Generic x86_64 PC')
    def test_is_raspberrypi_false(self, mock_file):
        """Test is_raspberrypi returns False when not on Raspberry Pi"""
        result = Config.is_raspberrypi()
        assert result is False
    
    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_is_raspberrypi_exception(self, mock_file):
        """Test is_raspberrypi returns False when file doesn't exist"""
        result = Config.is_raspberrypi()
        assert result is False
    
    def test_legacy_functions(self):
        """Test legacy compatibility functions"""
        # Test setDebug and getDebug
        original_debug = getDebug()
        
        setDebug(True)
        assert getDebug() is True
        
        setDebug(False)
        assert getDebug() is False
        
        # Restore original state
        setDebug(original_debug)
    
    @patch('src.config.Config.is_raspberrypi')
    def test_legacy_is_raspberrypi(self, mock_static_method):
        """Test legacy is_raspberrypi function"""
        mock_static_method.return_value = True
        
        result = is_raspberrypi()
        assert result is True
        mock_static_method.assert_called_once()
    
    def test_global_config_instance(self):
        """Test that global config instance is properly exported"""
        assert config is not None
        assert isinstance(config, Config)
        assert hasattr(config, 'debug')
        assert hasattr(config, 'mqtt_server')


class TestConfigIntegration:
    """Integration tests for configuration module"""
    
    def test_config_state_persistence(self):
        """Test that config state persists across function calls"""
        original_debug = getDebug()
        
        # Change debug state
        setDebug(not original_debug)
        assert getDebug() == (not original_debug)
        
        # State should persist
        assert getDebug() == (not original_debug)
        
        # Restore original state
        setDebug(original_debug)
        assert getDebug() == original_debug
    
    def test_config_properties_immutability(self):
        """Test that configuration properties maintain their values"""
        cfg = Config()
        
        # Store original values
        original_server = cfg.mqtt_server
        original_port = cfg.mqtt_port
        original_keepalive = cfg.mqtt_keepalive
        
        # These values should remain constant
        assert cfg.mqtt_server == original_server
        assert cfg.mqtt_port == original_port
        assert cfg.mqtt_keepalive == original_keepalive
        
        # Create another instance - should have same values
        cfg2 = Config()
        assert cfg2.mqtt_server == original_server
        assert cfg2.mqtt_port == original_port
        assert cfg2.mqtt_keepalive == original_keepalive
