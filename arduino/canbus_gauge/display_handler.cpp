/*
 * display_handler.cpp - Nextion display implementation
 */

#include "display_handler.h"

DisplayHandler::DisplayHandler(HardwareSerial& serial) : _serial(serial) {
    _lastUpdate = 0;
    _shiftVisible = false;
    _alertVisible = false;
    
    _lastRPM = 0xFFFF;  // Invalid value to force initial update
    _lastSpeed = 0xFF;
    _lastTemp = -999;
    _lastOil = -1;
    _lastRPMColor = 0;
    _lastTempColor = 0;
    _lastOilColor = 0;
}

void DisplayHandler::begin() {
    _serial.begin(NEXTION_BAUD, SERIAL_8N1, NEXTION_RX_PIN, NEXTION_TX_PIN);
    
    // Wait for display to initialize
    delay(500);
    
    // Send empty commands to clear any garbage
    for (int i = 0; i < 3; i++) {
        endCommand();
        delay(50);
    }
    
    // Reset display
    sendCommand("rest");
    delay(1000);
    
    // Set baud rate (in case display default differs)
    sendCommand("baud=%d", NEXTION_BAUD);
    delay(100);
    
    // Go to main page
    goToPage(NextionID::PAGE_MAIN);
    
    // Initialize default states
    hideAlert();
    showShiftLight(false);
    setCANStatus(false);
    
    #if DEBUG_ENABLED
    Serial.println("Display initialized");
    #endif
}

void DisplayHandler::update(uint16_t rpm, uint8_t speedMph, int16_t waterTempF, 
                            float oilPressurePsi, AlertHandler& alerts) {
    // Throttle updates to prevent overwhelming the display
    if (millis() - _lastUpdate < DISPLAY_UPDATE_MS) {
        return;
    }
    _lastUpdate = millis();
    
    // Get colors from alert handler
    uint16_t rpmColor = alerts.getRPMColor(rpm);
    uint16_t tempColor = alerts.getTempColor(waterTempF);
    uint16_t oilColor = alerts.getOilColor(oilPressurePsi);
    
    // Update values only if changed
    if (rpm != _lastRPM || rpmColor != _lastRPMColor) {
        setRPM(rpm, rpmColor);
        _lastRPM = rpm;
        _lastRPMColor = rpmColor;
    }
    
    if (speedMph != _lastSpeed) {
        setSpeed(speedMph);
        _lastSpeed = speedMph;
    }
    
    if (waterTempF != _lastTemp || tempColor != _lastTempColor) {
        setWaterTemp(waterTempF, tempColor);
        _lastTemp = waterTempF;
        _lastTempColor = tempColor;
    }
    
    if (abs(oilPressurePsi - _lastOil) > 0.5 || oilColor != _lastOilColor) {
        setOilPressure(oilPressurePsi, oilColor);
        _lastOil = oilPressurePsi;
        _lastOilColor = oilColor;
    }
    
    // Handle shift light
    if (alerts.isShiftActive()) {
        // Flash the shift light
        showShiftLight(alerts.getFlashState());
    } else {
        showShiftLight(false);
    }
    
    // Handle critical alerts
    if (alerts.isTempCritical()) {
        if (alerts.getFlashState()) {
            showAlert("HOT!", COLOR_RED);
        } else {
            hideAlert();
        }
    } else if (alerts.isOilCritical()) {
        if (alerts.getFlashState()) {
            showAlert("OIL LOW!", COLOR_RED);
        } else {
            hideAlert();
        }
    } else if (alerts.isTempWarning()) {
        showAlert("TEMP WARN", COLOR_YELLOW);
    } else if (alerts.isOilWarning()) {
        showAlert("OIL WARN", COLOR_YELLOW);
    } else {
        hideAlert();
    }
}

void DisplayHandler::setRPM(uint16_t rpm, uint16_t color) {
    // Set RPM text value
    setText(NextionID::RPM_VALUE, (int)rpm);
    
    // Set progress bar (0-100 scale)
    // Map RPM_MIN-RPM_MAX to 0-100
    uint8_t progress = map(constrain(rpm, RPM_MIN, RPM_MAX), 
                          RPM_MIN, RPM_MAX, 0, 100);
    setProgress(NextionID::RPM_GAUGE, progress);
    
    // Set gauge color
    setColor(NextionID::RPM_GAUGE, color);
}

void DisplayHandler::setSpeed(uint8_t mph) {
    setText(NextionID::SPEED_VALUE, (int)mph);
}

void DisplayHandler::setWaterTemp(int16_t tempF, uint16_t color) {
    setText(NextionID::TEMP_VALUE, (int)tempF);
    
    // Set progress bar (map WATER_TEMP_MIN-WATER_TEMP_MAX to 0-100)
    uint8_t progress = map(constrain(tempF, WATER_TEMP_MIN, WATER_TEMP_MAX),
                          WATER_TEMP_MIN, WATER_TEMP_MAX, 0, 100);
    setProgress(NextionID::TEMP_GAUGE, progress);
    
    // Set gauge color
    setColor(NextionID::TEMP_GAUGE, color);
}

void DisplayHandler::setOilPressure(float psi, uint16_t color) {
    setText(NextionID::OIL_VALUE, (int)psi);
    
    // Set progress bar
    uint8_t progress = map(constrain((int)psi, OIL_PRESSURE_MIN, OIL_PRESSURE_MAX),
                          OIL_PRESSURE_MIN, OIL_PRESSURE_MAX, 0, 100);
    setProgress(NextionID::OIL_GAUGE, progress);
    
    // Set gauge color
    setColor(NextionID::OIL_GAUGE, color);
}

void DisplayHandler::showShiftLight(bool show) {
    if (show != _shiftVisible) {
        setVisible(NextionID::SHIFT_OVERLAY, show);
        _shiftVisible = show;
    }
}

void DisplayHandler::showAlert(const char* message, uint16_t color) {
    setText(NextionID::ALERT_TEXT, message);
    setColor(NextionID::ALERT_OVERLAY, color);
    
    if (!_alertVisible) {
        setVisible(NextionID::ALERT_OVERLAY, true);
        _alertVisible = true;
    }
}

void DisplayHandler::hideAlert() {
    if (_alertVisible) {
        setVisible(NextionID::ALERT_OVERLAY, false);
        _alertVisible = false;
    }
}

void DisplayHandler::setCANStatus(bool connected) {
    setColor(NextionID::CAN_STATUS, connected ? COLOR_GREEN : COLOR_RED);
}

void DisplayHandler::goToPage(const char* pageName) {
    _serial.print("page ");
    _serial.print(pageName);
    endCommand();
}

void DisplayHandler::showStartup(const char* message) {
    goToPage(NextionID::PAGE_STARTUP);
    delay(50);
    setText("startup_txt", message);
}

void DisplayHandler::sendCommand(const char* cmd) {
    _serial.print(cmd);
    endCommand();
}

void DisplayHandler::sendCommand(const char* format, int value) {
    char buf[64];
    snprintf(buf, sizeof(buf), format, value);
    _serial.print(buf);
    endCommand();
}

void DisplayHandler::sendCommand(const char* format, const char* value) {
    char buf[64];
    snprintf(buf, sizeof(buf), format, value);
    _serial.print(buf);
    endCommand();
}

void DisplayHandler::endCommand() {
    // Nextion commands end with three 0xFF bytes
    _serial.write(0xFF);
    _serial.write(0xFF);
    _serial.write(0xFF);
}

void DisplayHandler::setNumber(const char* component, int32_t value) {
    _serial.print(component);
    _serial.print(".val=");
    _serial.print(value);
    endCommand();
}

void DisplayHandler::setText(const char* component, const char* text) {
    _serial.print(component);
    _serial.print(".txt=\"");
    _serial.print(text);
    _serial.print("\"");
    endCommand();
}

void DisplayHandler::setText(const char* component, int value) {
    char buf[16];
    snprintf(buf, sizeof(buf), "%d", value);
    setText(component, buf);
}

void DisplayHandler::setProgress(const char* component, uint8_t value) {
    // Progress bar uses .val property
    setNumber(component, constrain(value, 0, 100));
}

void DisplayHandler::setColor(const char* component, uint16_t color) {
    // Set foreground color (.pco property)
    _serial.print(component);
    _serial.print(".pco=");
    _serial.print(color);
    endCommand();
}

void DisplayHandler::setVisible(const char* component, bool visible) {
    // Nextion uses vis command
    _serial.print("vis ");
    _serial.print(component);
    _serial.print(",");
    _serial.print(visible ? 1 : 0);
    endCommand();
}
