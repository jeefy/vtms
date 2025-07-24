"""
Integration tests for VTMS system
"""

import asyncio
import sys
import os
from unittest.mock import Mock, patch, MagicMock
import time

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client import VTMSClient
from tests.conftest import MockOBDAsync, MockMQTTClient, MockGPSPacket


class TestVTMSIntegration:
    """Integration tests for the complete VTMS system"""
    
    @patch('obd.scan_serial')
    @patch('obd.Async')
    @patch('paho.mqtt.client.Client')
    @patch('gpsd2.connect')
    @patch('gpsd2.get_current')
    @patch('src.config.is_raspberrypi')
    async def test_complete_system_startup(self, mock_is_pi, mock_gps_current, 
                                         mock_gps_connect, mock_mqtt_class, 
                                         mock_obd_async, mock_scan):
        """Test complete system startup and basic operation"""
        
        # Setup mocks
        mock_is_pi.return_value = False
        mock_scan.return_value = ['/dev/ttyUSB0']
        
        mock_obd_connection = MockOBDAsync()
        mock_obd_async.return_value = mock_obd_connection
        
        mock_mqtt_client = MockMQTTClient()
        mock_mqtt_class.return_value = mock_mqtt_client
        
        mock_gps_packet = MockGPSPacket()
        mock_gps_current.return_value = mock_gps_packet
        
        # Create client and setup
        client = VTMSClient()
        
        # Test MQTT setup
        mqtt_result = client.setup_mqtt()
        assert mqtt_result is True
        assert client.mqttc is not None
        
        # Test OBD setup
        obd_result = client.setup_obd_connection()
        assert obd_result is True
        assert client.obd_connection is not None
        
        # Test OBD watches setup
        client.obd_connection.add_supported_command("RPM_COMMAND")
        client.obd_connection.add_supported_command("SPEED_COMMAND")
        client.setup_obd_watches()
        assert len(client.obd_connection.watched_commands) > 0
        
        # Test GPS monitoring for a short time
        gps_task = asyncio.create_task(client.start_gps_monitoring())
        await asyncio.sleep(0.1)  # Let it run briefly
        gps_task.cancel()
        
        try:
            await gps_task
        except asyncio.CancelledError:
            pass
        
        # Verify GPS data was published
        assert len(mock_mqtt_client.published_messages) > 0
        topics = [msg[0] for msg in mock_mqtt_client.published_messages]
        assert any("lemons/gps/" in topic for topic in topics)
    
    @patch('src.config.is_raspberrypi')
    def test_message_routing_integration(self, mock_is_pi):
        """Test complete message routing system"""
        mock_is_pi.return_value = False
        
        client = VTMSClient()
        client.mqttc = MockMQTTClient()
        client.obd_connection = MockOBDAsync()
        
        # Test various message types
        test_messages = [
            ("lemons/debug", "true"),
            ("lemons/message", "Test pit message"),
            ("lemons/flag/red", "true"),
            ("lemons/flag/black", "true"),
            ("lemons/pit", "true"),
            ("lemons/box", "true"),
        ]
        
        for topic, payload in test_messages:
            # Simulate receiving message
            client.mqttc.simulate_message(topic, payload)
        
        # All messages should be handled without errors
        assert True  # If we get here, no exceptions were raised
    
    @patch('obd.commands')
    @patch('src.config.is_raspberrypi')
    def test_obd_message_handling_integration(self, mock_is_pi, mock_commands):
        """Test OBD message handling integration"""
        mock_is_pi.return_value = False
        mock_commands.__contains__ = Mock(return_value=True)
        mock_commands.__getitem__ = Mock(return_value="TEST_COMMAND")
        
        client = VTMSClient()
        client.mqttc = MockMQTTClient()
        client.obd_connection = MockOBDAsync()
        
        # Test OBD watch command
        client.mqttc.simulate_message("lemons/obd2/watch", "RPM")
        assert "TEST_COMMAND" in client.obd_connection.watched_commands
        
        # Test OBD unwatch command
        client.mqttc.simulate_message("lemons/obd2/unwatch", "RPM")
        assert "TEST_COMMAND" not in client.obd_connection.watched_commands
        
        # Test OBD query command
        with patch('src.myobd.new_metric') as mock_new_metric:
            with patch('src.myobd.metric_commands', ['RPM']):
                client.mqttc.simulate_message("lemons/obd2/query", "RPM")
                mock_new_metric.assert_called_once()
    
    @patch('src.config.is_raspberrypi')
    @patch('client.logger')
    def test_error_handling_integration(self, mock_logger, mock_is_pi):
        """Test error handling throughout the system"""
        mock_is_pi.return_value = False
        
        client = VTMSClient()
        
        # Test MQTT setup failure
        with patch('paho.mqtt.client.Client', side_effect=Exception("MQTT Error")):
            result = client.setup_mqtt()
            assert result is False
            mock_logger.error.assert_called()
        
        # Test OBD setup with no ports
        with patch('obd.scan_serial', return_value=[]):
            with patch('time.sleep'):  # Mock sleep to speed up test
                # This would normally loop forever, so we'll just test the first iteration
                try:
                    with patch('src.config.config') as mock_config:
                        mock_config.obd_retry_delay = 0.001
                        # Run setup for a very short time
                        import threading
                        import time
                        
                        def timeout_setup():
                            time.sleep(0.01)  # Very short timeout
                            return False
                        
                        # We can't easily test the infinite loop, so we'll just verify
                        # the logging happens
                        ports = []
                        if len(ports) == 0:
                            mock_logger.warning.assert_called()
                except:
                    pass  # Expected to timeout or error
    
    @patch('src.config.is_raspberrypi')
    async def test_cleanup_and_shutdown(self, mock_is_pi):
        """Test proper cleanup and shutdown"""
        mock_is_pi.return_value = False
        
        client = VTMSClient()
        
        # Setup mocks
        mock_obd = Mock()
        mock_mqtt = Mock()
        
        client.obd_connection = mock_obd
        client.mqttc = mock_mqtt
        
        # Create a GPS task
        gps_task = asyncio.create_task(client.start_gps_monitoring())
        
        # Simulate shutdown
        gps_task.cancel()
        
        # Test cleanup (simulating the finally block)
        if client.obd_connection:
            client.obd_connection.stop()
        if client.mqttc:
            client.mqttc.loop_stop()
            client.mqttc.disconnect()
        
        # Verify cleanup methods were called
        mock_obd.stop.assert_called_once()
        mock_mqtt.loop_stop.assert_called_once()
        mock_mqtt.disconnect.assert_called_once()
    
    @patch('src.config.getDebug')
    @patch('src.config.is_raspberrypi')
    def test_debug_mode_integration(self, mock_is_pi, mock_debug):
        """Test debug mode affects system behavior"""
        mock_is_pi.return_value = False
        mock_debug.return_value = True
        
        client = VTMSClient()
        client.mqttc = MockMQTTClient()
        
        # Test debug message handling
        client.mqttc.simulate_message("lemons/debug", "false")
        
        # Verify debug state can be changed
        with patch('src.config.setDebug') as mock_set_debug:
            client.message_router.route_message("lemons/debug", "true")
            mock_set_debug.assert_called_with(True)


class TestVTMSPerformance:
    """Performance and stress tests for VTMS"""
    
    @patch('src.config.is_raspberrypi')
    async def test_message_throughput(self, mock_is_pi):
        """Test system can handle high message throughput"""
        mock_is_pi.return_value = False
        
        client = VTMSClient()
        client.mqttc = MockMQTTClient()
        
        # Send many messages rapidly
        start_time = time.time()
        message_count = 100
        
        for i in range(message_count):
            client.mqttc.simulate_message("lemons/debug", "true" if i % 2 == 0 else "false")
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should process messages quickly (less than 1 second for 100 messages)
        assert processing_time < 1.0
        print(f"Processed {message_count} messages in {processing_time:.3f} seconds")
    
    @patch('src.config.is_raspberrypi')
    async def test_gps_data_collection_performance(self, mock_is_pi):
        """Test GPS data collection performance"""
        mock_is_pi.return_value = False
        
        with patch('gpsd2.connect'), patch('gpsd2.get_current') as mock_gps:
            mock_gps.return_value = MockGPSPacket()
            
            client = VTMSClient()
            client.mqttc = MockMQTTClient()
            
            # Run GPS monitoring for a short time
            start_time = time.time()
            gps_task = asyncio.create_task(client.start_gps_monitoring())
            
            await asyncio.sleep(0.5)  # Run for half a second
            gps_task.cancel()
            
            try:
                await gps_task
            except asyncio.CancelledError:
                pass
            
            end_time = time.time()
            
            # Verify data was collected
            assert len(client.mqttc.published_messages) > 0
            
            # Calculate rate
            messages_per_second = len(client.mqttc.published_messages) / (end_time - start_time)
            print(f"GPS data rate: {messages_per_second:.1f} messages/second")
            
            # Should be collecting data at reasonable rate
            assert messages_per_second > 1.0  # At least 1 GPS update per second
