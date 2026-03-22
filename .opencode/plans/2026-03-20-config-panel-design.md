# Config Panel Design

**Goal:** Add a settings UI to the VTMS dashboard that lets the user configure GoPro URLs, MQTT connection, and gauge definitions at runtime, persisted server-side as a JSON file.

## Config Data Shape

Stored at `server/data/config.json`:

```json
{
  "mqtt": {
    "url": "ws://192.168.50.24:9001",
    "topicPrefix": "lemons/"
  },
  "gopro": {
    "apiUrl": "http://localhost:3001",
    "streamWsUrl": "ws://localhost:9002"
  },
  "gauges": [
    {
      "id": "rpm",
      "topic": "lemons/RPM",
      "label": "RPM",
      "min": 0,
      "max": 8000,
      "unit": "rpm",
      "zones": [
        { "from": 0, "to": 5000, "color": "#4ade80" },
        { "from": 5000, "to": 6500, "color": "#facc15" },
        { "from": 6500, "to": 8000, "color": "#ef4444" }
      ]
    }
  ]
}
```

- Each gauge has a stable `id` for React keys
- `zones` is optional
- `decimals` is optional (defaults to 0)
- Hardcoded defaults in `gauges.ts` become the fallback

## Server API

- `GET /api/config` -- read config from disk, return defaults if file missing
- `PUT /api/config` -- validate and write full config to disk
- `express.json()` middleware added for body parsing
- `server/data/` added to `.gitignore`

## Frontend Architecture

- `useConfig()` hook fetches config on mount, exposes `config`, `saveConfig()`, `loading`, `error`
- `App.tsx` passes config values as props (replacing static imports)
- `GaugePanel` receives gauge list as prop
- `useMqtt` and `useGoPro` receive URLs as parameters
- Hooks reconnect when URLs change

## Settings Panel UI

- Gear icon in `StatusBar` right side
- Opens a modal overlay with three sections:
  1. **Connection** -- MQTT URL, topic prefix, GoPro API URL, stream WS URL
  2. **Gauges** -- list editor: add/remove/edit label, topic, min, max, unit, zones
  3. **Actions** -- Save, Reset to Defaults
- Basic validation: required fields, min < max, URL format
- Save calls `PUT /api/config`, closes on success

## Approach

Flat JSON file on the Express server. No database. No localStorage cache.
