/*
 * display_handler.h - Nextion display communication
 * 
 * Handles all communication with the Nextion 7" display.
 */

#ifndef DISPLAY_HANDLER_H
#define DISPLAY_HANDLER_H

#include <Arduino.h>
#include "config.h"
#include "alerts.h"

// Nextion component IDs (must match HMI design)
// These are the object names in the Nextion Editor
namespace NextionID {
    // Page names
    const char PAGE_MAIN[] = "main";
    const char PAGE_STARTUP[] = "startup";
    const char PAGE_ALERT[] = "alert";
    
    // Main page components
    const char RPM_GAUGE[] = "rpm_gauge";       // Progress bar for RPM
    const char RPM_VALUE[] = "rpm_val";         // Text: RPM number
    const char SPEED_VALUE[] = "speed_val";     // Text: Speed number
    const char SPEED_UNIT[] = "speed_unit";     // Text: "MPH"
    
    const char TEMP_GAUGE[] = "temp_gauge";     // Progress bar for temp
    const char TEMP_VALUE[] = "temp_val";       // Text: Temperature number
    const char TEMP_UNIT[] = "temp_unit";       // Text: "°F"
    
    const char OIL_GAUGE[] = "oil_gauge";       // Progress bar for oil
    const char OIL_VALUE[] = "oil_val";         // Text: Oil pressure number
    const char OIL_UNIT[] = "oil_unit";         // Text: "PSI"
    
    const char SHIFT_OVERLAY[] = "shift_box";   // Shift light overlay
    const char ALERT_OVERLAY[] = "alert_box";   // Alert overlay
    const char ALERT_TEXT[] = "alert_txt";      // Alert text
    
    // Status indicators
    const char CAN_STATUS[] = "can_stat";       // CAN connection status
}

class DisplayHandler {
public:
    DisplayHandler(HardwareSerial& serial);
    
    // Initialize display
    void begin();
    
    // Update display with current values
    void update(uint16_t rpm, uint8_t speedMph, int16_t waterTempF, 
                float oilPressurePsi, AlertHandler& alerts);
    
    // Set individual values
    void setRPM(uint16_t rpm, uint16_t color);
    void setSpeed(uint8_t mph);
    void setWaterTemp(int16_t tempF, uint16_t color);
    void setOilPressure(float psi, uint16_t color);
    
    // Show/hide overlays
    void showShiftLight(bool show);
    void showAlert(const char* message, uint16_t color);
    void hideAlert();
    
    // Set CAN status indicator
    void setCANStatus(bool connected);
    
    // Change page
    void goToPage(const char* pageName);
    
    // Show startup screen
    void showStartup(const char* message);
    
    // Raw command sending
    void sendCommand(const char* cmd);
    void sendCommand(const char* format, int value);
    void sendCommand(const char* format, const char* value);

private:
    HardwareSerial& _serial;
    
    uint32_t _lastUpdate;
    bool _shiftVisible;
    bool _alertVisible;
    
    // Last sent values (to avoid redundant updates)
    uint16_t _lastRPM;
    uint8_t _lastSpeed;
    int16_t _lastTemp;
    float _lastOil;
    uint16_t _lastRPMColor;
    uint16_t _lastTempColor;
    uint16_t _lastOilColor;
    
    // End command with Nextion terminator
    void endCommand();
    
    // Set numeric value
    void setNumber(const char* component, int32_t value);
    
    // Set text value
    void setText(const char* component, const char* text);
    void setText(const char* component, int value);
    
    // Set progress bar value (0-100)
    void setProgress(const char* component, uint8_t value);
    
    // Set component color
    void setColor(const char* component, uint16_t color);
    
    // Set visibility
    void setVisible(const char* component, bool visible);
};

#endif // DISPLAY_HANDLER_H
