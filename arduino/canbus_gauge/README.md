# ESP32 CAN Bus Gauge Cluster

Custom digital gauge cluster for **2007-2008 Acura TL (Manual Transmission)** using ESP32 and Nextion 7" display.

## Features

- **Tachometer** with progressive color zones (green → yellow → orange → red)
- **Shift Light** with flashing visual alert at 6300 RPM
- **Speedometer** (MPH)
- **Water Temperature** gauge with warning (205°F) and critical (215°F) alerts
- **Oil Pressure** gauge with warning (<45 PSI) and critical (<25 PSI) alerts
- **Audible Buzzer** for shift light and critical alerts
- **CAN Bus** connection status indicator

## Hardware Requirements

### Components

| Component | Description | Notes |
|-----------|-------------|-------|
| ESP32 DevKit | Main controller | Any ESP32 dev board |
| MCP2515 Module | CAN bus transceiver | With TJA1050 driver |
| Nextion 7" Display | NX8048P070 or similar | 800x480 resolution |
| Oil Pressure Sender | 0-5V, 0-100 PSI | Generic automotive sender |
| Piezo Buzzer | Active or passive | 3.3V compatible |
| LM2596 Buck Converter | 12V → 5V | Powers Nextion display |
| AMS1117-3.3 | 5V → 3.3V | Powers ESP32 (or use onboard) |

### Wiring Diagram

```
                    ┌─────────────────┐
                    │     ESP32       │
                    │                 │
    MCP2515         │  GPIO5  ← CS    │
    ┌──────┐        │  GPIO18 ← SCK   │
    │      │ SPI    │  GPIO23 ← MOSI  │
    │      ├───────►│  GPIO19 → MISO  │
    │      │        │  GPIO4  ← INT   │
    │      │        │                 │
    │ CAN-H├──┐     │  GPIO17 → TX2 ──┼──► Nextion RX
    │ CAN-L├──┤     │  GPIO16 ← RX2 ──┼──► Nextion TX
    └──────┘  │     │                 │
              │     │  GPIO34 ← ADC ──┼──► Oil Pressure Sensor
         To OBD-II  │                 │
         Port       │  GPIO25 → PWM ──┼──► Buzzer
         Pin 6,14   │                 │
                    │  3.3V, GND      │
                    └─────────────────┘

OBD-II Connector Pinout:
  Pin 4:  Chassis Ground
  Pin 5:  Signal Ground  
  Pin 6:  CAN-High (connect to MCP2515 CAN-H)
  Pin 14: CAN-Low (connect to MCP2515 CAN-L)
  Pin 16: Battery Power (+12V)
```

### Oil Pressure Sensor Wiring

For a 0-5V oil pressure sender with ESP32's 3.3V ADC:

```
Oil Pressure      Voltage Divider       ESP32
Sender            (10kΩ resistors)
  │                                       
  ├──────────┬──────[10kΩ]──────► GPIO34 (ADC)
  │          │
[0-5V]      [10kΩ]
  │          │
  └──GND─────┴──────────────────► GND
```

This divides the 0-5V signal to 0-2.5V (safe for ESP32 ADC).

## Software Setup

### Arduino IDE Setup

1. Install ESP32 board support:
   - File → Preferences → Additional Board Manager URLs
   - Add: `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
   - Tools → Board → Board Manager → Search "ESP32" → Install

2. Install required libraries:
   - Sketch → Include Library → Manage Libraries
   - Search and install: **MCP_CAN** by coryjfowler

3. Select board:
   - Tools → Board → ESP32 Dev Module
   - Tools → Upload Speed → 921600
   - Tools → Flash Frequency → 80MHz

### Configuration

All settings are in `config.h`:

```cpp
// Shift Light
#define SHIFT_RPM           6300    // Trigger shift alert
#define SHIFT_WARNING_RPM   6000    // Pre-warning zone

// Water Temperature (°F)
#define WATER_TEMP_WARNING  205     // Warning threshold
#define WATER_TEMP_CRITICAL 215     // Critical threshold

// Oil Pressure (PSI)
#define OIL_PRESSURE_WARNING    45  // Warning below this
#define OIL_PRESSURE_CRITICAL   25  // Critical below this

// Buzzer
#define BUZZER_ENABLED      true    // Enable/disable buzzer
```

### Nextion Display Setup

1. Download [Nextion Editor](https://nextion.tech/nextion-editor/)
2. Create new project for 800x480 display
3. Follow the design spec in `nextion_hmi_design.h`
4. Compile and upload to Nextion via USB

Or use the provided HMI file (if available) directly.

## OBD-II PIDs Used

| Data | PID | Formula |
|------|-----|---------|
| RPM | 0x0C | ((A × 256) + B) / 4 |
| Speed | 0x0D | A (km/h) × 0.621 = MPH |
| Coolant Temp | 0x05 | A - 40 = °C → °F |

**Note:** Oil pressure is NOT available via OBD-II on the 2007-2008 Acura TL. You must use an external analog pressure sender.

## CAN Bus Specifications

- **Bus Speed:** 500 kbps
- **OBD-II Request ID:** 0x7DF
- **ECU Response IDs:** 0x7E8 - 0x7EF

## Alert Behavior

### Shift Light
- **6000+ RPM:** Tachometer turns orange (pre-warning)
- **6300+ RPM:** 
  - Red "SHIFT!" overlay flashes on screen
  - Buzzer beeps rapidly

### Water Temperature
- **205°F+:** Yellow "TEMP WARN" message
- **215°F+:** 
  - Flashing red "HOT!" overlay
  - Continuous buzzer alarm

### Oil Pressure
- **Below 45 PSI:** Yellow "OIL WARN" message
- **Below 25 PSI:**
  - Flashing red "OIL LOW!" overlay  
  - Continuous buzzer alarm

*Oil pressure alerts only trigger when RPM > 500 to avoid false alarms at startup.*

## File Structure

```
canbus_gauge/
├── canbus_gauge.ino      # Main sketch
├── config.h              # Configuration and thresholds
├── obd_pids.h            # OBD-II PID definitions
├── can_handler.h         # CAN bus header
├── can_handler.cpp       # CAN bus implementation
├── sensors.h             # Analog sensor header
├── sensors.cpp           # Analog sensor implementation
├── alerts.h              # Alert logic header
├── alerts.cpp            # Alert logic implementation
├── display_handler.h     # Nextion display header
├── display_handler.cpp   # Nextion display implementation
└── nextion_hmi_design.h  # Nextion HMI design specification
```

## Troubleshooting

### CAN Bus Not Connecting
1. Verify wiring to OBD-II pins 6 (CAN-H) and 14 (CAN-L)
2. Check MCP2515 crystal matches `CAN_CLOCK` in config (8MHz or 16MHz)
3. Ensure car ignition is ON
4. Try swapping CAN-H and CAN-L wires

### No OBD Data
1. Some vehicles need engine running
2. Check debug output in Serial Monitor (115200 baud)
3. Verify PID support with an OBD-II scanner app first

### Display Not Responding
1. Check TX/RX connections (may need to swap)
2. Verify baud rate matches (115200)
3. Ensure Nextion is powered with 5V (not 3.3V)

### Oil Pressure Reading Incorrect
1. Calibrate sensor values in `config.h`:
   - `OIL_SENSOR_V_MIN` - Voltage at 0 PSI
   - `OIL_SENSOR_V_MAX` - Voltage at max PSI
2. Verify voltage divider ratio

## Future Enhancements

- [ ] MQTT integration for logging/remote monitoring
- [ ] Lap timer functionality
- [ ] Data logging to SD card
- [ ] Additional sensor inputs (transmission temp, AFR)
- [ ] Configurable gauge layouts
- [ ] Touch screen calibration menu

## License

Part of the VTMS (Vehicle Telemetry Monitoring System) project.
