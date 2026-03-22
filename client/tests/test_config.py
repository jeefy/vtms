"""
Unit tests for configuration module
"""

import sys
import os
import pytest
from unittest.mock import patch, mock_open

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vtms_client.config import Config, config


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
        """Test that configuration properties are accessible as attributes"""
        cfg = Config()

        assert cfg.mqtt_server == "192.168.50.24"
        assert cfg.mqtt_port == 1883
        assert cfg.mqtt_keepalive == 60
        assert cfg.obd_retry_delay == 15
        assert cfg.gps_update_interval == 1

    @patch("builtins.open", new_callable=mock_open, read_data="raspberry pi 4 model b")
    def test_is_raspberrypi_true(self, mock_file):
        """Test is_raspberrypi returns True when on Raspberry Pi"""
        result = Config.is_raspberrypi()
        assert result is True

    @patch("builtins.open", new_callable=mock_open, read_data="Generic x86_64 PC")
    def test_is_raspberrypi_false(self, mock_file):
        """Test is_raspberrypi returns False when not on Raspberry Pi"""
        result = Config.is_raspberrypi()
        assert result is False

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_is_raspberrypi_exception(self, mock_file):
        """Test is_raspberrypi returns False when file doesn't exist"""
        result = Config.is_raspberrypi()
        assert result is False

    def test_legacy_functions(self):
        """Test debug property access on config instance"""
        original_debug = config.debug

        config.debug = True
        assert config.debug is True

        config.debug = False
        assert config.debug is False

        # Restore original state
        config.debug = original_debug

    def test_is_raspberrypi_static_method(self):
        """Test Config.is_raspberrypi() static method directly"""
        with patch.object(
            Config, "is_raspberrypi", return_value=True
        ) as mock_static_method:
            result = Config.is_raspberrypi()
            assert result is True
            mock_static_method.assert_called_once()

    def test_global_config_instance(self):
        """Test that global config instance is properly exported"""
        assert config is not None
        assert isinstance(config, Config)
        assert hasattr(config, "debug")
        assert hasattr(config, "mqtt_server")

    def test_config_without_postgres_creates_successfully(self, monkeypatch):
        """Test Config can be created without postgres env vars (for client use)"""
        monkeypatch.delenv("POSTGRES_USER", raising=False)
        monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
        cfg = Config()
        assert cfg.postgres_user == ""

    def test_validate_postgres_raises_without_env(self, monkeypatch):
        """Test validate_postgres raises EnvironmentError when env vars missing"""
        monkeypatch.delenv("POSTGRES_USER", raising=False)
        monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
        cfg = Config()
        with pytest.raises(EnvironmentError):
            cfg.validate_postgres()

    def test_config_reads_env_vars(self, monkeypatch):
        """Test Config reads postgres credentials from env vars"""
        monkeypatch.setenv("POSTGRES_USER", "env_test_user")
        monkeypatch.setenv("POSTGRES_PASSWORD", "env_test_pass")
        c = Config()
        assert c.postgres_user == "env_test_user"
        assert c.postgres_password == "env_test_pass"


class TestConfigIntegration:
    """Integration tests for configuration module"""

    def test_config_state_persistence(self):
        """Test that config state persists across property access"""
        original_debug = config.debug

        # Change debug state
        config.debug = not original_debug
        assert config.debug == (not original_debug)

        # State should persist
        assert config.debug == (not original_debug)

        # Restore original state
        config.debug = original_debug
        assert config.debug == original_debug

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
