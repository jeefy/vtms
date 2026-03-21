/*
 * sensors.h - Analog sensor handling (Oil Pressure)
 * 
 * Handles reading and calibrating the 0-5V oil pressure sender.
 */

#ifndef SENSORS_H
#define SENSORS_H

#include <Arduino.h>
#include "config.h"

// Moving average filter template
template<typename T, int SIZE>
class MovingAverage {
public:
    MovingAverage() : _index(0), _count(0), _sum(0) {
        memset(_samples, 0, sizeof(_samples));
    }
    
    T add(T value) {
        _sum -= _samples[_index];
        _samples[_index] = value;
        _sum += value;
        _index = (_index + 1) % SIZE;
        if (_count < SIZE) _count++;
        return _sum / _count;
    }
    
    T get() {
        return (_count > 0) ? (_sum / _count) : 0;
    }
    
    void reset() {
        _index = 0;
        _count = 0;
        _sum = 0;
        memset(_samples, 0, sizeof(_samples));
    }
    
private:
    T _samples[SIZE];
    int _index;
    int _count;
    T _sum;
};

// Structure to hold all sensor data
typedef struct {
    float oilPressurePsi;       // Oil pressure in PSI
    float oilPressureRaw;       // Raw voltage reading
    bool  oilPressureValid;     // Sensor reading valid
} SensorData_t;

class SensorHandler {
public:
    SensorHandler();
    
    // Initialize sensors
    void begin();
    
    // Read all sensors (call at SENSOR_READ_MS interval)
    void update();
    
    // Get sensor data
    SensorData_t getData();
    
    // Get individual readings
    float getOilPressurePsi();
    float getOilPressureVoltage();
    
    // Calibration
    void setOilPressureCalibration(float vMin, float vMax, float psiMax);
    
private:
    SensorData_t _sensorData;
    
    // Oil pressure calibration
    float _oilVMin;     // Voltage at 0 PSI
    float _oilVMax;     // Voltage at max PSI
    float _oilPsiMax;   // Max PSI reading
    
    // Moving average filters
    MovingAverage<float, OIL_SMOOTHING_SAMPLES> _oilFilter;
    
    // Read oil pressure sensor
    float readOilPressure();
    
    // Convert ADC reading to voltage
    float adcToVoltage(int adcValue);
    
    // Convert voltage to PSI
    float voltageToPsi(float voltage);
};

#endif // SENSORS_H
