"""
Unit tests for MQTT message handlers
"""

import sys
import os
from unittest.mock import Mock, patch

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.mqtt_handlers import (
    MQTTMessageRouter,
    create_debug_handler,
    create_flag_handler,
    create_pit_handler,
    create_message_handler
)


class TestMQTTMessageRouter:
    """Test cases for MQTTMessageRouter class"""
    
    def test_router_initialization(self):
        """Test router initialization"""
        router = MQTTMessageRouter()
        
        assert router.handlers == {}
        assert router.pattern_handlers == {}
    
    def test_register_handler(self):
        """Test registering a message handler"""
        router = MQTTMessageRouter()
        handler = Mock()
        
        router.register_handler("test/topic", handler)
        
        assert "test/topic" in router.handlers
        assert router.handlers["test/topic"] == handler
    
    def test_register_pattern_handler(self):
        """Test registering a pattern handler"""
        router = MQTTMessageRouter()
        handler = Mock()
        
        router.register_pattern_handler("test/", handler)
        
        assert "test/" in router.pattern_handlers
        assert router.pattern_handlers["test/"] == handler
    
    def test_route_message_exact_match(self):
        """Test routing message with exact topic match"""
        router = MQTTMessageRouter()
        handler = Mock()
        
        router.register_handler("test/topic", handler)
        result = router.route_message("test/topic", "payload", extra_arg="value")
        
        assert result is True
        handler.assert_called_once_with("test/topic", "payload", extra_arg="value")
    
    def test_route_message_pattern_match(self):
        """Test routing message with pattern match"""
        router = MQTTMessageRouter()
        handler = Mock()
        
        router.register_pattern_handler("test/", handler)
        result = router.route_message("test/subtopic", "payload")
        
        assert result is True
        handler.assert_called_once_with("test/subtopic", "payload")
    
    def test_route_message_exact_takes_precedence(self):
        """Test that exact match takes precedence over pattern match"""
        router = MQTTMessageRouter()
        exact_handler = Mock()
        pattern_handler = Mock()
        
        router.register_handler("test/topic", exact_handler)
        router.register_pattern_handler("test/", pattern_handler)
        
        result = router.route_message("test/topic", "payload")
        
        assert result is True
        exact_handler.assert_called_once_with("test/topic", "payload")
        pattern_handler.assert_not_called()
    
    @patch('src.config.getDebug')
    @patch('src.mqtt_handlers.logger')
    def test_route_message_no_match(self, mock_logger, mock_debug):
        """Test routing message with no matching handler"""
        mock_debug.return_value = True
        router = MQTTMessageRouter()
        
        result = router.route_message("unknown/topic", "payload")
        
        assert result is False
        mock_logger.warning.assert_called_once_with("No handler found for topic: unknown/topic")
    
    @patch('src.config.getDebug')
    def test_route_message_no_match_debug_off(self, mock_debug):
        """Test routing message with no match when debug is off"""
        mock_debug.return_value = False
        router = MQTTMessageRouter()
        
        result = router.route_message("unknown/topic", "payload")
        
        assert result is False


class TestDebugHandler:
    """Test cases for debug message handler"""
    
    @patch('src.config.setDebug')
    @patch('src.mqtt_handlers.logger')
    def test_debug_handler_enable(self, mock_logger, mock_set_debug):
        """Test debug handler enabling debug mode"""
        handler = create_debug_handler()
        
        handler("lemons/debug", "true")
        
        mock_set_debug.assert_called_once_with(True)
        mock_logger.info.assert_called_once_with('Debug mode enabled')
    
    @patch('src.config.setDebug')
    @patch('src.mqtt_handlers.logger')
    def test_debug_handler_disable(self, mock_logger, mock_set_debug):
        """Test debug handler disabling debug mode"""
        handler = create_debug_handler()
        
        handler("lemons/debug", "false")
        
        mock_set_debug.assert_called_once_with(False)
        mock_logger.info.assert_called_once_with('Debug mode disabled')
    
    @patch('src.config.setDebug')
    @patch('src.mqtt_handlers.logger')
    def test_debug_handler_other_value(self, mock_logger, mock_set_debug):
        """Test debug handler with non-true value"""
        handler = create_debug_handler()
        
        handler("lemons/debug", "anything_else")
        
        mock_set_debug.assert_called_once_with(False)
        mock_logger.info.assert_called_once_with('Debug mode disabled')


class TestFlagHandler:
    """Test cases for flag message handler"""
    
    @patch('src.mqtt_handlers.logger')
    def test_flag_handler_red_flag(self, mock_logger):
        """Test flag handler for red flag"""
        handler = create_flag_handler()
        
        handler("lemons/flag/red", "true")
        
        mock_logger.warning.assert_called_once_with('Red Flag: true')
    
    @patch('src.mqtt_handlers.logger')
    def test_flag_handler_black_flag(self, mock_logger):
        """Test flag handler for black flag"""
        handler = create_flag_handler()
        
        handler("lemons/flag/black", "true")
        
        mock_logger.warning.assert_called_once_with('Black Flag: true')
    
    @patch('src.mqtt_handlers.logger')
    def test_flag_handler_false_value(self, mock_logger):
        """Test flag handler with false value"""
        handler = create_flag_handler()
        
        handler("lemons/flag/red", "false")
        
        mock_logger.warning.assert_not_called()
    
    @patch('src.mqtt_handlers.logger')
    def test_flag_handler_unknown_flag(self, mock_logger):
        """Test flag handler with unknown flag type"""
        handler = create_flag_handler()
        
        handler("lemons/flag/unknown", "true")
        
        mock_logger.warning.assert_not_called()


class TestPitHandler:
    """Test cases for pit message handler"""
    
    @patch('src.mqtt_handlers.logger')
    def test_pit_handler_pit_soon(self, mock_logger):
        """Test pit handler for pit soon message"""
        handler = create_pit_handler()
        
        handler("lemons/pit", "true")
        
        mock_logger.info.assert_called_once_with('Pit Soon: true')
    
    @patch('src.mqtt_handlers.logger')
    def test_pit_handler_box_box(self, mock_logger):
        """Test pit handler for box box message"""
        handler = create_pit_handler()
        
        handler("lemons/box", "true")
        
        mock_logger.warning.assert_called_once_with('BOX BOX: true')
    
    @patch('src.mqtt_handlers.logger')
    def test_pit_handler_false_value(self, mock_logger):
        """Test pit handler with false value"""
        handler = create_pit_handler()
        
        handler("lemons/pit", "false")
        
        mock_logger.info.assert_not_called()
        mock_logger.warning.assert_not_called()
    
    @patch('src.mqtt_handlers.logger')
    def test_pit_handler_unknown_topic(self, mock_logger):
        """Test pit handler with unknown topic"""
        handler = create_pit_handler()
        
        handler("lemons/unknown", "true")
        
        mock_logger.info.assert_not_called()
        mock_logger.warning.assert_not_called()


class TestMessageHandler:
    """Test cases for general message handler"""
    
    @patch('src.mqtt_handlers.logger')
    def test_message_handler(self, mock_logger):
        """Test general message handler"""
        handler = create_message_handler()
        
        handler("lemons/message", "Test pit message")
        
        mock_logger.info.assert_called_once_with('Pit message: Test pit message')


class TestMQTTHandlersIntegration:
    """Integration tests for MQTT handlers"""
    
    @patch('src.config.setDebug')
    @patch('src.mqtt_handlers.logger')
    def test_complete_message_routing(self, mock_logger, mock_set_debug):
        """Test complete message routing workflow"""
        router = MQTTMessageRouter()
        
        # Set up all handlers
        router.register_handler('lemons/debug', create_debug_handler())
        router.register_handler('lemons/message', create_message_handler())
        router.register_pattern_handler('lemons/flag/', create_flag_handler())
        
        pit_handler = create_pit_handler()
        router.register_handler('lemons/pit', pit_handler)
        router.register_handler('lemons/box', pit_handler)
        
        # Test different message types
        router.route_message('lemons/debug', 'true')
        router.route_message('lemons/message', 'Test message')
        router.route_message('lemons/flag/red', 'true')
        router.route_message('lemons/pit', 'true')
        router.route_message('lemons/box', 'true')
        
        # Verify all handlers were called
        mock_set_debug.assert_called_once_with(True)
        assert mock_logger.info.call_count >= 2  # debug + message + pit
        assert mock_logger.warning.call_count >= 2  # red flag + box box
    
    def test_handler_isolation(self):
        """Test that handlers don't interfere with each other"""
        router = MQTTMessageRouter()
        
        handler1 = Mock()
        handler2 = Mock()
        
        router.register_handler('topic1', handler1)
        router.register_handler('topic2', handler2)
        
        router.route_message('topic1', 'payload1')
        router.route_message('topic2', 'payload2')
        
        handler1.assert_called_once_with('topic1', 'payload1')
        handler2.assert_called_once_with('topic2', 'payload2')
