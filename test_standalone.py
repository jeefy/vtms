#!/usr/bin/env python3
"""
Standalone test runner that doesn't require external dependencies
"""

import sys
import os
from unittest.mock import Mock, MagicMock, patch

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_config_module():
    """Test the config module without external dependencies"""
    print("Testing config module...")
    
    try:
        from src.config import Config, setDebug, getDebug
        
        # Test Config class
        cfg = Config()
        assert cfg.debug is False
        assert cfg.mqtt_server == "192.168.50.24"
        assert cfg.mqtt_port == 1883
        
        # Test debug functions
        original_debug = getDebug()
        setDebug(True)
        assert getDebug() is True
        setDebug(False)
        assert getDebug() is False
        setDebug(original_debug)
        
        print("  ✅ Config module tests passed")
        return True
        
    except Exception as e:
        print(f"  ❌ Config module tests failed: {e}")
        return False


def test_mqtt_handlers():
    """Test MQTT handlers without external dependencies"""
    print("Testing MQTT handlers...")
    
    try:
        from src.mqtt_handlers import (
            MQTTMessageRouter,
            create_debug_handler,
            create_flag_handler,
            create_pit_handler,
            create_message_handler
        )
        
        # Test router
        router = MQTTMessageRouter()
        assert router.handlers == {}
        assert router.pattern_handlers == {}
        
        # Test handler registration
        handler = Mock()
        router.register_handler("test/topic", handler)
        assert "test/topic" in router.handlers
        
        # Test handler creation
        debug_handler = create_debug_handler()
        flag_handler = create_flag_handler()
        pit_handler = create_pit_handler()
        message_handler = create_message_handler()
        
        assert callable(debug_handler)
        assert callable(flag_handler)
        assert callable(pit_handler)
        assert callable(message_handler)
        
        print("  ✅ MQTT handlers tests passed")
        return True
        
    except Exception as e:
        print(f"  ❌ MQTT handlers tests failed: {e}")
        return False


def test_mock_objects():
    """Test mock objects work correctly"""
    print("Testing mock objects...")
    
    try:
        # Simple mock tests without external dependencies
        mock_mqtt = Mock()
        mock_mqtt.connected = False
        mock_mqtt.published_messages = []
        
        # Test mock functionality
        mock_mqtt.publish("test/topic", "test_payload")
        mock_mqtt.published_messages.append(("test/topic", "test_payload"))
        
        assert len(mock_mqtt.published_messages) == 1
        assert mock_mqtt.published_messages[0] == ("test/topic", "test_payload")
        
        # Test context manager mock
        class MockContextManager:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
        
        mock_context = MockContextManager()
        with mock_context as ctx:
            assert ctx is mock_context
        
        print("  ✅ Mock objects tests passed")
        return True
        
    except Exception as e:
        print(f"  ❌ Mock objects tests failed: {e}")
        return False


def test_client_basic_structure():
    """Test client basic structure without external dependencies"""
    print("Testing client basic structure...")
    
    try:
        # Mock external dependencies
        with patch('gpsd2.connect'), \
             patch('gpsd2.get_current'), \
             patch('obd.scan_serial'), \
             patch('obd.Async'), \
             patch('paho.mqtt.client.Client'), \
             patch('src.config.is_raspberrypi', return_value=False):
            
            from client import VTMSClient
            
            # Test basic initialization
            client = VTMSClient()
            assert client.mqttc is None
            assert client.obd_connection is None
            assert client.is_pi is False
            assert client.message_router is not None
        
        print("  ✅ Client basic structure tests passed")
        return True
        
    except Exception as e:
        print(f"  ❌ Client basic structure tests failed: {e}")
        return False


def run_all_tests():
    """Run all available tests"""
    print("VTMS Standalone Test Suite")
    print("=" * 50)
    
    tests = [
        test_config_module,
        test_mqtt_handlers,
        test_mock_objects,
        test_client_basic_structure,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ❌ Test {test.__name__} crashed: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)
    
    if failed == 0:
        print("🎉 All tests passed!")
    else:
        print("❌ Some tests failed")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
