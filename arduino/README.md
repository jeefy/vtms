# Arduino / ESP32 Firmware

ESP32 firmware for the VTMS sensor peripherals. Four MicroPython devices read sensors and publish data to MQTT on the car-pi. One Arduino/C++ device drives a CAN bus gauge cluster. All MicroPython devices share a common boot sequence that joins the car-pi WiFi hotspot and checks for OTA firmware updates before entering their main loop.

## Devices

| Device | What it does | Hardware | MQTT topics |
|--------|-------------|----------|-------------|
| `analog_sensors` | Fuel level + oil pressure via voltage dividers | ELEGOO ESP32, HiLetgo 0-25V modules | `lemons/analog/fuel_level`, `lemons/analog/oil_pressure` |
| `thermoprobe` | Oil temperature via thermocouple | ESP32, MAX6675 breakout | `lemons/temp/oil_F` |
| `temp_sensor` | Transmission temperature via analog sender | ESP32, analog temp sensor on GPIO36 | `lemons/temp/transmission` |
| `led_controller` | Race flag / pit / box indicator LEDs | ESP32, GPIO-driven LEDs | Subscribes to `lemons/#` |
| `canbus_gauge` | Digital gauge cluster (RPM, speed, water temp, oil pressure) | ESP32, MCP2515, Nextion 7" display | N/A (reads OBD-II CAN bus directly) |

The first four are MicroPython. `canbus_gauge` is Arduino/C++ and has its own build process via Arduino IDE.

## Shared Modules (`common/`)

All MicroPython devices share these modules, copied to each device at flash time:

| Module | Purpose |
|--------|---------|
| `boot.py` | Runs at power-on. Tries each WiFi SSID in the device's `config.py` until one connects, then checks for OTA updates if on the car-pi hotspot. |
| `mqtt_client.py` | Thin wrapper around `umqtt.robust`. Generates a unique client ID from the MAC address. Provides `connect()`, `publish()`, and `subscribe()`. |
| `ota_update.py` | Fetches a manifest from the OTA server, compares hashes, downloads updated files, and handles backup/rollback if the new firmware crash-loops. |

## Flash Workflow

### Prerequisites

```bash
pip install esptool mpremote
```

### From scratch (blank chip → running device)

One command does everything — downloads MicroPython firmware, erases flash, writes firmware, installs `umqtt.robust`, generates secrets, copies device files, and resets:

```bash
make flash-fresh-analog-sensors
make flash-fresh-thermoprobe
make flash-fresh-temp-sensor
make flash-fresh-led-controller
```

To target a specific serial port (default is auto-detect):

```bash
make flash-fresh-analog-sensors ESP_PORT=/dev/ttyUSB1
```

### Flash device code only (MicroPython already installed)

If the board already has MicroPython and `umqtt.robust`, just flash the application code:

```bash
make flash-analog-sensors
make flash-thermoprobe
make flash-temp-sensor
make flash-led-controller
```

### Flash MicroPython firmware only

Downloads the firmware (cached in `.cache/`), erases flash, writes firmware, and installs `umqtt.robust`:

```bash
make flash-micropython
```

Override the MicroPython version:

```bash
make flash-micropython MICROPYTHON_VERSION=v1.24.1
```

`canbus_gauge` is flashed separately through Arduino IDE. See [canbus_gauge/README.md](canbus_gauge/README.md) for setup.

## OTA Updates

MicroPython devices check for updates automatically at boot:

1. `boot.py` connects to WiFi and detects the car-pi hotspot (gateway `10.42.0.1`).
2. If on the hotspot, `ota_update.py` fetches a manifest from the `ota` container at `10.42.0.1:8266`.
3. If the server hash differs from the local hash, it backs up current files, downloads the update, and reboots.
4. If the device crash-loops (3+ boots without reaching `reset_boot_count()`), it rolls back to the backup and skips that hash.

Updates are served by the `ota` container running on car-pi. Push new firmware there, and devices pick it up on next power cycle.

## Testing

Host-side pytest for all MicroPython devices (sensor math, OTA logic, LED parsing):

```bash
make esp32-test
```

This runs tests in `common/tests/`, `analog_sensors/tests/`, `thermoprobe/tests/`, `temp_sensor/tests/`, and `led_controller/tests/`.

## Monitoring

Open a serial REPL to any connected ESP32:

```bash
make monitor-esp32
```

This runs `mpremote connect auto repl`. Output includes WiFi status, OTA check results, and sensor readings.

## Device READMEs

- [analog_sensors/README.md](analog_sensors/README.md) -- wiring, calibration, MQTT topics
- [canbus_gauge/README.md](canbus_gauge/README.md) -- Arduino IDE setup, CAN bus wiring, Nextion display, OBD-II PIDs
