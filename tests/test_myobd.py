"""
Unit tests for myobd module
"""

import sys
import os
from unittest.mock import Mock, patch

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import myobd


class MockOBDResponse:
    """Mock OBD response for testing"""
    
    def __init__(self, command_name, value=None, is_null=False):
        self.command = Mock()
        self.command.name = command_name
        self.value = value
        self._is_null = is_null
    
    def is_null(self):
        return self._is_null


class MockMQTTClient:
    """Mock MQTT client for testing"""
    
    def __init__(self):
        self.published_messages = []
    
    def publish(self, topic, payload):
        self.published_messages.append((topic, payload))


class TestMyOBDModule:
    """Test cases for myobd module"""
    
    def test_metric_commands_list(self):
        """Test that metric commands list is properly defined"""
        assert isinstance(myobd.metric_commands, list)
        assert len(myobd.metric_commands) > 0
        assert 'RPM' in myobd.metric_commands
        assert 'SPEED' in myobd.metric_commands
        assert 'ENGINE_LOAD' in myobd.metric_commands
    
    def test_monitor_commands_list(self):
        """Test that monitor commands list is properly defined"""
        assert isinstance(myobd.monitor_commands, list)
        assert len(myobd.monitor_commands) > 0
        assert 'MONITOR_EGR_B1' in myobd.monitor_commands
        assert 'MONITOR_VVT_B1' in myobd.monitor_commands


class TestNewMetric:
    """Test cases for new_metric function"""
    
    @patch('src.config.getDebug')
    def test_new_metric_with_valid_data(self, mock_debug):
        """Test new_metric with valid OBD response"""
        mock_debug.return_value = True
        mock_mqttc = MockMQTTClient()
        
        # Create mock response with magnitude
        mock_value = Mock()
        mock_value.magnitude = 2500
        response = MockOBDResponse('RPM', mock_value)
        
        myobd.new_metric(response, mock_mqttc)
        
        # Verify MQTT publish was called
        assert len(mock_mqttc.published_messages) == 1
        topic, payload = mock_mqttc.published_messages[0]
        assert topic == "lemons/RPM"
        assert str(mock_value) in payload
    
    @patch('src.config.getDebug')
    def test_new_metric_with_null_response(self, mock_debug):
        """Test new_metric with null OBD response"""
        mock_debug.return_value = True
        mock_mqttc = MockMQTTClient()
        
        response = MockOBDResponse('RPM', None, is_null=True)
        
        myobd.new_metric(response, mock_mqttc)
        
        # Verify no MQTT publish was called for null response
        assert len(mock_mqttc.published_messages) == 0
    
    @patch('src.config.getDebug')
    def test_new_metric_debug_disabled(self, mock_debug):
        """Test new_metric with debug disabled"""
        mock_debug.return_value = False
        mock_mqttc = MockMQTTClient()
        
        mock_value = Mock()
        mock_value.magnitude = 2500
        response = MockOBDResponse('RPM', mock_value)
        
        myobd.new_metric(response, mock_mqttc)
        
        # Should still publish even with debug disabled
        assert len(mock_mqttc.published_messages) == 1


class TestNewMonitor:
    """Test cases for new_monitor function"""
    
    @patch('src.config.getDebug')
    def test_new_monitor_with_valid_data(self, mock_debug):
        """Test new_monitor with valid OBD response"""
        mock_debug.return_value = True
        mock_mqttc = MockMQTTClient()
        
        response = MockOBDResponse('MONITOR_VVT_B1', 'test_monitor_value')
        
        myobd.new_monitor(response, mock_mqttc)
        
        # Verify MQTT publish was called
        assert len(mock_mqttc.published_messages) == 1
        topic, payload = mock_mqttc.published_messages[0]
        assert topic == "lemons/MONITOR_VVT_B1"
        assert payload == "test_monitor_value"
    
    @patch('src.config.getDebug')
    def test_new_monitor_with_null_response(self, mock_debug):
        """Test new_monitor with null OBD response"""
        mock_debug.return_value = True
        mock_mqttc = MockMQTTClient()
        
        response = MockOBDResponse('MONITOR_VVT_B1', None, is_null=True)
        
        myobd.new_monitor(response, mock_mqttc)
        
        # Verify no MQTT publish was called for null response
        assert len(mock_mqttc.published_messages) == 0
    
    @patch('src.config.getDebug')
    def test_new_monitor_debug_disabled(self, mock_debug):
        """Test new_monitor with debug disabled"""
        mock_debug.return_value = False
        mock_mqttc = MockMQTTClient()
        
        response = MockOBDResponse('MONITOR_VVT_B1', 'test_value')
        
        myobd.new_monitor(response, mock_mqttc)
        
        # Should still publish even with debug disabled
        assert len(mock_mqttc.published_messages) == 1


class TestNewDTC:
    """Test cases for new_dtc function"""
    
    @patch('src.config.getDebug')
    def test_new_dtc_with_single_dtc(self, mock_debug):
        """Test new_dtc with single DTC"""
        mock_debug.return_value = True
        mock_mqttc = MockMQTTClient()
        
        # Single DTC as tuple (code, description)
        dtc_tuple = ('P0300', 'Random/Multiple Cylinder Misfire Detected')
        response = MockOBDResponse('GET_DTC', dtc_tuple)
        
        myobd.new_dtc(response, mock_mqttc)
        
        # Verify MQTT publish was called
        assert len(mock_mqttc.published_messages) == 1
        topic, payload = mock_mqttc.published_messages[0]
        assert topic == "lemons/DTC/P0300"
        assert payload == 'Random/Multiple Cylinder Misfire Detected'
    
    @patch('src.config.getDebug')
    def test_new_dtc_with_multiple_dtcs(self, mock_debug):
        """Test new_dtc with multiple DTCs"""
        mock_debug.return_value = True
        mock_mqttc = MockMQTTClient()
        
        # Multiple DTCs as list of tuples
        dtc_list = [
            ('P0300', 'Random/Multiple Cylinder Misfire Detected'),
            ('P0420', 'Catalyst System Efficiency Below Threshold')
        ]
        response = MockOBDResponse('GET_DTC', dtc_list)
        
        myobd.new_dtc(response, mock_mqttc)
        
        # Verify MQTT publish was called for each DTC
        assert len(mock_mqttc.published_messages) == 2
        
        # Check first DTC
        topic1, payload1 = mock_mqttc.published_messages[0]
        assert topic1 == "lemons/DTC/P0300"
        assert payload1 == 'Random/Multiple Cylinder Misfire Detected'
        
        # Check second DTC
        topic2, payload2 = mock_mqttc.published_messages[1]
        assert topic2 == "lemons/DTC/P0420"
        assert payload2 == 'Catalyst System Efficiency Below Threshold'
    
    @patch('src.config.getDebug')
    def test_new_dtc_converts_single_to_list(self, mock_debug):
        """Test new_dtc converts single DTC to list format"""
        mock_debug.return_value = True
        mock_mqttc = MockMQTTClient()
        
        # Single DTC that's not already in list format
        dtc_tuple = ('P0300', 'Random/Multiple Cylinder Misfire Detected')
        response = MockOBDResponse('GET_DTC', dtc_tuple)
        
        # The function should convert single DTC to list
        myobd.new_dtc(response, mock_mqttc)
        
        # Should still publish correctly
        assert len(mock_mqttc.published_messages) == 1
    
    @patch('src.config.getDebug')
    def test_new_dtc_debug_disabled(self, mock_debug):
        """Test new_dtc with debug disabled"""
        mock_debug.return_value = False
        mock_mqttc = MockMQTTClient()
        
        dtc_tuple = ('P0300', 'Random/Multiple Cylinder Misfire Detected')
        response = MockOBDResponse('GET_DTC', dtc_tuple)
        
        myobd.new_dtc(response, mock_mqttc)
        
        # Should still publish even with debug disabled
        assert len(mock_mqttc.published_messages) == 1


class TestMyOBDIntegration:
    """Integration tests for myobd module"""
    
    @patch('src.config.getDebug')
    def test_all_functions_with_debug_enabled(self, mock_debug):
        """Test all functions work together with debug enabled"""
        mock_debug.return_value = True
        mock_mqttc = MockMQTTClient()
        
        # Test metric
        mock_value = Mock()
        mock_value.magnitude = 2500
        metric_response = MockOBDResponse('RPM', mock_value)
        myobd.new_metric(metric_response, mock_mqttc)
        
        # Test monitor
        monitor_response = MockOBDResponse('MONITOR_VVT_B1', 'monitor_value')
        myobd.new_monitor(monitor_response, mock_mqttc)
        
        # Test DTC
        dtc_response = MockOBDResponse('GET_DTC', ('P0300', 'Misfire'))
        myobd.new_dtc(dtc_response, mock_mqttc)
        
        # Verify all published
        assert len(mock_mqttc.published_messages) == 3
        
        # Check topics
        topics = [msg[0] for msg in mock_mqttc.published_messages]
        assert "lemons/RPM" in topics
        assert "lemons/MONITOR_VVT_B1" in topics
        assert "lemons/DTC/P0300" in topics
    
    def test_command_lists_consistency(self):
        """Test that command lists contain valid command names"""
        # All commands should be strings
        for command in myobd.metric_commands:
            assert isinstance(command, str)
            assert len(command) > 0
        
        for command in myobd.monitor_commands:
            assert isinstance(command, str)
            assert len(command) > 0
        
        # No duplicates within lists
        assert len(myobd.metric_commands) == len(set(myobd.metric_commands))
        assert len(myobd.monitor_commands) == len(set(myobd.monitor_commands))
        
        # No overlap between metric and monitor commands
        metric_set = set(myobd.metric_commands)
        monitor_set = set(myobd.monitor_commands)
        assert len(metric_set.intersection(monitor_set)) == 0
