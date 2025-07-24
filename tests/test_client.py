"""
Unit tests for VTMS Client
"""

import asyncio
import pytest
import sys
import os
import json
import time
from unittest.mock import Mock, MagicMock, patch, call
from obd import OBDStatus
from collections import deque

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client import VTMSClient, MQTTWrapper
from src.config import Config
from tests.conftest import MockOBDAsync, MockMQTTClient, MockGPSPacket


class TestVTMSClient:
    """Test cases for VTMSClient class"""
    
    @patch('src.config.is_raspberrypi')
    @patch('client.logger')
    def test_init_not_raspberry_pi(self, mock_logger, mock_is_pi):
        """Test VTMSClient initialization when not on Raspberry Pi"""
        mock_is_pi.return_value = False
        
        client = VTMSClient()
        
        assert client.mqttc is None
        assert client.obd_connection is None
        assert client.is_pi is False
        assert client.led_handler is None
        assert client.message_router is not None
    
    @patch('src.config.is_raspberrypi')
    @patch('client.logger')
    def test_init_raspberry_pi_with_led(self, mock_logger, mock_is_pi):
        """Test VTMSClient initialization on Raspberry Pi with LED support"""
        mock_is_pi.return_value = True
        
        # Mock the LED module import
        with patch.dict('sys.modules', {'src.led': Mock()}):
            client = VTMSClient()
            
            assert client.is_pi is True
            assert client.led_handler is not None
            mock_logger.info.assert_called_with("LED support enabled for Raspberry Pi")
    
    @patch('src.config.is_raspberrypi')
    @patch('client.logger')
    def test_init_raspberry_pi_without_led(self, mock_logger, mock_is_pi):
        """Test VTMSClient initialization on Raspberry Pi without LED support"""
        mock_is_pi.return_value = True
        
        # Mock ImportError for LED module
        with patch('builtins.__import__', side_effect=ImportError):
            client = VTMSClient()
            
            assert client.is_pi is True
            assert client.led_handler is None
            mock_logger.warning.assert_called_with("LED module not available")
    
    def test_setup_message_handlers(self):
        """Test message handler setup"""
        with patch('src.config.is_raspberrypi', return_value=False):
            client = VTMSClient()
            
            # Check that handlers are registered
            assert 'lemons/debug' in client.message_router.handlers
            assert 'lemons/message' in client.message_router.handlers
            assert 'lemons/pit' in client.message_router.handlers
            assert 'lemons/box' in client.message_router.handlers
            assert 'lemons/flag/' in client.message_router.pattern_handlers
    
    @patch('paho.mqtt.client.Client')
    @patch('src.config.mqtt_server', 'test.mqtt.server')
    @patch('src.config.config')
    @patch('client.logger')
    def test_setup_mqtt_success(self, mock_logger, mock_config, mock_mqtt_class):
        """Test successful MQTT setup"""
        mock_config.mqtt_port = 1883
        mock_config.mqtt_keepalive = 60
        
        mock_client = MockMQTTClient()
        mock_mqtt_class.return_value = mock_client
        
        with patch('src.config.is_raspberrypi', return_value=False):
            client = VTMSClient()
            result = client.setup_mqtt()
            
            assert result is True
            assert client.mqttc is not None
            mock_logger.info.assert_called_with("MQTT client connected to test.mqtt.server")
    
    @patch('paho.mqtt.client.Client')
    @patch('client.logger')
    def test_setup_mqtt_failure(self, mock_logger, mock_mqtt_class):
        """Test MQTT setup failure"""
        mock_mqtt_class.side_effect = Exception("Connection failed")
        
        with patch('src.config.is_raspberrypi', return_value=False):
            client = VTMSClient()
            result = client.setup_mqtt()
            
            assert result is False
            mock_logger.error.assert_called_with("Failed to setup MQTT: Connection failed")
    
    @patch('gpsd2.connect')
    @patch('gpsd2.get_current')
    @patch('src.config.getDebug')
    @patch('client.logger')
    async def test_start_gps_monitoring_success(self, mock_logger, mock_debug, mock_get_current, mock_connect):
        """Test GPS monitoring with successful data collection"""
        mock_debug.return_value = True
        mock_gps_packet = MockGPSPacket()
        mock_get_current.return_value = mock_gps_packet
        
        with patch('src.config.is_raspberrypi', return_value=False):
            client = VTMSClient()
            client.mqttc = MockMQTTClient()
            
            # Create a task that will run for a short time
            task = asyncio.create_task(client.start_gps_monitoring())
            
            # Let it run for a short time
            await asyncio.sleep(0.1)
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            # Verify GPS data was published
            published = client.mqttc.published_messages
            assert len(published) > 0
            
            # Check specific topics were published
            topics = [msg[0] for msg in published]
            assert "lemons/gps/pos" in topics
            assert "lemons/gps/speed" in topics
            assert "lemons/gps/altitude" in topics
            assert "lemons/gps/track" in topics
    
    @patch('gpsd2.connect')
    @patch('gpsd2.get_current')
    @patch('client.logger')
    async def test_start_gps_monitoring_error(self, mock_logger, mock_get_current, mock_connect):
        """Test GPS monitoring with error handling"""
        mock_connect.side_effect = Exception("GPS connection failed")
        
        with patch('src.config.is_raspberrypi', return_value=False):
            client = VTMSClient()
            client.mqttc = MockMQTTClient()
            
            # Create a task that will run for a short time
            task = asyncio.create_task(client.start_gps_monitoring())
            
            # Let it run for a short time
            await asyncio.sleep(0.1)
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            # Verify error was logged
            mock_logger.error.assert_called()
    
    def test_on_connect_callback(self):
        """Test MQTT on_connect callback"""
        with patch('src.config.is_raspberrypi', return_value=False):
            client = VTMSClient()
            
            mock_client = Mock()
            client._on_connect(mock_client, None, None, 0, None)
            
            mock_client.subscribe.assert_called_once_with("lemons/#")
    
    @patch('src.config.getDebug')
    @patch('client.logger')
    def test_on_message_callback(self, mock_logger, mock_debug):
        """Test MQTT on_message callback"""
        mock_debug.return_value = True
        
        with patch('src.config.is_raspberrypi', return_value=False):
            client = VTMSClient()
            client.mqttc = MockMQTTClient()
            
            # Mock message
            msg = Mock()
            msg.topic = "lemons/debug"
            msg.payload.decode.return_value = "true"
            
            client._on_message(None, None, msg)
            
            mock_logger.info.assert_called_with("lemons/debug: true")
    
    def test_handle_obd_message_no_connection(self):
        """Test OBD message handling when no connection exists"""
        with patch('src.config.is_raspberrypi', return_value=False):
            client = VTMSClient()
            
            # Should not raise error when no connection
            client._handle_obd_message("lemons/obd2/watch", "RPM")
    
    @patch('obd.commands')
    def test_handle_obd_watch_message(self, mock_commands):
        """Test OBD watch message handling"""
        mock_commands.__contains__ = Mock(return_value=True)
        mock_commands.__getitem__ = Mock(return_value="RPM_COMMAND")
        
        with patch('src.config.is_raspberrypi', return_value=False):
            client = VTMSClient()
            client.obd_connection = MockOBDAsync()
            client.mqttc = MockMQTTClient()
            
            client._handle_obd_message("lemons/obd2/watch", "RPM")
            
            # Verify watch was called
            assert "RPM_COMMAND" in client.obd_connection.watched_commands
    
    @patch('obd.commands')
    def test_handle_obd_unwatch_message(self, mock_commands):
        """Test OBD unwatch message handling"""
        mock_commands.__contains__ = Mock(return_value=True)
        mock_commands.__getitem__ = Mock(return_value="RPM_COMMAND")
        
        with patch('src.config.is_raspberrypi', return_value=False):
            client = VTMSClient()
            client.obd_connection = MockOBDAsync()
            client.mqttc = MockMQTTClient()
            
            # First watch, then unwatch
            client.obd_connection.watch("RPM_COMMAND", Mock())
            client._handle_obd_message("lemons/obd2/unwatch", "RPM")
            
            # Verify unwatch was called
            assert "RPM_COMMAND" not in client.obd_connection.watched_commands
    
    @patch('obd.commands')
    @patch('src.myobd.metric_commands', ['RPM'])
    @patch('src.myobd.new_metric')
    def test_handle_obd_query_message(self, mock_new_metric, mock_commands):
        """Test OBD query message handling"""
        mock_commands.__contains__ = Mock(return_value=True)
        mock_commands.__getitem__ = Mock(return_value="RPM_COMMAND")
        
        with patch('src.config.is_raspberrypi', return_value=False):
            client = VTMSClient()
            client.obd_connection = MockOBDAsync()
            client.mqttc = MockMQTTClient()
            
            client._handle_obd_message("lemons/obd2/query", "RPM")
            
            # Verify metric handler was called
            mock_new_metric.assert_called_once()
    
    @patch('obd.scan_serial')
    @patch('obd.Async')
    @patch('client.logger')
    def test_setup_obd_connection_success(self, mock_logger, mock_obd_async, mock_scan):
        """Test successful OBD connection setup"""
        mock_scan.return_value = ['/dev/ttyUSB0']
        mock_connection = MockOBDAsync()
        mock_obd_async.return_value = mock_connection
        
        with patch('src.config.is_raspberrypi', return_value=False):
            client = VTMSClient()
            result = client.setup_obd_connection()
            
            assert result is True
            assert client.obd_connection is not None
            mock_logger.info.assert_called_with('Connected to OBDII port on /dev/ttyUSB0')
    
    @patch('obd.scan_serial')
    @patch('time.sleep')
    @patch('client.logger')
    def test_setup_obd_connection_no_ports(self, mock_logger, mock_sleep, mock_scan):
        """Test OBD connection setup with no ports found"""
        # First call returns no ports, second call returns a port
        mock_scan.side_effect = [[], ['/dev/ttyUSB0']]
        
        with patch('src.config.is_raspberrypi', return_value=False):
            with patch('obd.Async') as mock_obd_async:
                mock_connection = MockOBDAsync()
                mock_obd_async.return_value = mock_connection
                
                client = VTMSClient()
                result = client.setup_obd_connection()
                
                assert result is True
                mock_logger.warning.assert_called()
                mock_sleep.assert_called()
    
    @patch('obd.commands')
    @patch('src.myobd.metric_commands', ['RPM', 'SPEED'])
    @patch('src.myobd.monitor_commands', ['MONITOR_VVT_B1'])
    @patch('client.logger')
    def test_setup_obd_watches(self, mock_logger, mock_commands):
        """Test OBD watches setup"""
        mock_commands.__getitem__ = Mock(side_effect=lambda x: f"{x}_COMMAND")
        
        with patch('src.config.is_raspberrypi', return_value=False):
            client = VTMSClient()
            client.obd_connection = MockOBDAsync()
            client.mqttc = MockMQTTClient()
            
            # Add supported commands
            client.obd_connection.add_supported_command("RPM_COMMAND")
            client.obd_connection.add_supported_command("SPEED_COMMAND")
            client.obd_connection.add_supported_command("MONITOR_VVT_B1_COMMAND")
            client.obd_connection.add_supported_command("GET_DTC_COMMAND")
            
            client.setup_obd_watches()
            
            # Verify watches were set up
            assert len(client.obd_connection.watched_commands) >= 3  # metrics + monitor + DTC
    
    def test_setup_obd_watches_no_connection(self):
        """Test OBD watches setup without connection"""
        with patch('src.config.is_raspberrypi', return_value=False):
            with patch('client.logger') as mock_logger:
                client = VTMSClient()
                client.setup_obd_watches()


class TestMQTTBuffering:
    """Test cases for MQTT message buffering functionality"""
    
    @patch('src.config.is_raspberrypi')
    @patch('client.logger')
    def test_publish_message_when_connected(self, mock_logger, mock_is_pi):
        """Test publishing message when MQTT is connected"""
        mock_is_pi.return_value = False
        
        client = VTMSClient()
        client.mqttc = Mock()
        client.mqtt_connected = True
        
        # Mock successful publish
        mock_result = Mock()
        mock_result.rc = 0
        client.mqttc.publish.return_value = mock_result
        
        # Test publishing
        result = client._publish_message("test/topic", {"key": "value"})
        
        assert result is True
        client.mqttc.publish.assert_called_once_with("test/topic", '{"key": "value"}', 0, False)
    
    @patch('src.config.is_raspberrypi')
    @patch('client.logger')
    def test_publish_message_when_disconnected(self, mock_logger, mock_is_pi):
        """Test publishing message when MQTT is disconnected"""
        mock_is_pi.return_value = False
        
        client = VTMSClient()
        client.mqttc = Mock()
        client.mqtt_connected = False
        
        # Test publishing
        result = client._publish_message("test/topic", {"key": "value"})
        
        assert result is False
        # Should not call actual publish
        client.mqttc.publish.assert_not_called()
        # Should buffer the message
        assert len(client.message_buffer) == 1
        assert client.message_buffer[0]['topic'] == "test/topic"
        assert client.message_buffer[0]['payload'] == {"key": "value"}
    
    @patch('src.config.is_raspberrypi')
    @patch('client.logger')
    def test_buffer_message_overflow(self, mock_logger, mock_is_pi):
        """Test message buffer overflow handling"""
        mock_is_pi.return_value = False
        
        client = VTMSClient()
        client.max_buffer_size = 3  # Small buffer for testing
        
        # Fill buffer beyond capacity
        for i in range(5):
            client._buffer_message(f"test/topic/{i}", f"message {i}")
        
        # Buffer should only contain the last 3 messages
        assert len(client.message_buffer) == 3
        topics = [msg['topic'] for msg in client.message_buffer]
        assert "test/topic/2" in topics
        assert "test/topic/3" in topics
        assert "test/topic/4" in topics
        assert "test/topic/0" not in topics
        assert "test/topic/1" not in topics
    
    @patch('src.config.is_raspberrypi')
    @patch('client.logger')
    def test_flush_message_buffer_success(self, mock_logger, mock_is_pi):
        """Test successful flushing of message buffer"""
        mock_is_pi.return_value = False
        
        client = VTMSClient()
        client.mqttc = Mock()
        client.mqtt_connected = True
        
        # Mock successful publish
        mock_result = Mock()
        mock_result.rc = 0
        client.mqttc.publish.return_value = mock_result
        
        # Add messages to buffer
        client._buffer_message("test/topic/1", "message 1")
        client._buffer_message("test/topic/2", "message 2")
        
        # Flush buffer
        client._flush_message_buffer()
        
        # All messages should be published and buffer should be empty
        assert len(client.message_buffer) == 0
        assert client.mqttc.publish.call_count == 2
    
    @patch('src.config.is_raspberrypi')
    @patch('client.logger')  
    def test_flush_message_buffer_expired_messages(self, mock_logger, mock_is_pi):
        """Test flushing buffer with expired messages"""
        mock_is_pi.return_value = False
        
        client = VTMSClient()
        client.mqttc = Mock()
        client.mqtt_connected = True
        
        # Add expired message (timestamp more than 5 minutes ago)
        old_time = time.time() - 400  # 400 seconds ago
        client.message_buffer.append({
            'topic': 'test/old',
            'payload': 'old message',
            'qos': 0,
            'retain': False,
            'timestamp': old_time
        })
        
        # Add fresh message
        client._buffer_message("test/fresh", "fresh message")
        
        # Mock successful publish
        mock_result = Mock()
        mock_result.rc = 0
        client.mqttc.publish.return_value = mock_result
        
        # Flush buffer
        client._flush_message_buffer()
        
        # Only fresh message should be published
        client.mqttc.publish.assert_called_once_with("test/fresh", "fresh message", 0, False)
        assert len(client.message_buffer) == 0


class TestMQTTWrapper:
    """Test cases for MQTTWrapper class"""
    
    @patch('src.config.is_raspberrypi')
    def test_mqtt_wrapper_publish(self, mock_is_pi):
        """Test MQTTWrapper publish method"""
        mock_is_pi.return_value = False
        
        client = VTMSClient()
        wrapper = MQTTWrapper(client)
        
        # Mock the client's _publish_message method
        client._publish_message = Mock(return_value=True)
        
        # Test wrapper publish
        result = wrapper.publish("test/topic", "test message", 1, True)
        
        assert result is True
        client._publish_message.assert_called_once_with("test/topic", "test message", 1, True)
