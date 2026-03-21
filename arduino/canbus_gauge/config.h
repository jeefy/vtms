/*
 * config.h - Configuration and thresholds for CAN Bus Gauge Cluster
 * 
 * Vehicle: 2007-2008 Acura TL (Manual Transmission)
 * 
 * All thresholds are easily configurable here.
 */

#ifndef CONFIG_H
#define CONFIG_H

// =============================================================================
// HARDWARE PIN CONFIGURATION
// =============================================================================

// MCP2515 CAN Controller (SPI)
#define CAN_CS_PIN      5       // Chip Select
#define CAN_INT_PIN     4       // Interrupt pin
// SPI pins are fixed on ESP32 VSPI:
// SCK  = GPIO18
// MOSI = GPIO23
// MISO = GPIO19

// Nextion Display (UART2)
#define NEXTION_TX_PIN  17      // ESP32 TX -> Nextion RX
#define NEXTION_RX_PIN  16      // ESP32 RX -> Nextion TX
#define NEXTION_BAUD    115200  // Nextion serial baud rate

// Analog Sensors
#define OIL_PRESSURE_PIN    34  // ADC1_CH6 (0-5V oil pressure sender)

// Buzzer Output
#define BUZZER_PIN      25      // PWM capable pin for buzzer

// =============================================================================
// CAN BUS CONFIGURATION
// =============================================================================

#define CAN_SPEED       CAN_500KBPS     // 2007-2008 Acura TL uses 500kbps
#define CAN_CLOCK       MCP_8MHZ        // MCP2515 crystal (common: 8MHz or 16MHz)

// OBD-II CAN IDs
#define OBD_REQUEST_ID      0x7DF       // Broadcast request ID
#define OBD_RESPONSE_ID_MIN 0x7E8       // ECU response range start
#define OBD_RESPONSE_ID_MAX 0x7EF       // ECU response range end

// =============================================================================
// TIMING CONFIGURATION (milliseconds)
// =============================================================================

#define DISPLAY_UPDATE_MS   100     // Display refresh rate (10 Hz)
#define CAN_POLL_MS         50      // CAN polling rate (20 Hz)
#define SENSOR_READ_MS      50      // Analog sensor read rate (20 Hz)
#define ALERT_FLASH_MS      250     // Alert flash interval
#define CAN_TIMEOUT_MS      100     // Timeout waiting for CAN response

// =============================================================================
// RPM THRESHOLDS & SHIFT LIGHT
// =============================================================================

#define RPM_MIN             0       // Minimum RPM display
#define RPM_MAX             8000    // Maximum RPM display (redline area)
#define RPM_REDLINE         7100    // Acura TL redline

// Shift light thresholds
#define SHIFT_RPM           6300    // RPM to trigger SHIFT alert
#define SHIFT_WARNING_RPM   6000    // Pre-warning zone (yellow/orange)

// Progressive tachometer color zones (RPM values)
#define RPM_ZONE_GREEN      0       // Green zone start
#define RPM_ZONE_YELLOW     4500    // Yellow zone start
#define RPM_ZONE_ORANGE     5500    // Orange zone start  
#define RPM_ZONE_RED        6300    // Red zone start

// =============================================================================
// WATER TEMPERATURE THRESHOLDS (Fahrenheit)
// =============================================================================

#define WATER_TEMP_MIN      100     // Minimum display temp
#define WATER_TEMP_MAX      260     // Maximum display temp
#define WATER_TEMP_NORMAL   195     // Normal operating temp
#define WATER_TEMP_WARNING  205     // Warning threshold (yellow)
#define WATER_TEMP_CRITICAL 215     // Critical threshold (red alert)

// =============================================================================
// OIL PRESSURE THRESHOLDS (PSI)
// =============================================================================

#define OIL_PRESSURE_MIN        0       // Minimum display
#define OIL_PRESSURE_MAX        100     // Maximum display (for 0-100 PSI sender)
#define OIL_PRESSURE_NORMAL     55      // Normal operating pressure
#define OIL_PRESSURE_WARNING    45      // Warning threshold (yellow)
#define OIL_PRESSURE_CRITICAL   25      // Critical threshold (red alert)

// Oil pressure sensor calibration (0-5V sender to 0-100 PSI)
// Typical 0-5V sender: 0.5V = 0 PSI, 4.5V = 100 PSI
#define OIL_SENSOR_V_MIN        0.5     // Voltage at 0 PSI
#define OIL_SENSOR_V_MAX        4.5     // Voltage at max PSI
#define OIL_SENSOR_PSI_MAX      100.0   // Max PSI reading

// ESP32 ADC calibration
#define ADC_RESOLUTION      4095        // 12-bit ADC
#define ADC_VREF            3.3         // ESP32 ADC reference voltage
// Note: For 5V sensor, use a voltage divider (e.g., 10k/10k) to scale to 3.3V
#define VOLTAGE_DIVIDER_RATIO   2.0     // If using voltage divider (5V -> 2.5V max)

// =============================================================================
// SPEED CONFIGURATION
// =============================================================================

#define SPEED_MIN           0       // Minimum speed display
#define SPEED_MAX           160     // Maximum speed display (MPH)
#define SPEED_UNIT_MPH      true    // true = MPH, false = km/h
#define KMH_TO_MPH          0.621371

// =============================================================================
// ALERT CONFIGURATION
// =============================================================================

// Buzzer tones (Hz)
#define BUZZER_SHIFT_FREQ       2500    // Shift light buzzer frequency
#define BUZZER_WARNING_FREQ     1500    // Warning alert frequency
#define BUZZER_CRITICAL_FREQ    3000    // Critical alert frequency

// Buzzer enable/disable
#define BUZZER_ENABLED          true    // Set to false to disable buzzer
#define BUZZER_SHIFT_ENABLED    true    // Buzzer on shift light
#define BUZZER_TEMP_ENABLED     true    // Buzzer on temp critical
#define BUZZER_OIL_ENABLED      true    // Buzzer on oil pressure critical

// =============================================================================
// DISPLAY COLORS (Nextion RGB565 format)
// =============================================================================

// RGB565 color values for Nextion display
#define COLOR_BLACK         0x0000
#define COLOR_WHITE         0xFFFF
#define COLOR_RED           0xF800
#define COLOR_GREEN         0x07E0
#define COLOR_BLUE          0x001F
#define COLOR_YELLOW        0xFFE0
#define COLOR_ORANGE        0xFD20
#define COLOR_CYAN          0x07FF
#define COLOR_DARK_GRAY     0x4208
#define COLOR_LIGHT_GRAY    0xC618

// Gauge-specific colors
#define COLOR_RPM_GREEN     0x07E0
#define COLOR_RPM_YELLOW    0xFFE0
#define COLOR_RPM_ORANGE    0xFD20
#define COLOR_RPM_RED       0xF800
#define COLOR_TEMP_NORMAL   0x07E0
#define COLOR_TEMP_WARNING  0xFFE0
#define COLOR_TEMP_CRITICAL 0xF800
#define COLOR_OIL_NORMAL    0x07E0
#define COLOR_OIL_WARNING   0xFFE0
#define COLOR_OIL_CRITICAL  0xF800

// =============================================================================
// SMOOTHING / FILTERING
// =============================================================================

#define RPM_SMOOTHING_SAMPLES       5   // Moving average samples for RPM
#define SPEED_SMOOTHING_SAMPLES     3   // Moving average samples for speed
#define TEMP_SMOOTHING_SAMPLES      10  // Moving average samples for temp
#define OIL_SMOOTHING_SAMPLES       5   // Moving average samples for oil pressure

// =============================================================================
// DEBUG CONFIGURATION
// =============================================================================

#define DEBUG_ENABLED       true        // Enable serial debug output
#define DEBUG_BAUD          115200      // Debug serial baud rate
#define DEBUG_CAN_MESSAGES  false       // Print raw CAN messages
#define DEBUG_SENSOR_VALUES true        // Print sensor values periodically

#endif // CONFIG_H
