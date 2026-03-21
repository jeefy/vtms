/*
 * can_handler.cpp - CAN Bus communication implementation
 */

#include "can_handler.h"

CANHandler::CANHandler(uint8_t csPin, uint8_t intPin) {
    _csPin = csPin;
    _intPin = intPin;
    _can = new MCP_CAN(csPin);
    
    _connected = false;
    _newData = false;
    _lastQueryTime = 0;
    _currentPidIndex = 0;
    
    _queryCount = 0;
    _responseCount = 0;
    _errorCount = 0;
    
    memset(&_obdData, 0, sizeof(OBDData_t));
    memset(_lastError, 0, sizeof(_lastError));
}

bool CANHandler::begin() {
    // Initialize MCP2515 with specified speed
    // Try multiple times in case of startup issues
    for (int attempt = 0; attempt < 3; attempt++) {
        if (_can->begin(MCP_ANY, CAN_SPEED, CAN_CLOCK) == CAN_OK) {
            // Set to normal mode
            _can->setMode(MCP_NORMAL);
            
            // Set up interrupt pin
            pinMode(_intPin, INPUT);
            
            _connected = true;
            
            #if DEBUG_ENABLED
            Serial.println("CAN bus initialized successfully");
            #endif
            
            return true;
        }
        delay(100);
    }
    
    strncpy(_lastError, "CAN init failed after 3 attempts", sizeof(_lastError));
    _connected = false;
    return false;
}

bool CANHandler::isConnected() {
    return _connected;
}

bool CANHandler::queryPID(uint8_t pid) {
    if (!_connected) {
        return false;
    }
    
    return sendQuery(OBD_SERVICE_CURRENT_DATA, pid);
}

bool CANHandler::sendQuery(uint8_t service, uint8_t pid) {
    // OBD-II query format:
    // Byte 0: Number of additional bytes (2 for standard query)
    // Byte 1: Service (01 = current data)
    // Byte 2: PID
    // Bytes 3-7: Padding (0x55 or 0xCC per ISO 15765-2)
    
    uint8_t txData[8] = {0x02, service, pid, 0xCC, 0xCC, 0xCC, 0xCC, 0xCC};
    
    // Send to broadcast address 0x7DF
    byte result = _can->sendMsgBuf(OBD_REQUEST_ID, 0, 8, txData);
    
    if (result == CAN_OK) {
        _queryCount++;
        _lastQueryTime = millis();
        
        #if DEBUG_CAN_MESSAGES
        Serial.printf("CAN TX: Service=0x%02X PID=0x%02X\n", service, pid);
        #endif
        
        return true;
    } else {
        _errorCount++;
        snprintf(_lastError, sizeof(_lastError), "CAN send failed: %d", result);
        return false;
    }
}

bool CANHandler::processMessages() {
    if (!_connected) {
        return false;
    }
    
    // Check if there's a message waiting
    if (digitalRead(_intPin) == LOW || _can->checkReceive() == CAN_MSGAVAIL) {
        unsigned long rxId;
        uint8_t len;
        uint8_t rxBuf[8];
        
        // Read the message
        _can->readMsgBuf(&rxId, &len, rxBuf);
        
        #if DEBUG_CAN_MESSAGES
        Serial.printf("CAN RX: ID=0x%03lX Len=%d Data=", rxId, len);
        for (int i = 0; i < len; i++) {
            Serial.printf("%02X ", rxBuf[i]);
        }
        Serial.println();
        #endif
        
        // Check if it's an OBD-II response (0x7E8-0x7EF)
        if (rxId >= OBD_RESPONSE_ID_MIN && rxId <= OBD_RESPONSE_ID_MAX) {
            parseResponse(rxBuf, len);
            _responseCount++;
            return true;
        }
    }
    
    return false;
}

void CANHandler::parseResponse(uint8_t* data, uint8_t len) {
    // OBD-II response format:
    // Byte 0: Number of additional bytes
    // Byte 1: Service + 0x40 (e.g., 0x41 for service 0x01)
    // Byte 2: PID
    // Bytes 3+: Data
    
    if (len < 4) {
        return; // Invalid response
    }
    
    uint8_t numBytes = data[0];
    uint8_t service = data[1];
    uint8_t pid = data[2];
    
    // Verify it's a response to service 01
    if (service != (OBD_SERVICE_CURRENT_DATA + 0x40)) {
        return;
    }
    
    // Parse based on PID
    switch (pid) {
        case PID_ENGINE_RPM:
            // Data bytes: A, B -> RPM = ((A * 256) + B) / 4
            if (numBytes >= 4) {
                _obdData.rpm = calculateRPM(data[3], data[4]);
                _obdData.valid = true;
                _newData = true;
                
                #if DEBUG_SENSOR_VALUES
                Serial.printf("RPM: %d\n", _obdData.rpm);
                #endif
            }
            break;
            
        case PID_VEHICLE_SPEED:
            // Data byte: A -> Speed in km/h
            if (numBytes >= 3) {
                _obdData.speed_kmh = calculateSpeedKmh(data[3]);
                _obdData.speed_mph = calculateSpeedMph(_obdData.speed_kmh);
                _newData = true;
                
                #if DEBUG_SENSOR_VALUES
                Serial.printf("Speed: %d km/h (%d mph)\n", _obdData.speed_kmh, _obdData.speed_mph);
                #endif
            }
            break;
            
        case PID_COOLANT_TEMP:
            // Data byte: A -> Temp = A - 40 (°C)
            if (numBytes >= 3) {
                _obdData.coolant_temp_c = calculateCoolantTempC(data[3]);
                _obdData.coolant_temp_f = celsiusToFahrenheit(_obdData.coolant_temp_c);
                _newData = true;
                
                #if DEBUG_SENSOR_VALUES
                Serial.printf("Coolant Temp: %d°C (%d°F)\n", _obdData.coolant_temp_c, _obdData.coolant_temp_f);
                #endif
            }
            break;
            
        case PID_THROTTLE_POSITION:
            if (numBytes >= 3) {
                _obdData.throttle_pos = calculateThrottlePos(data[3]);
                _newData = true;
            }
            break;
            
        case PID_ENGINE_LOAD:
            if (numBytes >= 3) {
                _obdData.engine_load = calculateEngineLoad(data[3]);
                _newData = true;
            }
            break;
            
        case PID_INTAKE_TEMP:
            if (numBytes >= 3) {
                _obdData.intake_temp_c = calculateIntakeTempC(data[3]);
                _newData = true;
            }
            break;
            
        case PID_OIL_TEMP:
            if (numBytes >= 3) {
                _obdData.oil_temp_c = calculateOilTempC(data[3]);
                _obdData.oil_temp_f = celsiusToFahrenheit(_obdData.oil_temp_c);
                _newData = true;
            }
            break;
            
        case PID_CONTROL_MODULE_VOLTAGE:
            if (numBytes >= 4) {
                _obdData.battery_voltage = calculateVoltage(data[3], data[4]);
                _newData = true;
            }
            break;
            
        case PID_RUN_TIME:
            if (numBytes >= 4) {
                _obdData.run_time = calculateRunTime(data[3], data[4]);
                _newData = true;
            }
            break;
    }
}

OBDData_t CANHandler::getData() {
    return _obdData;
}

bool CANHandler::hasNewData() {
    return _newData;
}

void CANHandler::clearNewDataFlag() {
    _newData = false;
}

const char* CANHandler::getLastError() {
    return _lastError;
}

uint32_t CANHandler::getQueryCount() {
    return _queryCount;
}

uint32_t CANHandler::getResponseCount() {
    return _responseCount;
}

uint32_t CANHandler::getErrorCount() {
    return _errorCount;
}
