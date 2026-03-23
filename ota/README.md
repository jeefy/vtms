# OTA Server

The OTA server is a lightweight HTTP server that distributes MicroPython firmware to ESP32 devices. It scans firmware files from `arduino/` directories at startup, computes per-device SHA256 hashes, serves firmware over HTTP, and publishes hash announcements to MQTT so devices can detect when updates are available.

## How It Works

1. **Scan firmware.** On startup, the server walks subdirectories of `FIRMWARE_DIR`. Each subdirectory (except `common/`) is treated as a device type. Files in `common/` are shared across all device types.
2. **Build manifests.** For each device type, the server collects `.py` files from both `common/` and the device-specific directory (deduplicated, device overrides common), then computes a SHA256 hash over all file contents. The result is a manifest with the device type, hash, and file list.
3. **Serve HTTP.** Devices fetch their manifest and individual files over HTTP.
4. **Announce via MQTT.** A background thread publishes each device type's manifest hash to MQTT as a retained message. This repeats every `ANNOUNCE_INTERVAL` seconds so devices can detect new firmware without polling HTTP.

File resolution priority: if a filename exists in both the device directory and `common/`, the device-specific version wins.

## HTTP Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Returns `{"status": "ok"}` |
| `/manifest/<device_type>` | GET | Returns the manifest JSON for a device type (hash, file list) |
| `/files/<device_type>/<filename>` | GET | Returns the firmware file contents (`text/plain`) |

Manifest response example:

```json
{
  "device_type": "thermoprobe",
  "hash": "a1b2c3d4...",
  "files": ["boot.py", "config.py", "main.py", "max6675.py"]
}
```

## MQTT Topics

| Topic | Payload | Retained |
|---|---|---|
| `vtms/ota/<device_type>/notify` | `{"hash": "<sha256>"}` | Yes |

The server publishes to these topics on startup and every `ANNOUNCE_INTERVAL` seconds. Devices subscribe to their device type's topic and compare the hash against their local firmware hash to decide whether to pull an update.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `FIRMWARE_DIR` | `/firmware` | Root directory containing device firmware subdirectories |
| `MQTT_BROKER` | `192.168.50.24` | MQTT broker hostname or IP |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `HTTP_PORT` | `8266` | HTTP server port |
| `ANNOUNCE_INTERVAL` | `60` | Seconds between MQTT hash re-announcements |

## Testing

```sh
make ota-test
```

Or directly:

```sh
python -m pytest ota/tests/ -v
```

Tests cover the pure functions (file listing, file resolution priority, hash computation, manifest building) without requiring MQTT or a running server.

## Docker Build and Deployment

Build the image:

```sh
make image-ota
```

This uses `Dockerfile.ota`, which copies `ota/server.py` and all firmware files from `arduino/` into the image under `/firmware/`. Current device types bundled: `analog_sensors`, `thermoprobe`, `temp_sensor`, `led_controller`.

The server runs on `car-pi`. The container exposes port 8266.

## Device Interaction

ESP32 devices subscribe to their `vtms/ota/<device_type>/notify` MQTT topic. When the announced hash differs from their local hash, they fetch the manifest from `/manifest/<device_type>`, then download each file from `/files/<device_type>/<filename>`.

See [arduino/README.md](../arduino/README.md) for the device-side OTA implementation.
