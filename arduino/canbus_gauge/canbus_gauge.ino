/*
 * canbus_gauge.ino - ESP32 CAN Bus Gauge Cluster
 * 
 * Main sketch for the custom gauge cluster display.
 * 
 * Vehicle: 2007-2008 Acura TL (Manual Transmission)
 * 
 * Features:
 * - Tachometer with progressive color zones and shift light
 * - Speedometer (MPH)
 * - Water temperature gauge with warning/critical alerts
 * - Oil pressure gauge (analog sensor) with warning/critical alerts
 * - Audible buzzer for alerts
 * 
 * Hardware:
 * - ESP32 DevKit
 * - MCP2515 CAN transceiver
 * - Nextion 7" display
 * - 0-5V oil pressure sender
 * - Piezo buzzer
 * 
 * Author: VTMS Project
 * Date: 2026
 */

#include <SPI.h>
#include <mcp_can.h>

#include "config.h"
#include "obd_pids.h"
#include "can_handler.h"
#include "sensors.h"
#include "alerts.h"
#include "display_handler.h"

// =============================================================================
// GLOBAL OBJECTS
// =============================================================================

// CAN bus handler
CANHandler canHandler(CAN_CS_PIN, CAN_INT_PIN);

// Analog sensors
SensorHandler sensors;

// Alert handler
AlertHandler alerts;

// Display handler (using Serial2)
DisplayHandler display(Serial2);

// =============================================================================
// TIMING VARIABLES
// =============================================================================

uint32_t lastCANPoll = 0;
uint32_t lastSensorRead = 0;
uint32_t lastDisplayUpdate = 0;
uint32_t lastDebugPrint = 0;

uint8_t currentPIDIndex = 0;

// =============================================================================
// CURRENT VALUES
// =============================================================================

uint16_t currentRPM = 0;
uint8_t  currentSpeedMph = 0;
int16_t  currentWaterTempF = 0;
float    currentOilPsi = 0;

// =============================================================================
// SETUP
// =============================================================================

void setup() {
    // Initialize debug serial
    #if DEBUG_ENABLED
    Serial.begin(DEBUG_BAUD);
    while (!Serial && millis() < 3000); // Wait up to 3 seconds for Serial
    Serial.println();
    Serial.println("=================================");
    Serial.println("  ESP32 CAN Bus Gauge Cluster");
    Serial.println("  2007-2008 Acura TL");
    Serial.println("=================================");
    Serial.println();
    #endif
    
    // Initialize display first (show startup screen)
    Serial.println("Initializing display...");
    display.begin();
    display.showStartup("Initializing...");
    
    // Initialize CAN bus
    Serial.println("Initializing CAN bus...");
    display.showStartup("CAN Bus Init...");
    
    if (canHandler.begin()) {
        Serial.println("CAN bus: OK");
        display.setCANStatus(true);
    } else {
        Serial.println("CAN bus: FAILED");
        Serial.println(canHandler.getLastError());
        display.setCANStatus(false);
        display.showStartup("CAN FAILED!");
        // Continue anyway - might be useful for testing
    }
    
    // Initialize sensors
    Serial.println("Initializing sensors...");
    display.showStartup("Sensors Init...");
    sensors.begin();
    
    // Initialize alerts
    Serial.println("Initializing alerts...");
    alerts.begin();
    
    // Ready!
    Serial.println();
    Serial.println("System ready!");
    Serial.println();
    
    display.showStartup("Ready!");
    delay(1000);
    
    // Switch to main display
    display.goToPage(NextionID::PAGE_MAIN);
    
    // Print configuration
    #if DEBUG_ENABLED
    printConfig();
    #endif
}

// =============================================================================
// MAIN LOOP
// =============================================================================

void loop() {
    uint32_t now = millis();
    
    // --- Poll CAN bus for OBD data ---
    if (now - lastCANPoll >= CAN_POLL_MS) {
        lastCANPoll = now;
        pollCANData();
    }
    
    // --- Process incoming CAN messages ---
    while (canHandler.processMessages()) {
        // Keep processing until no more messages
        updateFromCAN();
    }
    
    // --- Read analog sensors ---
    if (now - lastSensorRead >= SENSOR_READ_MS) {
        lastSensorRead = now;
        readSensors();
    }
    
    // --- Update alerts ---
    alerts.update(currentRPM, currentWaterTempF, currentOilPsi);
    
    // --- Update display ---
    if (now - lastDisplayUpdate >= DISPLAY_UPDATE_MS) {
        lastDisplayUpdate = now;
        updateDisplay();
    }
    
    // --- Debug output ---
    #if DEBUG_ENABLED
    if (now - lastDebugPrint >= 1000) {
        lastDebugPrint = now;
        printDebugInfo();
    }
    #endif
}

// =============================================================================
// CAN BUS POLLING
// =============================================================================

void pollCANData() {
    // Query next PID in sequence
    if (currentPIDIndex >= NUM_QUERY_PIDS) {
        currentPIDIndex = 0;
    }
    
    uint8_t pid = QUERY_PIDS[currentPIDIndex];
    canHandler.queryPID(pid);
    
    currentPIDIndex++;
}

void updateFromCAN() {
    if (canHandler.hasNewData()) {
        OBDData_t data = canHandler.getData();
        
        // Update current values
        currentRPM = data.rpm;
        currentSpeedMph = data.speed_mph;
        currentWaterTempF = data.coolant_temp_f;
        
        canHandler.clearNewDataFlag();
    }
}

// =============================================================================
// SENSOR READING
// =============================================================================

void readSensors() {
    sensors.update();
    
    SensorData_t sensorData = sensors.getData();
    currentOilPsi = sensorData.oilPressurePsi;
}

// =============================================================================
// DISPLAY UPDATE
// =============================================================================

void updateDisplay() {
    display.update(currentRPM, currentSpeedMph, currentWaterTempF, 
                   currentOilPsi, alerts);
}

// =============================================================================
// DEBUG FUNCTIONS
// =============================================================================

#if DEBUG_ENABLED
void printConfig() {
    Serial.println("--- Configuration ---");
    Serial.printf("CAN Speed: 500 kbps\n");
    Serial.printf("Shift RPM: %d (warning at %d)\n", SHIFT_RPM, SHIFT_WARNING_RPM);
    Serial.printf("Water Temp Warning: %d°F, Critical: %d°F\n", 
                  WATER_TEMP_WARNING, WATER_TEMP_CRITICAL);
    Serial.printf("Oil Pressure Warning: <%d PSI, Critical: <%d PSI\n",
                  OIL_PRESSURE_WARNING, OIL_PRESSURE_CRITICAL);
    Serial.printf("Buzzer: %s\n", BUZZER_ENABLED ? "Enabled" : "Disabled");
    Serial.println("---------------------");
    Serial.println();
}

void printDebugInfo() {
    Serial.println("--- Current Values ---");
    Serial.printf("RPM: %d\n", currentRPM);
    Serial.printf("Speed: %d MPH\n", currentSpeedMph);
    Serial.printf("Water Temp: %d°F\n", currentWaterTempF);
    Serial.printf("Oil Pressure: %.1f PSI\n", currentOilPsi);
    Serial.printf("CAN Queries: %lu, Responses: %lu, Errors: %lu\n",
                  canHandler.getQueryCount(),
                  canHandler.getResponseCount(),
                  canHandler.getErrorCount());
    
    AlertState_t alertState = alerts.getState();
    if (alertState.shiftActive) Serial.println("*** SHIFT LIGHT ACTIVE ***");
    if (alertState.tempWarning) Serial.println("*** TEMP WARNING ***");
    if (alertState.tempCritical) Serial.println("*** TEMP CRITICAL ***");
    if (alertState.oilWarning) Serial.println("*** OIL WARNING ***");
    if (alertState.oilCritical) Serial.println("*** OIL CRITICAL ***");
    
    Serial.println("----------------------");
    Serial.println();
}
#endif

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

// Can be called from serial commands for testing
void simulateValues(uint16_t rpm, uint8_t speed, int16_t temp, float oil) {
    currentRPM = rpm;
    currentSpeedMph = speed;
    currentWaterTempF = temp;
    currentOilPsi = oil;
    
    Serial.printf("Simulated: RPM=%d, Speed=%d, Temp=%d, Oil=%.1f\n",
                  rpm, speed, temp, oil);
}
