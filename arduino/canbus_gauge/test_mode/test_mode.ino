/*
 * test_mode.ino - Test mode for gauge cluster without CAN bus
 * 
 * This sketch allows you to test the display and alerts without
 * needing the car's CAN bus connected. Use serial commands to
 * simulate different values.
 * 
 * Serial Commands (115200 baud):
 *   r <value>  - Set RPM (e.g., "r 6500")
 *   s <value>  - Set Speed MPH (e.g., "s 65")
 *   t <value>  - Set Water Temp °F (e.g., "t 210")
 *   o <value>  - Set Oil Pressure PSI (e.g., "o 30")
 *   a          - Auto-cycle through demo values
 *   x          - Stop auto-cycle
 *   b          - Toggle buzzer on/off
 *   ?          - Show help
 */

#include <Arduino.h>
#include "config.h"
#include "obd_pids.h"
#include "sensors.h"
#include "alerts.h"
#include "display_handler.h"

// Handlers
SensorHandler sensors;
AlertHandler alerts;
DisplayHandler display(Serial2);

// Test values
uint16_t testRPM = 2500;
uint8_t testSpeed = 45;
int16_t testWaterTemp = 195;
float testOilPsi = 55;

// Auto-cycle mode
bool autoCycle = false;
uint32_t lastAutoCycle = 0;
int autoCyclePhase = 0;

// Serial input buffer
char serialBuffer[64];
int bufferIndex = 0;

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 3000);
    
    Serial.println();
    Serial.println("================================");
    Serial.println("  Gauge Cluster TEST MODE");
    Serial.println("================================");
    Serial.println();
    Serial.println("Commands:");
    Serial.println("  r <rpm>   - Set RPM");
    Serial.println("  s <mph>   - Set Speed");
    Serial.println("  t <temp>  - Set Water Temp (F)");
    Serial.println("  o <psi>   - Set Oil Pressure");
    Serial.println("  a         - Auto demo cycle");
    Serial.println("  x         - Stop auto cycle");
    Serial.println("  b         - Toggle buzzer");
    Serial.println("  ?         - Show this help");
    Serial.println();
    
    // Initialize display
    Serial.println("Initializing display...");
    display.begin();
    display.showStartup("TEST MODE");
    delay(1500);
    display.goToPage(NextionID::PAGE_MAIN);
    display.setCANStatus(true);  // Fake "connected" for testing
    
    // Initialize alerts
    alerts.begin();
    
    Serial.println("Ready! Enter commands:");
}

void loop() {
    // Process serial input
    processSerial();
    
    // Handle auto-cycle mode
    if (autoCycle) {
        runAutoCycle();
    }
    
    // Update alerts
    alerts.update(testRPM, testWaterTemp, testOilPsi);
    
    // Update display
    static uint32_t lastDisplayUpdate = 0;
    if (millis() - lastDisplayUpdate >= DISPLAY_UPDATE_MS) {
        lastDisplayUpdate = millis();
        display.update(testRPM, testSpeed, testWaterTemp, testOilPsi, alerts);
    }
}

void processSerial() {
    while (Serial.available()) {
        char c = Serial.read();
        
        if (c == '\n' || c == '\r') {
            if (bufferIndex > 0) {
                serialBuffer[bufferIndex] = '\0';
                processCommand(serialBuffer);
                bufferIndex = 0;
            }
        } else if (bufferIndex < sizeof(serialBuffer) - 1) {
            serialBuffer[bufferIndex++] = c;
        }
    }
}

void processCommand(char* cmd) {
    char type = cmd[0];
    int value = 0;
    
    if (strlen(cmd) > 2) {
        value = atoi(&cmd[2]);
    }
    
    switch (type) {
        case 'r':
        case 'R':
            testRPM = constrain(value, 0, 8000);
            Serial.printf("RPM set to: %d\n", testRPM);
            break;
            
        case 's':
        case 'S':
            testSpeed = constrain(value, 0, 160);
            Serial.printf("Speed set to: %d MPH\n", testSpeed);
            break;
            
        case 't':
        case 'T':
            testWaterTemp = constrain(value, 100, 260);
            Serial.printf("Water Temp set to: %d°F\n", testWaterTemp);
            break;
            
        case 'o':
        case 'O':
            testOilPsi = constrain(value, 0, 100);
            Serial.printf("Oil Pressure set to: %.0f PSI\n", testOilPsi);
            break;
            
        case 'a':
        case 'A':
            autoCycle = true;
            autoCyclePhase = 0;
            Serial.println("Auto-cycle mode STARTED");
            break;
            
        case 'x':
        case 'X':
            autoCycle = false;
            Serial.println("Auto-cycle mode STOPPED");
            break;
            
        case 'b':
        case 'B':
            {
                static bool buzzerOn = true;
                buzzerOn = !buzzerOn;
                alerts.setBuzzerEnabled(buzzerOn);
                Serial.printf("Buzzer: %s\n", buzzerOn ? "ON" : "OFF");
            }
            break;
            
        case '?':
            Serial.println("Commands:");
            Serial.println("  r <rpm>   - Set RPM");
            Serial.println("  s <mph>   - Set Speed");
            Serial.println("  t <temp>  - Set Water Temp (F)");
            Serial.println("  o <psi>   - Set Oil Pressure");
            Serial.println("  a         - Auto demo cycle");
            Serial.println("  x         - Stop auto cycle");
            Serial.println("  b         - Toggle buzzer");
            break;
            
        default:
            Serial.println("Unknown command. Type ? for help.");
    }
    
    // Print current values
    Serial.printf("Current: RPM=%d, Speed=%d MPH, Temp=%d°F, Oil=%.0f PSI\n",
                  testRPM, testSpeed, testWaterTemp, testOilPsi);
}

void runAutoCycle() {
    if (millis() - lastAutoCycle < 100) {
        return;
    }
    lastAutoCycle = millis();
    
    // Different demo phases
    switch (autoCyclePhase) {
        case 0:
            // Ramp up RPM
            testRPM += 50;
            testSpeed = map(testRPM, 0, 7000, 0, 120);
            if (testRPM >= 7000) {
                autoCyclePhase = 1;
                Serial.println("Phase 1: Ramp down");
            }
            break;
            
        case 1:
            // Ramp down RPM
            testRPM -= 50;
            testSpeed = map(testRPM, 0, 7000, 0, 120);
            if (testRPM <= 1000) {
                testRPM = 3000;
                autoCyclePhase = 2;
                Serial.println("Phase 2: Temp warning test");
            }
            break;
            
        case 2:
            // Temperature warning test
            testWaterTemp += 1;
            if (testWaterTemp >= 220) {
                testWaterTemp = 195;
                autoCyclePhase = 3;
                Serial.println("Phase 3: Oil pressure warning test");
            }
            break;
            
        case 3:
            // Oil pressure warning test
            testOilPsi -= 1;
            if (testOilPsi <= 20) {
                testOilPsi = 55;
                autoCyclePhase = 0;
                testRPM = 1000;
                Serial.println("Phase 0: Ramp up");
            }
            break;
    }
}
