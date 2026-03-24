# ESP32 Flash Workflow Simplification

**Date:** 2026-03-24
**Branch:** esp32-firmware-hardening

## Problem

Flashing an ESP32 from scratch requires multiple manual steps across different tools:

1. Manually download MicroPython firmware from micropython.org
2. `esptool.py erase_flash`
3. `esptool.py write_flash`
4. `mpremote mip install umqtt.robust`
5. `make flash-<device>` (which runs 6-8 separate `mpremote cp` calls, each reconnecting)

Each `mpremote cp` call opens and closes the serial connection independently, adding unnecessary overhead.

## Design

### 1. Auto-download firmware

- `MICROPYTHON_VERSION` variable defaults to latest stable (e.g., `v1.25.0`)
- Firmware cached in `.cache/ESP32_GENERIC-$(MICROPYTHON_VERSION).bin`
- Downloaded via `curl` from `micropython.org/resources/firmware/`
- `.cache/` added to `.gitignore`

### 2. Staging directory for file deployment

- Each `flash-<device>` target assembles common + device-specific files into `.flash-stage/`
- Single `mpremote cp -r .flash-stage/ : + reset` replaces N individual `cp` calls
- `.flash-stage/` cleaned before and after each flash, added to `.gitignore`

### 3. Unified flash targets

- `flash-micropython` — auto-downloads firmware, erases, flashes, installs umqtt.robust
- `flash-<device>` — generates secrets, stages files, copies to device, resets
- `flash-fresh-<device>` — chains `flash-micropython` then `flash-<device>` (blank chip to running device)

### 4. Port handling

- `ESP_PORT ?= auto`
- `esptool` uses `--port $(ESP_PORT)` (esptool supports `auto` natively when available, but the variable allows explicit override)
- `mpremote` uses `connect $(ESP_PORT)` when not `auto`, otherwise omits it for auto-detect
- Override with `make flash-analog-sensors ESP_PORT=/dev/ttyUSB1`

## Files changed

- `Makefile` — rewrite ESP32 flash targets
- `.gitignore` — add `.cache/` and `.flash-stage/`
- `arduino/README.md` — update flash workflow documentation

## What stays the same

- `generate-secrets` target unchanged
- `esp32-test` target unchanged
- `monitor-esp32` target unchanged
- Device file lists unchanged (just assembled via staging directory)
- All existing device-specific configs and source files unchanged
