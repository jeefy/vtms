/*
 * obd_pids.h - OBD-II PID definitions for CAN Bus Gauge Cluster
 * 
 * Standard OBD-II PIDs used for querying vehicle data.
 * Reference: SAE J1979 / ISO 15031-5
 */

#ifndef OBD_PIDS_H
#define OBD_PIDS_H

#include <stdint.h>

// =============================================================================
// OBD-II SERVICE MODES
// =============================================================================

#define OBD_SERVICE_CURRENT_DATA    0x01    // Show current data
#define OBD_SERVICE_FREEZE_FRAME    0x02    // Show freeze frame data
#define OBD_SERVICE_STORED_DTC      0x03    // Show stored DTCs
#define OBD_SERVICE_CLEAR_DTC       0x04    // Clear DTCs
#define OBD_SERVICE_VEHICLE_INFO    0x09    // Request vehicle information

// =============================================================================
// OBD-II PARAMETER IDs (PIDs) - SERVICE 01
// =============================================================================

// Supported PIDs
#define PID_SUPPORTED_01_20         0x00    // PIDs supported [01-20]
#define PID_SUPPORTED_21_40         0x20    // PIDs supported [21-40]
#define PID_SUPPORTED_41_60         0x40    // PIDs supported [41-60]
#define PID_SUPPORTED_61_80         0x60    // PIDs supported [61-80]

// Engine data
#define PID_MONITOR_STATUS          0x01    // Monitor status since DTCs cleared
#define PID_FREEZE_DTC              0x02    // Freeze DTC
#define PID_FUEL_SYSTEM_STATUS      0x03    // Fuel system status
#define PID_ENGINE_LOAD             0x04    // Calculated engine load (%)
#define PID_COOLANT_TEMP            0x05    // Engine coolant temperature (°C)
#define PID_SHORT_FUEL_TRIM_1       0x06    // Short term fuel trim - Bank 1
#define PID_LONG_FUEL_TRIM_1        0x07    // Long term fuel trim - Bank 1
#define PID_SHORT_FUEL_TRIM_2       0x08    // Short term fuel trim - Bank 2
#define PID_LONG_FUEL_TRIM_2        0x09    // Long term fuel trim - Bank 2
#define PID_FUEL_PRESSURE           0x0A    // Fuel pressure (kPa gauge)
#define PID_INTAKE_MAP              0x0B    // Intake manifold absolute pressure
#define PID_ENGINE_RPM              0x0C    // Engine RPM
#define PID_VEHICLE_SPEED           0x0D    // Vehicle speed (km/h)
#define PID_TIMING_ADVANCE          0x0E    // Timing advance (° before TDC)
#define PID_INTAKE_TEMP             0x0F    // Intake air temperature (°C)
#define PID_MAF_FLOW                0x10    // MAF air flow rate (g/s)
#define PID_THROTTLE_POSITION       0x11    // Throttle position (%)

// O2 sensors
#define PID_O2_SENSORS_PRESENT      0x13    // O2 sensors present (2 banks)
#define PID_O2_B1S1                 0x14    // O2 sensor 1, Bank 1
#define PID_O2_B1S2                 0x15    // O2 sensor 2, Bank 1
#define PID_O2_B1S3                 0x16    // O2 sensor 3, Bank 1
#define PID_O2_B1S4                 0x17    // O2 sensor 4, Bank 1
#define PID_O2_B2S1                 0x18    // O2 sensor 1, Bank 2
#define PID_O2_B2S2                 0x19    // O2 sensor 2, Bank 2
#define PID_O2_B2S3                 0x1A    // O2 sensor 3, Bank 2
#define PID_O2_B2S4                 0x1B    // O2 sensor 4, Bank 2

// Other data
#define PID_OBD_STANDARDS           0x1C    // OBD standards this vehicle conforms to
#define PID_O2_SENSORS_PRESENT_4B   0x1D    // O2 sensors present (4 banks)
#define PID_AUX_INPUT_STATUS        0x1E    // Auxiliary input status
#define PID_RUN_TIME                0x1F    // Run time since engine start (s)

// Extended PIDs
#define PID_DISTANCE_W_MIL          0x21    // Distance traveled with MIL on (km)
#define PID_FUEL_RAIL_PRESSURE      0x22    // Fuel rail pressure (kPa)
#define PID_FUEL_RAIL_GAUGE_PRESS   0x23    // Fuel rail gauge pressure (kPa)
#define PID_COMMANDED_EGR           0x2C    // Commanded EGR (%)
#define PID_EGR_ERROR               0x2D    // EGR error (%)
#define PID_EVAP_PURGE              0x2E    // Commanded evaporative purge (%)
#define PID_FUEL_LEVEL              0x2F    // Fuel tank level input (%)
#define PID_WARMUPS_SINCE_CLEAR     0x30    // Warm-ups since codes cleared
#define PID_DISTANCE_SINCE_CLEAR    0x31    // Distance traveled since codes cleared (km)
#define PID_EVAP_PRESSURE           0x32    // Evap system vapor pressure (Pa)
#define PID_BAROMETRIC_PRESSURE     0x33    // Absolute barometric pressure (kPa)

// Catalyst temperature
#define PID_CATALYST_TEMP_B1S1      0x3C    // Catalyst temp Bank 1, Sensor 1
#define PID_CATALYST_TEMP_B2S1      0x3D    // Catalyst temp Bank 2, Sensor 1
#define PID_CATALYST_TEMP_B1S2      0x3E    // Catalyst temp Bank 1, Sensor 2
#define PID_CATALYST_TEMP_B2S2      0x3F    // Catalyst temp Bank 2, Sensor 2

// Control module
#define PID_CONTROL_MODULE_VOLTAGE  0x42    // Control module voltage (V)
#define PID_ABSOLUTE_LOAD           0x43    // Absolute load value (%)
#define PID_COMMANDED_AFR           0x44    // Commanded air-fuel ratio
#define PID_RELATIVE_THROTTLE       0x45    // Relative throttle position (%)
#define PID_AMBIENT_TEMP            0x46    // Ambient air temperature (°C)
#define PID_THROTTLE_POS_B          0x47    // Absolute throttle position B (%)
#define PID_THROTTLE_POS_C          0x48    // Absolute throttle position C (%)
#define PID_ACCEL_POS_D             0x49    // Accelerator pedal position D (%)
#define PID_ACCEL_POS_E             0x4A    // Accelerator pedal position E (%)
#define PID_ACCEL_POS_F             0x4B    // Accelerator pedal position F (%)
#define PID_COMMANDED_THROTTLE      0x4C    // Commanded throttle actuator (%)
#define PID_TIME_WITH_MIL           0x4D    // Time run with MIL on (min)
#define PID_TIME_SINCE_CLEAR        0x4E    // Time since codes cleared (min)

// Fuel info
#define PID_FUEL_TYPE               0x51    // Fuel type
#define PID_ETHANOL_PERCENT         0x52    // Ethanol fuel percentage (%)

// Oil temperature (not all vehicles support this)
#define PID_OIL_TEMP                0x5C    // Engine oil temperature (°C)
#define PID_FUEL_INJECTION_TIMING   0x5D    // Fuel injection timing (°)
#define PID_FUEL_RATE               0x5E    // Engine fuel rate (L/h)

// =============================================================================
// PID DATA STRUCTURES
// =============================================================================

// Structure to hold decoded OBD-II data
typedef struct {
    uint16_t rpm;               // Engine RPM
    uint8_t  speed_kmh;         // Vehicle speed in km/h
    uint8_t  speed_mph;         // Vehicle speed in MPH
    int16_t  coolant_temp_c;    // Coolant temp in Celsius
    int16_t  coolant_temp_f;    // Coolant temp in Fahrenheit
    uint8_t  throttle_pos;      // Throttle position %
    uint8_t  engine_load;       // Engine load %
    int16_t  intake_temp_c;     // Intake air temp Celsius
    int16_t  oil_temp_c;        // Oil temp Celsius (if supported)
    int16_t  oil_temp_f;        // Oil temp Fahrenheit
    float    battery_voltage;   // Control module voltage
    uint32_t run_time;          // Run time since start (seconds)
    bool     valid;             // Data validity flag
} OBDData_t;

// Structure for PID query/response
typedef struct {
    uint8_t  pid;               // PID number
    uint8_t  dataBytes;         // Number of data bytes expected
    const char* name;           // Human-readable name
} PIDInfo_t;

// =============================================================================
// PID CALCULATION FUNCTIONS (inline for speed)
// =============================================================================

// Calculate RPM from OBD response bytes A and B
// Formula: ((A * 256) + B) / 4
inline uint16_t calculateRPM(uint8_t a, uint8_t b) {
    return ((uint16_t)a * 256 + b) / 4;
}

// Calculate vehicle speed from OBD response byte A (returns km/h)
// Formula: A (direct)
inline uint8_t calculateSpeedKmh(uint8_t a) {
    return a;
}

// Convert km/h to MPH
inline uint8_t calculateSpeedMph(uint8_t kmh) {
    return (uint8_t)(kmh * 0.621371);
}

// Calculate coolant temperature from OBD response byte A (returns °C)
// Formula: A - 40
inline int16_t calculateCoolantTempC(uint8_t a) {
    return (int16_t)a - 40;
}

// Convert Celsius to Fahrenheit
inline int16_t celsiusToFahrenheit(int16_t celsius) {
    return (celsius * 9 / 5) + 32;
}

// Calculate throttle position from OBD response byte A (returns %)
// Formula: A * 100 / 255
inline uint8_t calculateThrottlePos(uint8_t a) {
    return (uint8_t)((uint16_t)a * 100 / 255);
}

// Calculate engine load from OBD response byte A (returns %)
// Formula: A * 100 / 255
inline uint8_t calculateEngineLoad(uint8_t a) {
    return (uint8_t)((uint16_t)a * 100 / 255);
}

// Calculate intake air temperature from OBD response byte A (returns °C)
// Formula: A - 40
inline int16_t calculateIntakeTempC(uint8_t a) {
    return (int16_t)a - 40;
}

// Calculate oil temperature from OBD response byte A (returns °C)
// Formula: A - 40
inline int16_t calculateOilTempC(uint8_t a) {
    return (int16_t)a - 40;
}

// Calculate control module voltage from OBD response bytes A and B (returns V)
// Formula: ((A * 256) + B) / 1000
inline float calculateVoltage(uint8_t a, uint8_t b) {
    return ((float)((uint16_t)a * 256 + b)) / 1000.0;
}

// Calculate run time from OBD response bytes A and B (returns seconds)
// Formula: (A * 256) + B
inline uint32_t calculateRunTime(uint8_t a, uint8_t b) {
    return (uint32_t)a * 256 + b;
}

// =============================================================================
// PID LIST FOR QUERIES
// =============================================================================

// PIDs we want to query regularly (in order of priority)
static const uint8_t QUERY_PIDS[] = {
    PID_ENGINE_RPM,         // Most important - for shift light
    PID_VEHICLE_SPEED,      // Speed display
    PID_COOLANT_TEMP,       // Water temperature
    // PID_OIL_TEMP,        // Uncomment if your vehicle supports it
};

static const uint8_t NUM_QUERY_PIDS = sizeof(QUERY_PIDS) / sizeof(QUERY_PIDS[0]);

#endif // OBD_PIDS_H
