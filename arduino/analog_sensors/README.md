# ESP32 Analog Sensors

MicroPython firmware for an ESP32 that reads fuel level and oil pressure by
passively tapping existing gauge wiring via HiLetgo 0-25V voltage divider
modules, and publishes calibrated readings to MQTT.

## Hardware

- **Board:** ELEGOO ESP-32 (ESP-WROOM-32, USB-C) -- Amazon B0D8T53CQ5
- **Voltage dividers:** HiLetgo 0-25V detection modules (5:1 ratio) -- Amazon B01HTC4XKY
- **Fuel sender:** Stock 2004 Honda Accord, tapped at gauge wire
- **Oil sender:** Aftermarket Greddy 1/8 NPT, tapped at gauge wire

### Wiring

```
Fuel gauge wire ──┬── stock gauge
                  │
            [HiLetgo module]
            VCC ── tap point
            GND ── ESP32 GND
            S ──── ESP32 GPIO34

Oil gauge wire ───┬── Greddy gauge
                  │
            [HiLetgo module]
            VCC ── tap point
            GND ── ESP32 GND
            S ──── ESP32 GPIO35
```

**Safety:** Measure actual voltage at each gauge wire with a multimeter before
connecting. Expected 0-5V range; module output 0-1V (safe for ESP32 3.3V ADC).

## Files

| File | Purpose |
|------|---------|
| `config.py` | WiFi, MQTT, ADC pins, calibration values |
| `sensors.py` | Pure-math conversion functions (ADC->voltage->value) |
| `mqtt_client.py` | MQTT wrapper using `umqtt.robust` |
| `boot.py` | Multi-network WiFi connection on startup |
| `main.py` | Main loop: read, smooth, convert, publish |
| `tests/test_sensors.py` | Host-side pytest tests for sensor math |

## Setup

### 1. Flash MicroPython (one-time)

```bash
pip install esptool mpremote
make flash-micropython
# Follow the printed instructions
```

### 2. Install MQTT library (one-time)

```bash
mpremote mip install umqtt.robust
```

### 3. Deploy firmware

```bash
make flash-analog-sensors
```

### 4. Monitor serial output

```bash
make monitor-analog
```

## Testing

Run sensor conversion tests on the host:

```bash
make esp32-test
```

## Calibration

1. Set `DEBUG = True` in `config.py` (default)
2. Deploy and subscribe to raw voltages:
   ```bash
   mosquitto_sub -h 192.168.50.24 -t "lemons/analog/#" -v
   ```
3. Record voltages at known states (full/empty tank, engine off/running)
4. Update calibration values in `config.py`
5. Re-deploy: `make flash-analog-sensors`
6. Set `DEBUG = False` once calibration is complete

## MQTT Topics

| Topic | Payload | Units |
|-------|---------|-------|
| `lemons/analog/fuel_level` | `0.0` - `100.0` | percent |
| `lemons/analog/oil_pressure` | `0.0` - `150.0` | PSI |
| `lemons/analog/raw/a0_voltage` | raw voltage | volts (debug) |
| `lemons/analog/raw/a1_voltage` | raw voltage | volts (debug) |
