/*
 * sensors.cpp - Analog sensor handling implementation
 */

#include "sensors.h"

SensorHandler::SensorHandler() {
    memset(&_sensorData, 0, sizeof(SensorData_t));
    
    // Default calibration from config
    _oilVMin = OIL_SENSOR_V_MIN;
    _oilVMax = OIL_SENSOR_V_MAX;
    _oilPsiMax = OIL_SENSOR_PSI_MAX;
}

void SensorHandler::begin() {
    // Configure ADC
    analogReadResolution(12);  // 12-bit resolution (0-4095)
    analogSetAttenuation(ADC_11db);  // Full range: 0-3.3V
    
    // Configure oil pressure pin
    pinMode(OIL_PRESSURE_PIN, INPUT);
    
    // Take a few readings to stabilize
    for (int i = 0; i < 10; i++) {
        readOilPressure();
        delay(10);
    }
    
    #if DEBUG_ENABLED
    Serial.println("Sensors initialized");
    Serial.printf("Oil pressure pin: GPIO%d\n", OIL_PRESSURE_PIN);
    Serial.printf("Oil calibration: %.2fV-%.2fV = 0-%.0f PSI\n", 
                  _oilVMin, _oilVMax, _oilPsiMax);
    #endif
}

void SensorHandler::update() {
    // Read and filter oil pressure
    float rawPsi = readOilPressure();
    _sensorData.oilPressurePsi = _oilFilter.add(rawPsi);
    
    // Validate reading (check if sensor is connected)
    // A completely disconnected sensor will read near 0V or 3.3V
    float voltage = _sensorData.oilPressureRaw;
    _sensorData.oilPressureValid = (voltage > 0.1 && voltage < 3.2);
    
    #if DEBUG_SENSOR_VALUES
    static uint32_t lastPrint = 0;
    if (millis() - lastPrint > 1000) {  // Print every second
        Serial.printf("Oil Pressure: %.1f PSI (%.2fV) %s\n", 
                     _sensorData.oilPressurePsi,
                     _sensorData.oilPressureRaw,
                     _sensorData.oilPressureValid ? "OK" : "INVALID");
        lastPrint = millis();
    }
    #endif
}

float SensorHandler::readOilPressure() {
    // Read ADC multiple times and average for noise reduction
    int sum = 0;
    const int samples = 4;
    
    for (int i = 0; i < samples; i++) {
        sum += analogRead(OIL_PRESSURE_PIN);
    }
    int adcValue = sum / samples;
    
    // Convert to voltage (accounting for voltage divider)
    float voltage = adcToVoltage(adcValue);
    _sensorData.oilPressureRaw = voltage;
    
    // Convert voltage to PSI
    return voltageToPsi(voltage);
}

float SensorHandler::adcToVoltage(int adcValue) {
    // Convert ADC value to voltage
    // ADC reads 0-3.3V as 0-4095
    float voltage = (float)adcValue / ADC_RESOLUTION * ADC_VREF;
    
    // Account for voltage divider if used
    // If using a divider to scale 5V to 3.3V, multiply back
    #if VOLTAGE_DIVIDER_RATIO > 1.0
    voltage *= VOLTAGE_DIVIDER_RATIO;
    #endif
    
    return voltage;
}

float SensorHandler::voltageToPsi(float voltage) {
    // Linear interpolation from voltage to PSI
    // Typical 0-5V sender: 0.5V = 0 PSI, 4.5V = 100 PSI
    
    // Clamp voltage to calibration range
    if (voltage <= _oilVMin) {
        return 0.0;
    }
    if (voltage >= _oilVMax) {
        return _oilPsiMax;
    }
    
    // Linear interpolation
    float psi = ((voltage - _oilVMin) / (_oilVMax - _oilVMin)) * _oilPsiMax;
    
    // Clamp to valid range
    if (psi < 0) psi = 0;
    if (psi > _oilPsiMax) psi = _oilPsiMax;
    
    return psi;
}

SensorData_t SensorHandler::getData() {
    return _sensorData;
}

float SensorHandler::getOilPressurePsi() {
    return _sensorData.oilPressurePsi;
}

float SensorHandler::getOilPressureVoltage() {
    return _sensorData.oilPressureRaw;
}

void SensorHandler::setOilPressureCalibration(float vMin, float vMax, float psiMax) {
    _oilVMin = vMin;
    _oilVMax = vMax;
    _oilPsiMax = psiMax;
    
    // Reset filter when calibration changes
    _oilFilter.reset();
    
    #if DEBUG_ENABLED
    Serial.printf("Oil pressure calibration updated: %.2fV-%.2fV = 0-%.0f PSI\n",
                  vMin, vMax, psiMax);
    #endif
}
