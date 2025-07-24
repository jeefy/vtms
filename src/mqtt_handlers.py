"""
MQTT message handlers for VTMS system
"""

import logging
from typing import Dict, Callable, Any

from . import config

logger = logging.getLogger(__name__)


class MQTTMessageRouter:
    """Router for handling different types of MQTT messages"""
    
    def __init__(self):
        self.handlers: Dict[str, Callable] = {}
        self.pattern_handlers: Dict[str, Callable] = {}
    
    def register_handler(self, topic: str, handler: Callable):
        """Register a handler for a specific topic"""
        self.handlers[topic] = handler
    
    def register_pattern_handler(self, pattern: str, handler: Callable):
        """Register a handler for a topic pattern (prefix matching)"""
        self.pattern_handlers[pattern] = handler
    
    def route_message(self, topic: str, payload: str, **kwargs) -> bool:
        """Route a message to the appropriate handler"""
        # Check exact match first
        if topic in self.handlers:
            self.handlers[topic](topic, payload, **kwargs)
            return True
        
        # Check pattern matches
        for pattern, handler in self.pattern_handlers.items():
            if topic.startswith(pattern):
                handler(topic, payload, **kwargs)
                return True
        
        if config.getDebug():
            logger.warning(f"No handler found for topic: {topic}")
        return False


def create_debug_handler():
    """Create handler for debug messages"""
    def handle_debug(topic: str, payload: str, **kwargs):
        if payload == 'true':
            config.setDebug(True)
            logger.info('Debug mode enabled')
        else:
            config.setDebug(False)
            logger.info('Debug mode disabled')
    return handle_debug


def create_flag_handler():
    """Create handler for flag messages"""
    def handle_flag(topic: str, payload: str, **kwargs):
        flag_type = topic.split('/')[-1]  # Extract flag type from topic
        if payload == 'true':
            if flag_type == 'red':
                logger.warning(f'Red Flag: {payload}')
            elif flag_type == 'black':
                logger.warning(f'Black Flag: {payload}')
    return handle_flag


def create_pit_handler():
    """Create handler for pit-related messages"""
    def handle_pit(topic: str, payload: str, **kwargs):
        if topic == 'lemons/pit' and payload == 'true':
            logger.info(f'Pit Soon: {payload}')
        elif topic == 'lemons/box' and payload == 'true':
            logger.warning(f'BOX BOX: {payload}')
    return handle_pit


def create_message_handler():
    """Create handler for general messages"""
    def handle_message(topic: str, payload: str, **kwargs):
        logger.info(f'Pit message: {payload}')
    return handle_message
