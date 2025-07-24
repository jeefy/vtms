# VTMS Testing Suite

This directory contains comprehensive tests for the Vehicle Telemetry Management System (VTMS).

## Test Structure

### Unit Tests
- `test_client.py` - Tests for the main VTMSClient class
- `test_config.py` - Tests for configuration management
- `test_mqtt_handlers.py` - Tests for MQTT message routing and handlers
- `test_myobd.py` - Tests for OBD2 data processing functions

### Integration Tests
- `test_integration.py` - End-to-end system tests and performance tests

### Test Configuration
- `conftest.py` - Shared test fixtures and mock objects
- `pytest.ini` - Pytest configuration

## Running Tests

### Prerequisites

Install development dependencies:
```bash
pip install -r requirements-dev.txt
```

### Running All Tests

Using the test runner:
```bash
python run_tests.py
```

Using pytest directly:
```bash
pytest tests/ -v
```

### Running Specific Test Files

```bash
pytest tests/test_client.py -v
pytest tests/test_config.py -v
pytest tests/test_mqtt_handlers.py -v
pytest tests/test_myobd.py -v
pytest tests/test_integration.py -v
```

### Running Specific Test Classes or Methods

```bash
pytest tests/test_client.py::TestVTMSClient::test_init_not_raspberry_pi -v
pytest tests/test_integration.py::TestVTMSIntegration -v
```

## Test Coverage

To run tests with coverage:
```bash
pytest tests/ --cov=src --cov=client --cov-report=html
```

This will generate an HTML coverage report in `htmlcov/index.html`.

## Mock Objects

The test suite includes comprehensive mock objects for:

### OBD2 Mocking
- `MockOBDAsync` - Simulates OBD2 async connection
- `MockOBDResponse` - Simulates OBD2 command responses
- Mock commands and status handling

### MQTT Mocking
- `MockMQTTClient` - Simulates MQTT client functionality
- Message simulation capabilities
- Publish/subscribe tracking

### GPS Mocking
- `MockGPSPacket` - Simulates GPS data packets
- Configurable position, speed, altitude, and track data

## Test Categories

### 1. Unit Tests
Test individual components in isolation:
- Class initialization
- Method functionality
- Error handling
- Configuration management

### 2. Integration Tests
Test component interactions:
- MQTT message routing
- OBD2 data flow
- GPS data collection
- System startup/shutdown

### 3. Performance Tests
Test system performance:
- Message throughput
- GPS data collection rates
- Resource usage

## Key Test Features

### Async Testing
- Proper async/await test patterns
- Task management and cleanup
- Timeout handling

### Error Simulation
- Network connection failures
- Hardware unavailability
- Invalid data scenarios

### State Management
- Configuration changes
- Debug mode toggling
- Connection state tracking

### Resource Cleanup
- Proper mock cleanup
- Task cancellation
- Connection shutdown

## Test Best Practices

1. **Isolation** - Each test is independent and doesn't affect others
2. **Mocking** - External dependencies are mocked for reliability
3. **Coverage** - Tests cover both success and failure scenarios
4. **Performance** - Integration tests verify performance requirements
5. **Documentation** - Each test has clear docstrings explaining purpose

## Debugging Tests

To run tests with more verbose output:
```bash
pytest tests/ -v -s
```

To run tests and stop on first failure:
```bash
pytest tests/ -x
```

To run tests with pdb debugging:
```bash
pytest tests/ --pdb
```

## Continuous Integration

These tests are designed to run in CI/CD environments:
- No external dependencies required (all mocked)
- Fast execution (< 30 seconds for full suite)
- Clear pass/fail indicators
- Detailed error reporting

## Adding New Tests

When adding new functionality:

1. Add unit tests for the new component
2. Add integration tests for component interactions
3. Update mock objects if needed
4. Ensure new tests follow existing patterns
5. Update this README if new test categories are added
