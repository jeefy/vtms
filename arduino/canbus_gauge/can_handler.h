/*
 * can_handler.h - CAN Bus communication handler for MCP2515
 * 
 * Handles OBD-II queries and responses via CAN bus.
 */

#ifndef CAN_HANDLER_H
#define CAN_HANDLER_H

#include <Arduino.h>
#include <mcp_can.h>
#include "config.h"
#include "obd_pids.h"

class CANHandler {
public:
    CANHandler(uint8_t csPin, uint8_t intPin);
    
    // Initialize CAN bus
    bool begin();
    
    // Check if CAN bus is connected
    bool isConnected();
    
    // Query a specific PID
    bool queryPID(uint8_t pid);
    
    // Process incoming CAN messages (call frequently)
    bool processMessages();
    
    // Get the latest OBD data
    OBDData_t getData();
    
    // Check if new data is available
    bool hasNewData();
    
    // Clear the new data flag
    void clearNewDataFlag();
    
    // Get last error message
    const char* getLastError();
    
    // Get statistics
    uint32_t getQueryCount();
    uint32_t getResponseCount();
    uint32_t getErrorCount();

private:
    MCP_CAN* _can;
    uint8_t _csPin;
    uint8_t _intPin;
    
    bool _connected;
    bool _newData;
    OBDData_t _obdData;
    
    uint32_t _lastQueryTime;
    uint8_t _currentPidIndex;
    
    // Statistics
    uint32_t _queryCount;
    uint32_t _responseCount;
    uint32_t _errorCount;
    
    char _lastError[64];
    
    // Parse OBD-II response
    void parseResponse(uint8_t* data, uint8_t len);
    
    // Send OBD-II query
    bool sendQuery(uint8_t service, uint8_t pid);
};

#endif // CAN_HANDLER_H
