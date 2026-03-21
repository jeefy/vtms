/*
 * alerts.h - Alert and shift light handling
 * 
 * Manages threshold checking, alerts, and buzzer control.
 */

#ifndef ALERTS_H
#define ALERTS_H

#include <Arduino.h>
#include "config.h"

// Alert types
typedef enum {
    ALERT_NONE = 0,
    ALERT_SHIFT,            // Shift light triggered
    ALERT_TEMP_WARNING,     // Water temp warning
    ALERT_TEMP_CRITICAL,    // Water temp critical
    ALERT_OIL_WARNING,      // Oil pressure warning  
    ALERT_OIL_CRITICAL      // Oil pressure critical
} AlertType_t;

// Alert state structure
typedef struct {
    bool shiftActive;           // Shift light active
    bool shiftWarning;          // Pre-shift warning active
    bool tempWarning;           // Temp warning active
    bool tempCritical;          // Temp critical active
    bool oilWarning;            // Oil warning active
    bool oilCritical;           // Oil critical active
    
    bool flashState;            // Current flash state (for blinking)
    uint32_t lastFlashTime;     // Last flash toggle time
    
    AlertType_t highestPriority; // Highest priority active alert
} AlertState_t;

// RPM zone for progressive tachometer
typedef enum {
    RPM_ZONE_1_GREEN = 0,
    RPM_ZONE_2_YELLOW,
    RPM_ZONE_3_ORANGE,
    RPM_ZONE_4_RED
} RPMZone_t;

class AlertHandler {
public:
    AlertHandler();
    
    // Initialize alerts and buzzer
    void begin();
    
    // Update alerts based on current values
    void update(uint16_t rpm, int16_t waterTempF, float oilPressurePsi);
    
    // Get alert state
    AlertState_t getState();
    
    // Check individual alerts
    bool isShiftActive();
    bool isShiftWarning();
    bool isTempWarning();
    bool isTempCritical();
    bool isOilWarning();
    bool isOilCritical();
    bool hasAnyAlert();
    bool hasCriticalAlert();
    
    // Get flash state for blinking alerts
    bool getFlashState();
    
    // Get RPM zone for progressive tachometer
    RPMZone_t getRPMZone(uint16_t rpm);
    
    // Get color for RPM value (returns RGB565)
    uint16_t getRPMColor(uint16_t rpm);
    
    // Get color for temperature (returns RGB565)
    uint16_t getTempColor(int16_t tempF);
    
    // Get color for oil pressure (returns RGB565)
    uint16_t getOilColor(float psi);
    
    // Buzzer control
    void setBuzzerEnabled(bool enabled);
    void silenceBuzzer();  // Temporarily silence
    
private:
    AlertState_t _state;
    bool _buzzerEnabled;
    bool _buzzerSilenced;
    uint32_t _silenceUntil;
    
    // Update flash state
    void updateFlash();
    
    // Update buzzer based on alerts
    void updateBuzzer();
    
    // Play buzzer tone
    void playTone(uint16_t frequency, uint32_t duration);
    void stopTone();
};

#endif // ALERTS_H
