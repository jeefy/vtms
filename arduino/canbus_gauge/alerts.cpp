/*
 * alerts.cpp - Alert and shift light implementation
 */

#include "alerts.h"

AlertHandler::AlertHandler() {
    memset(&_state, 0, sizeof(AlertState_t));
    _buzzerEnabled = BUZZER_ENABLED;
    _buzzerSilenced = false;
    _silenceUntil = 0;
}

void AlertHandler::begin() {
    // Configure buzzer pin
    pinMode(BUZZER_PIN, OUTPUT);
    digitalWrite(BUZZER_PIN, LOW);
    
    // Initialize PWM for buzzer (ESP32 LEDC)
    ledcSetup(0, 2000, 8);  // Channel 0, 2kHz default, 8-bit resolution
    ledcAttachPin(BUZZER_PIN, 0);
    ledcWrite(0, 0);  // Start silent
    
    #if DEBUG_ENABLED
    Serial.println("Alert handler initialized");
    Serial.printf("Buzzer pin: GPIO%d, Enabled: %s\n", 
                  BUZZER_PIN, _buzzerEnabled ? "Yes" : "No");
    #endif
}

void AlertHandler::update(uint16_t rpm, int16_t waterTempF, float oilPressurePsi) {
    // Update flash state for blinking
    updateFlash();
    
    // Check unsilence
    if (_buzzerSilenced && millis() > _silenceUntil) {
        _buzzerSilenced = false;
    }
    
    // --- RPM / Shift Light ---
    _state.shiftWarning = (rpm >= SHIFT_WARNING_RPM && rpm < SHIFT_RPM);
    _state.shiftActive = (rpm >= SHIFT_RPM);
    
    // --- Water Temperature ---
    _state.tempWarning = (waterTempF >= WATER_TEMP_WARNING && waterTempF < WATER_TEMP_CRITICAL);
    _state.tempCritical = (waterTempF >= WATER_TEMP_CRITICAL);
    
    // --- Oil Pressure ---
    // Oil pressure alerts are triggered when BELOW threshold
    _state.oilWarning = (oilPressurePsi < OIL_PRESSURE_WARNING && 
                         oilPressurePsi >= OIL_PRESSURE_CRITICAL);
    _state.oilCritical = (oilPressurePsi < OIL_PRESSURE_CRITICAL);
    
    // Only trigger oil alerts if engine is running (RPM > 500)
    // to avoid false alerts at startup
    if (rpm < 500) {
        _state.oilWarning = false;
        _state.oilCritical = false;
    }
    
    // --- Determine highest priority alert ---
    if (_state.tempCritical) {
        _state.highestPriority = ALERT_TEMP_CRITICAL;
    } else if (_state.oilCritical) {
        _state.highestPriority = ALERT_OIL_CRITICAL;
    } else if (_state.shiftActive) {
        _state.highestPriority = ALERT_SHIFT;
    } else if (_state.tempWarning) {
        _state.highestPriority = ALERT_TEMP_WARNING;
    } else if (_state.oilWarning) {
        _state.highestPriority = ALERT_OIL_WARNING;
    } else {
        _state.highestPriority = ALERT_NONE;
    }
    
    // Update buzzer
    updateBuzzer();
    
    #if DEBUG_ENABLED
    static AlertType_t lastAlert = ALERT_NONE;
    if (_state.highestPriority != lastAlert) {
        const char* alertNames[] = {
            "NONE", "SHIFT", "TEMP_WARNING", "TEMP_CRITICAL", 
            "OIL_WARNING", "OIL_CRITICAL"
        };
        Serial.printf("Alert changed: %s\n", alertNames[_state.highestPriority]);
        lastAlert = _state.highestPriority;
    }
    #endif
}

void AlertHandler::updateFlash() {
    uint32_t now = millis();
    if (now - _state.lastFlashTime >= ALERT_FLASH_MS) {
        _state.flashState = !_state.flashState;
        _state.lastFlashTime = now;
    }
}

void AlertHandler::updateBuzzer() {
    if (!_buzzerEnabled || _buzzerSilenced) {
        stopTone();
        return;
    }
    
    // Determine what tone to play based on alerts
    if (_state.tempCritical && BUZZER_TEMP_ENABLED) {
        // Critical temperature - continuous high tone
        if (_state.flashState) {
            playTone(BUZZER_CRITICAL_FREQ, 0);
        } else {
            stopTone();
        }
    } else if (_state.oilCritical && BUZZER_OIL_ENABLED) {
        // Critical oil pressure - continuous high tone
        if (_state.flashState) {
            playTone(BUZZER_CRITICAL_FREQ, 0);
        } else {
            stopTone();
        }
    } else if (_state.shiftActive && BUZZER_SHIFT_ENABLED) {
        // Shift light - rapid beeping
        if (_state.flashState) {
            playTone(BUZZER_SHIFT_FREQ, 0);
        } else {
            stopTone();
        }
    } else if ((_state.tempWarning || _state.oilWarning) && 
               (BUZZER_TEMP_ENABLED || BUZZER_OIL_ENABLED)) {
        // Warning - slower beep
        static uint32_t lastWarnBeep = 0;
        if (millis() - lastWarnBeep > 2000) {  // Beep every 2 seconds
            playTone(BUZZER_WARNING_FREQ, 200);
            lastWarnBeep = millis();
        }
    } else {
        stopTone();
    }
}

void AlertHandler::playTone(uint16_t frequency, uint32_t duration) {
    ledcChangeFrequency(0, frequency, 8);
    ledcWrite(0, 128);  // 50% duty cycle
    
    if (duration > 0) {
        delay(duration);
        stopTone();
    }
}

void AlertHandler::stopTone() {
    ledcWrite(0, 0);
}

AlertState_t AlertHandler::getState() {
    return _state;
}

bool AlertHandler::isShiftActive() {
    return _state.shiftActive;
}

bool AlertHandler::isShiftWarning() {
    return _state.shiftWarning;
}

bool AlertHandler::isTempWarning() {
    return _state.tempWarning;
}

bool AlertHandler::isTempCritical() {
    return _state.tempCritical;
}

bool AlertHandler::isOilWarning() {
    return _state.oilWarning;
}

bool AlertHandler::isOilCritical() {
    return _state.oilCritical;
}

bool AlertHandler::hasAnyAlert() {
    return _state.highestPriority != ALERT_NONE;
}

bool AlertHandler::hasCriticalAlert() {
    return _state.tempCritical || _state.oilCritical;
}

bool AlertHandler::getFlashState() {
    return _state.flashState;
}

RPMZone_t AlertHandler::getRPMZone(uint16_t rpm) {
    if (rpm >= RPM_ZONE_RED) {
        return RPM_ZONE_4_RED;
    } else if (rpm >= RPM_ZONE_ORANGE) {
        return RPM_ZONE_3_ORANGE;
    } else if (rpm >= RPM_ZONE_YELLOW) {
        return RPM_ZONE_2_YELLOW;
    } else {
        return RPM_ZONE_1_GREEN;
    }
}

uint16_t AlertHandler::getRPMColor(uint16_t rpm) {
    RPMZone_t zone = getRPMZone(rpm);
    switch (zone) {
        case RPM_ZONE_4_RED:
            return COLOR_RPM_RED;
        case RPM_ZONE_3_ORANGE:
            return COLOR_RPM_ORANGE;
        case RPM_ZONE_2_YELLOW:
            return COLOR_RPM_YELLOW;
        case RPM_ZONE_1_GREEN:
        default:
            return COLOR_RPM_GREEN;
    }
}

uint16_t AlertHandler::getTempColor(int16_t tempF) {
    if (tempF >= WATER_TEMP_CRITICAL) {
        return COLOR_TEMP_CRITICAL;
    } else if (tempF >= WATER_TEMP_WARNING) {
        return COLOR_TEMP_WARNING;
    } else {
        return COLOR_TEMP_NORMAL;
    }
}

uint16_t AlertHandler::getOilColor(float psi) {
    if (psi < OIL_PRESSURE_CRITICAL) {
        return COLOR_OIL_CRITICAL;
    } else if (psi < OIL_PRESSURE_WARNING) {
        return COLOR_OIL_WARNING;
    } else {
        return COLOR_OIL_NORMAL;
    }
}

void AlertHandler::setBuzzerEnabled(bool enabled) {
    _buzzerEnabled = enabled;
    if (!enabled) {
        stopTone();
    }
}

void AlertHandler::silenceBuzzer() {
    _buzzerSilenced = true;
    _silenceUntil = millis() + 30000;  // Silence for 30 seconds
    stopTone();
    
    #if DEBUG_ENABLED
    Serial.println("Buzzer silenced for 30 seconds");
    #endif
}
