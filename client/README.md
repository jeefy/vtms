# vtms-client

The VTMS client runs on a Raspberry Pi mounted in the race car. It reads OBD-II telemetry from the vehicle's ECU and GPS position from a serial receiver, then publishes everything to an MQTT broker under the `lemons/#` topic tree. It also subscribes to command/control topics so the pit crew can dynamically watch/unwatch OBD PIDs, toggle debug mode, and signal flag or pit status. On a Raspberry Pi, it optionally drives GPIO LEDs for in-car driver alerts.

## MQTT Topics

### Published (car -> broker)

| Topic | Source | Payload |
|---|---|---|
| `lemons/RPM` | OBD | Value with unit (e.g. `3200 revolutions_per_minute`) |
| `lemons/SPEED` | OBD | Vehicle speed |
| `lemons/COOLANT_TEMP` | OBD | Coolant temperature |
| `lemons/OIL_TEMP` | OBD | Oil temperature |
| `lemons/ENGINE_LOAD` | OBD | Calculated engine load |
| `lemons/FUEL_LEVEL` | OBD | Fuel tank level |
| `lemons/<PID>` | OBD | Any watched metric or monitor command |
| `lemons/DTC/<code>` | OBD | Diagnostic trouble code description |
| `lemons/gps/pos` | GPS | `latitude,longitude` |
| `lemons/gps/latitude` | GPS | Decimal latitude |
| `lemons/gps/longitude` | GPS | Decimal longitude |
| `lemons/gps/geohash` | GPS | Geohash (precision 12) |
| `lemons/gps/speed` | GPS | Speed in m/s (converted from knots) |
| `lemons/gps/altitude` | GPS | Altitude in meters |
| `lemons/gps/track` | GPS | True course in degrees |
| `lemons/health` | Client | JSON: `mqtt_connected`, `obd_connected`, `timestamp` |

See `src/vtms_client/myobd.py` for the full list of watched OBD PIDs.

### Subscribed (broker -> car)

| Topic | Effect |
|---|---|
| `lemons/obd2/watch` | Add an OBD PID watch (payload = command name) |
| `lemons/obd2/unwatch` | Remove an OBD PID watch |
| `lemons/obd2/query` | One-shot query of an OBD command |
| `lemons/debug` | `true`/`false` to toggle debug logging |
| `lemons/flag/red` | Red flag indicator (drives LED on Pi) |
| `lemons/flag/black` | Black flag indicator (drives LED on Pi) |
| `lemons/pit` | Pit-soon signal (drives LED on Pi) |
| `lemons/box` | Box-box signal (drives LED on Pi) |
| `lemons/message` | General pit message (logged) |

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- An OBD-II USB adapter (ELM327 compatible)
- A serial GPS receiver (shows up as `/dev/ttyACM*`)
- MQTT broker reachable at the configured address

## Install / Run / Test / Lint

All commands are run from the repository root via Make:

```sh
make client-install   # uv sync in client/
make client-run       # uv run vtms-client
make client-test      # uv run pytest tests/ -v
make client-test-cov  # pytest with coverage report
make client-lint      # ruff check src/ tests/
make client-format    # ruff format src/ tests/
```

Or directly from `client/`:

```sh
cd client
uv sync
uv run vtms-client
uv run pytest tests/ -v
```

## Configuration

Runtime defaults are in `src/vtms_client/config.py`:

| Setting | Default | Description |
|---|---|---|
| `mqtt_server` | `192.168.50.24` | MQTT broker address |
| `mqtt_port` | `1883` | MQTT broker port |
| `mqtt_keepalive` | `60` | MQTT keepalive interval (seconds) |
| `obd_retry_delay` | `15` | Seconds between OBD connection retries |
| `gps_enabled` | `True` | Enable GPS monitoring |
| `gps_baudrate` | `9600` | GPS serial baud rate |
| `gps_update_interval` | `1` | GPS update interval (seconds) |
| `debug` | `False` | Verbose logging |

### Environment Variables

| Variable | Used by |
|---|---|
| `POSTGRES_USER` | Database credentials (server-side use) |
| `POSTGRES_PASSWORD` | Database credentials (server-side use) |

## Docker

Build the container image (cross-compiled for ARM64 to run on the Pi):

```sh
make image-client
```

This builds from `client/Dockerfile` using `python:3.13-slim` with `uv`. The entrypoint is `uv run vtms-client`.

Push to the local registry:

```sh
make image-client-push
```

Images are pushed to the registry at `192.168.50.46:5000/vtms:latest` via skopeo.

## Hardware Notes

**Raspberry Pi:** The client auto-detects whether it's running on a Pi by reading `/sys/firmware/devicetree/base/model`. When detected, it imports `RPi.GPIO` and initializes LED outputs.

**GPIO LED Pinout (BOARD numbering):**

| Pin | Function |
|---|---|
| 8 | Box (pit box signal) |
| 10 | Pit (pit soon signal) |
| 12 | Red flag |
| 16 | Black flag |

LEDs are driven HIGH when the corresponding MQTT topic receives `true`, LOW on any other value.

**OBD-II:** The client scans all serial ports for an ELM327-compatible adapter, connects with `obd.Async`, and sets up watches for supported PIDs. If the connection drops, it automatically reconnects and re-registers watches.

**GPS:** The client looks for serial devices matching `ttyACM*` patterns. It reads NMEA sentences, parses them with pynmea2, and publishes position data. If pynmea2 or pyserial are not installed, GPS is gracefully disabled.

## Architecture

```
__main__.py  (VTMSClient orchestrator)
  |
  +-- mqtt_transport.py   MQTT lifecycle, publish buffering, reconnect
  +-- obd_service.py      OBD port scan, async connection, watch management
  +-- gps_service.py      GPS serial discovery, NMEA parsing, position publishing
  +-- myobd.py            OBD command lists, publish formatting
  +-- mqtt_handlers.py    Message router, debug/flag/pit handlers
  +-- config.py           Dataclass config with defaults
  +-- led.py              RPi.GPIO LED control (Pi-only)
```

The client runs four async tasks concurrently: GPS monitoring, OBD-II monitoring, MQTT connection monitoring, and periodic health publishing. Messages are buffered (up to 1000, with a 5-minute expiry) when the MQTT connection is down and flushed on reconnect.
