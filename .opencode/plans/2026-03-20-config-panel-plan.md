# Config Panel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a runtime-configurable settings panel to the VTMS dashboard for GoPro URLs, MQTT connection, and gauge definitions, persisted as a server-side JSON file.

**Architecture:** New `GET/PUT /api/config` endpoints on the Express server read/write a flat JSON file. A `useConfig()` hook on the frontend fetches config on mount and replaces static imports. A gear-icon-triggered modal provides the editing UI.

**Tech Stack:** Express (existing), Node `fs/promises`, React hooks, CSS modal overlay.

---

### Task 1: Config Type Definitions (shared shape)

**Files:**
- Create: `web/src/types/config.ts`

**Step 1: Create the config type file**

```ts
import type { GaugeZone } from "./telemetry";

export interface GaugeConfigEntry {
  id: string;
  topic: string;
  label: string;
  min: number;
  max: number;
  unit: string;
  zones?: GaugeZone[];
  decimals?: number;
}

export interface MqttConfig {
  url: string;
  topicPrefix: string;
}

export interface GoProConfig {
  apiUrl: string;
  streamWsUrl: string;
}

export interface AppConfig {
  mqtt: MqttConfig;
  gopro: GoProConfig;
  gauges: GaugeConfigEntry[];
}
```

**Step 2: Commit**

```
git add web/src/types/config.ts
git commit -m "feat: add AppConfig type definitions"
```

---

### Task 2: Default Config Constants

**Files:**
- Modify: `web/src/config/gauges.ts` (all lines)

Rename `gaugeConfig` to `defaultGaugeConfig`, rename `mqttConfig` to `defaultMqttConfig`, add `defaultGoProConfig` and `defaultAppConfig`. Add `id` field to each gauge entry. Keep all existing values.

**Step 1: Rewrite gauges.ts**

```ts
import type { AppConfig, GaugeConfigEntry, MqttConfig, GoProConfig } from "../types/config";

export const defaultGaugeConfig: GaugeConfigEntry[] = [
  {
    id: "rpm",
    topic: "lemons/RPM",
    label: "RPM",
    min: 0,
    max: 8000,
    unit: "rpm",
    zones: [
      { from: 0, to: 5000, color: "#4ade80" },
      { from: 5000, to: 6500, color: "#facc15" },
      { from: 6500, to: 8000, color: "#ef4444" },
    ],
  },
  {
    id: "speed",
    topic: "lemons/SPEED",
    label: "Speed",
    min: 0,
    max: 200,
    unit: "km/h",
    zones: [{ from: 0, to: 200, color: "#4ade80" }],
  },
  {
    id: "coolant",
    topic: "lemons/COOLANT_TEMP",
    label: "Coolant",
    min: 0,
    max: 130,
    unit: "\u00b0C",
    zones: [
      { from: 0, to: 50, color: "#60a5fa" },
      { from: 50, to: 100, color: "#4ade80" },
      { from: 100, to: 115, color: "#facc15" },
      { from: 115, to: 130, color: "#ef4444" },
    ],
  },
  {
    id: "oil_temp",
    topic: "lemons/OIL_TEMP",
    label: "Oil Temp",
    min: 0,
    max: 150,
    unit: "\u00b0C",
    zones: [
      { from: 0, to: 60, color: "#60a5fa" },
      { from: 60, to: 120, color: "#4ade80" },
      { from: 120, to: 135, color: "#facc15" },
      { from: 135, to: 150, color: "#ef4444" },
    ],
  },
  {
    id: "throttle",
    topic: "lemons/THROTTLE_POS",
    label: "Throttle",
    min: 0,
    max: 100,
    unit: "%",
    zones: [{ from: 0, to: 100, color: "#4ade80" }],
  },
  {
    id: "load",
    topic: "lemons/ENGINE_LOAD",
    label: "Load",
    min: 0,
    max: 100,
    unit: "%",
    zones: [
      { from: 0, to: 70, color: "#4ade80" },
      { from: 70, to: 90, color: "#facc15" },
      { from: 90, to: 100, color: "#ef4444" },
    ],
  },
];

export const defaultMqttConfig: MqttConfig = {
  url: import.meta.env.VITE_MQTT_URL ?? "ws://192.168.50.24:9001",
  topicPrefix: "lemons/",
};

export const defaultGoProConfig: GoProConfig = {
  apiUrl: import.meta.env.VITE_GOPRO_API_URL ?? "http://localhost:3001",
  streamWsUrl: import.meta.env.VITE_GOPRO_STREAM_URL ?? "ws://localhost:9002",
};

export const defaultAppConfig: AppConfig = {
  mqtt: defaultMqttConfig,
  gopro: defaultGoProConfig,
  gauges: defaultGaugeConfig,
};
```

**Step 2: Fix imports in files that reference old names**

Files to update:
- `web/src/components/GaugePanel.tsx:2` -- change `gaugeConfig` to `defaultGaugeConfig` (temporary; will be replaced by prop in Task 7)
- `web/src/hooks/useMqtt.ts:4` -- change `mqttConfig` to `defaultMqttConfig` (temporary; will be replaced by param in Task 8)

In `GaugePanel.tsx` line 2:
```ts
import { defaultGaugeConfig } from "../config/gauges";
```
And line 18:
```ts
{defaultGaugeConfig.map((cfg) => {
```

In `useMqtt.ts` line 4:
```ts
import { defaultMqttConfig } from "../config/gauges";
```
And lines 30-31:
```ts
const client = mqtt.connect(defaultMqttConfig.url, {
  reconnectPeriod: defaultMqttConfig.reconnectInterval,
```
Wait -- `defaultMqttConfig` no longer has `reconnectInterval`. Add it:

In `gauges.ts`, update `defaultMqttConfig` to include `reconnectInterval: 5000` in the object. But the `MqttConfig` type doesn't have that field. Since reconnect interval is internal to the MQTT hook and not user-configurable, keep it as a constant in `useMqtt.ts` instead.

In `useMqtt.ts`:
```ts
import { defaultMqttConfig } from "../config/gauges";

const RECONNECT_INTERVAL = 5000;
```
And line 31: `reconnectPeriod: RECONNECT_INTERVAL,`
And line 39: `client.subscribe(\`${defaultMqttConfig.topicPrefix}#\`, { qos: 0 });`

**Step 3: Verify build**

Run: `cd web && npm run build`
Expected: Build succeeds

**Step 4: Run e2e tests**

Run: `cd web && npx playwright test`
Expected: 10 tests pass

**Step 5: Commit**

```
git add web/src/config/gauges.ts web/src/components/GaugePanel.tsx web/src/hooks/useMqtt.ts
git commit -m "refactor: rename gauge/mqtt config to defaults, add ids"
```

---

### Task 3: Server Config API

**Files:**
- Create: `server/src/config-store.ts`
- Modify: `server/src/index.ts:6-30`

**Step 1: Create config-store.ts**

This module reads/writes `server/data/config.json`. It validates basic structure on write and returns defaults if the file doesn't exist.

```ts
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const CONFIG_DIR = join(__dirname, "..", "data");
const CONFIG_PATH = join(CONFIG_DIR, "config.json");

export interface GaugeZone {
  from: number;
  to: number;
  color: string;
}

export interface GaugeConfigEntry {
  id: string;
  topic: string;
  label: string;
  min: number;
  max: number;
  unit: string;
  zones?: GaugeZone[];
  decimals?: number;
}

export interface AppConfig {
  mqtt: { url: string; topicPrefix: string };
  gopro: { apiUrl: string; streamWsUrl: string };
  gauges: GaugeConfigEntry[];
}

const DEFAULT_CONFIG: AppConfig = {
  mqtt: {
    url: "ws://192.168.50.24:9001",
    topicPrefix: "lemons/",
  },
  gopro: {
    apiUrl: "http://localhost:3001",
    streamWsUrl: "ws://localhost:9002",
  },
  gauges: [
    {
      id: "rpm", topic: "lemons/RPM", label: "RPM",
      min: 0, max: 8000, unit: "rpm",
      zones: [
        { from: 0, to: 5000, color: "#4ade80" },
        { from: 5000, to: 6500, color: "#facc15" },
        { from: 6500, to: 8000, color: "#ef4444" },
      ],
    },
    {
      id: "speed", topic: "lemons/SPEED", label: "Speed",
      min: 0, max: 200, unit: "km/h",
      zones: [{ from: 0, to: 200, color: "#4ade80" }],
    },
    {
      id: "coolant", topic: "lemons/COOLANT_TEMP", label: "Coolant",
      min: 0, max: 130, unit: "\u00b0C",
      zones: [
        { from: 0, to: 50, color: "#60a5fa" },
        { from: 50, to: 100, color: "#4ade80" },
        { from: 100, to: 115, color: "#facc15" },
        { from: 115, to: 130, color: "#ef4444" },
      ],
    },
    {
      id: "oil_temp", topic: "lemons/OIL_TEMP", label: "Oil Temp",
      min: 0, max: 150, unit: "\u00b0C",
      zones: [
        { from: 0, to: 60, color: "#60a5fa" },
        { from: 60, to: 120, color: "#4ade80" },
        { from: 120, to: 135, color: "#facc15" },
        { from: 135, to: 150, color: "#ef4444" },
      ],
    },
    {
      id: "throttle", topic: "lemons/THROTTLE_POS", label: "Throttle",
      min: 0, max: 100, unit: "%",
      zones: [{ from: 0, to: 100, color: "#4ade80" }],
    },
    {
      id: "load", topic: "lemons/ENGINE_LOAD", label: "Load",
      min: 0, max: 100, unit: "%",
      zones: [
        { from: 0, to: 70, color: "#4ade80" },
        { from: 70, to: 90, color: "#facc15" },
        { from: 90, to: 100, color: "#ef4444" },
      ],
    },
  ],
};

export async function loadConfig(): Promise<AppConfig> {
  try {
    const raw = await readFile(CONFIG_PATH, "utf-8");
    return JSON.parse(raw) as AppConfig;
  } catch {
    return DEFAULT_CONFIG;
  }
}

export async function saveConfig(config: AppConfig): Promise<void> {
  validateConfig(config);
  await mkdir(CONFIG_DIR, { recursive: true });
  await writeFile(CONFIG_PATH, JSON.stringify(config, null, 2), "utf-8");
}

export function getDefaultConfig(): AppConfig {
  return DEFAULT_CONFIG;
}

function validateConfig(config: unknown): asserts config is AppConfig {
  if (typeof config !== "object" || config === null) {
    throw new Error("Config must be an object");
  }
  const c = config as Record<string, unknown>;
  if (!c.mqtt || typeof c.mqtt !== "object") throw new Error("Missing mqtt config");
  if (!c.gopro || typeof c.gopro !== "object") throw new Error("Missing gopro config");
  if (!Array.isArray(c.gauges)) throw new Error("gauges must be an array");

  const mqtt = c.mqtt as Record<string, unknown>;
  if (typeof mqtt.url !== "string") throw new Error("mqtt.url must be a string");
  if (typeof mqtt.topicPrefix !== "string") throw new Error("mqtt.topicPrefix must be a string");

  const gopro = c.gopro as Record<string, unknown>;
  if (typeof gopro.apiUrl !== "string") throw new Error("gopro.apiUrl must be a string");
  if (typeof gopro.streamWsUrl !== "string") throw new Error("gopro.streamWsUrl must be a string");

  for (const g of c.gauges as unknown[]) {
    if (typeof g !== "object" || g === null) throw new Error("Each gauge must be an object");
    const gauge = g as Record<string, unknown>;
    if (typeof gauge.id !== "string") throw new Error("gauge.id must be a string");
    if (typeof gauge.topic !== "string") throw new Error("gauge.topic must be a string");
    if (typeof gauge.label !== "string") throw new Error("gauge.label must be a string");
    if (typeof gauge.min !== "number") throw new Error("gauge.min must be a number");
    if (typeof gauge.max !== "number") throw new Error("gauge.max must be a number");
    if (gauge.min >= gauge.max) throw new Error(`gauge "${gauge.id}": min must be less than max`);
    if (typeof gauge.unit !== "string") throw new Error("gauge.unit must be a string");
  }
}
```

**Step 2: Add routes to server/src/index.ts**

Add `express.json()` middleware after CORS. Add two routes:

```ts
import { loadConfig, saveConfig, getDefaultConfig } from "./config-store.js";

// Add after CORS middleware:
app.use(express.json());

// Add after existing routes:
app.get("/api/config", async (_req, res) => {
  try {
    const config = await loadConfig();
    res.json(config);
  } catch (err) {
    res.status(500).json({ error: "Failed to load config", detail: String(err) });
  }
});

app.put("/api/config", async (req, res) => {
  try {
    await saveConfig(req.body);
    const config = await loadConfig();
    res.json(config);
  } catch (err) {
    res.status(400).json({ error: "Invalid config", detail: String(err) });
  }
});

app.get("/api/config/defaults", (_req, res) => {
  res.json(getDefaultConfig());
});
```

**Step 3: Add `server/data/` to .gitignore**

Append `server/data/` to the root `.gitignore`.

**Step 4: Verify server types**

Run: `cd server && npx tsc --noEmit`
Expected: No errors

**Step 5: Commit**

```
git add server/src/config-store.ts server/src/index.ts .gitignore
git commit -m "feat: add GET/PUT /api/config endpoints with JSON file storage"
```

---

### Task 4: useConfig Hook

**Files:**
- Create: `web/src/hooks/useConfig.ts`

**Step 1: Create the hook**

```ts
import { useState, useEffect, useCallback } from "react";
import type { AppConfig } from "../types/config";
import { defaultAppConfig } from "../config/gauges";

const CONFIG_API = import.meta.env.VITE_GOPRO_API_URL ?? "http://localhost:3001";

export function useConfig() {
  const [config, setConfig] = useState<AppConfig>(defaultAppConfig);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${CONFIG_API}/api/config`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: AppConfig = await res.json();
        if (!cancelled) {
          setConfig(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          // Keep defaults on failure -- dashboard still works
          setError(String(err));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const saveConfig = useCallback(async (newConfig: AppConfig) => {
    try {
      const res = await fetch(`${CONFIG_API}/api/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newConfig),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const saved: AppConfig = await res.json();
      setConfig(saved);
      setError(null);
      return { ok: true as const };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      return { ok: false as const, error: msg };
    }
  }, []);

  const resetToDefaults = useCallback(async () => {
    try {
      const res = await fetch(`${CONFIG_API}/api/config/defaults`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const defaults: AppConfig = await res.json();
      return saveConfig(defaults);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      return { ok: false as const, error: msg };
    }
  }, [saveConfig]);

  return { config, loading, error, saveConfig, resetToDefaults };
}
```

**Step 2: Verify build**

Run: `cd web && npm run build`
Expected: Build succeeds

**Step 3: Commit**

```
git add web/src/hooks/useConfig.ts
git commit -m "feat: add useConfig hook for runtime config loading/saving"
```

---

### Task 5: Settings Panel Component

**Files:**
- Create: `web/src/components/SettingsPanel.tsx`

**Step 1: Create the settings panel**

This is a modal overlay with three sections. The component receives the current config and callbacks for save/reset/close. It maintains local draft state for editing.

```tsx
import { useState } from "react";
import type { AppConfig, GaugeConfigEntry } from "../types/config";

interface SettingsPanelProps {
  config: AppConfig;
  onSave: (config: AppConfig) => Promise<{ ok: boolean; error?: string }>;
  onReset: () => Promise<{ ok: boolean; error?: string }>;
  onClose: () => void;
}

export function SettingsPanel({ config, onSave, onReset, onClose }: SettingsPanelProps) {
  const [draft, setDraft] = useState<AppConfig>(structuredClone(config));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"connection" | "gauges">("connection");

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    const result = await onSave(draft);
    setSaving(false);
    if (result.ok) {
      onClose();
    } else {
      setError(result.error ?? "Save failed");
    }
  };

  const handleReset = async () => {
    setSaving(true);
    setError(null);
    const result = await onReset();
    setSaving(false);
    if (result.ok) {
      onClose();
    } else {
      setError(result.error ?? "Reset failed");
    }
  };

  const updateMqtt = (field: string, value: string) => {
    setDraft((d) => ({ ...d, mqtt: { ...d.mqtt, [field]: value } }));
  };

  const updateGoPro = (field: string, value: string) => {
    setDraft((d) => ({ ...d, gopro: { ...d.gopro, [field]: value } }));
  };

  const updateGauge = (index: number, field: string, value: string | number) => {
    setDraft((d) => {
      const gauges = [...d.gauges];
      gauges[index] = { ...gauges[index], [field]: value };
      return { ...d, gauges };
    });
  };

  const addGauge = () => {
    const id = `gauge_${Date.now()}`;
    const newGauge: GaugeConfigEntry = {
      id,
      topic: "",
      label: "New Gauge",
      min: 0,
      max: 100,
      unit: "",
    };
    setDraft((d) => ({ ...d, gauges: [...d.gauges, newGauge] }));
  };

  const removeGauge = (index: number) => {
    setDraft((d) => ({
      ...d,
      gauges: d.gauges.filter((_, i) => i !== index),
    }));
  };

  const moveGauge = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= draft.gauges.length) return;
    setDraft((d) => {
      const gauges = [...d.gauges];
      [gauges[index], gauges[target]] = [gauges[target], gauges[index]];
      return { ...d, gauges };
    });
  };

  return (
    <div className="settings-backdrop" onClick={onClose}>
      <div className="settings-panel" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <h2>Settings</h2>
          <button className="settings-close-btn" onClick={onClose} aria-label="Close settings">
            &times;
          </button>
        </div>

        <div className="settings-tabs">
          <button
            className={`settings-tab ${activeTab === "connection" ? "active" : ""}`}
            onClick={() => setActiveTab("connection")}
          >
            Connection
          </button>
          <button
            className={`settings-tab ${activeTab === "gauges" ? "active" : ""}`}
            onClick={() => setActiveTab("gauges")}
          >
            Gauges
          </button>
        </div>

        <div className="settings-body">
          {activeTab === "connection" && (
            <div className="settings-section">
              <h3>MQTT</h3>
              <label className="settings-field">
                <span>Broker URL</span>
                <input
                  type="text"
                  value={draft.mqtt.url}
                  onChange={(e) => updateMqtt("url", e.target.value)}
                  placeholder="ws://host:port"
                />
              </label>
              <label className="settings-field">
                <span>Topic Prefix</span>
                <input
                  type="text"
                  value={draft.mqtt.topicPrefix}
                  onChange={(e) => updateMqtt("topicPrefix", e.target.value)}
                  placeholder="lemons/"
                />
              </label>

              <h3>GoPro</h3>
              <label className="settings-field">
                <span>API URL</span>
                <input
                  type="text"
                  value={draft.gopro.apiUrl}
                  onChange={(e) => updateGoPro("apiUrl", e.target.value)}
                  placeholder="http://host:port"
                />
              </label>
              <label className="settings-field">
                <span>Stream WS URL</span>
                <input
                  type="text"
                  value={draft.gopro.streamWsUrl}
                  onChange={(e) => updateGoPro("streamWsUrl", e.target.value)}
                  placeholder="ws://host:port"
                />
              </label>
            </div>
          )}

          {activeTab === "gauges" && (
            <div className="settings-section">
              {draft.gauges.map((gauge, i) => (
                <div key={gauge.id} className="settings-gauge-card">
                  <div className="settings-gauge-header">
                    <strong>{gauge.label || "Untitled"}</strong>
                    <div className="settings-gauge-actions">
                      <button
                        onClick={() => moveGauge(i, -1)}
                        disabled={i === 0}
                        aria-label="Move up"
                        title="Move up"
                      >
                        &uarr;
                      </button>
                      <button
                        onClick={() => moveGauge(i, 1)}
                        disabled={i === draft.gauges.length - 1}
                        aria-label="Move down"
                        title="Move down"
                      >
                        &darr;
                      </button>
                      <button
                        onClick={() => removeGauge(i)}
                        className="settings-remove-btn"
                        aria-label="Remove gauge"
                        title="Remove"
                      >
                        &times;
                      </button>
                    </div>
                  </div>
                  <div className="settings-gauge-fields">
                    <label className="settings-field">
                      <span>Label</span>
                      <input
                        type="text"
                        value={gauge.label}
                        onChange={(e) => updateGauge(i, "label", e.target.value)}
                      />
                    </label>
                    <label className="settings-field">
                      <span>MQTT Topic</span>
                      <input
                        type="text"
                        value={gauge.topic}
                        onChange={(e) => updateGauge(i, "topic", e.target.value)}
                        placeholder="lemons/RPM"
                      />
                    </label>
                    <div className="settings-field-row">
                      <label className="settings-field">
                        <span>Min</span>
                        <input
                          type="number"
                          value={gauge.min}
                          onChange={(e) => updateGauge(i, "min", Number(e.target.value))}
                        />
                      </label>
                      <label className="settings-field">
                        <span>Max</span>
                        <input
                          type="number"
                          value={gauge.max}
                          onChange={(e) => updateGauge(i, "max", Number(e.target.value))}
                        />
                      </label>
                      <label className="settings-field">
                        <span>Unit</span>
                        <input
                          type="text"
                          value={gauge.unit}
                          onChange={(e) => updateGauge(i, "unit", e.target.value)}
                          placeholder="rpm"
                        />
                      </label>
                    </div>
                  </div>
                </div>
              ))}
              <button className="settings-add-btn" onClick={addGauge}>
                + Add Gauge
              </button>
            </div>
          )}
        </div>

        {error && <div className="settings-error">{error}</div>}

        <div className="settings-footer">
          <button className="settings-btn settings-btn-secondary" onClick={handleReset} disabled={saving}>
            Reset to Defaults
          </button>
          <div className="settings-footer-right">
            <button className="settings-btn settings-btn-secondary" onClick={onClose} disabled={saving}>
              Cancel
            </button>
            <button className="settings-btn settings-btn-primary" onClick={handleSave} disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Verify build**

Run: `cd web && npm run build`
Expected: Build succeeds (component is not mounted yet, but should compile)

**Step 3: Commit**

```
git add web/src/components/SettingsPanel.tsx
git commit -m "feat: add SettingsPanel component with connection and gauge editors"
```

---

### Task 6: Settings Panel CSS

**Files:**
- Modify: `web/src/App.css` (append after line 336)

**Step 1: Add settings panel styles**

Append the following CSS to the end of `App.css`:

```css
/* ── Settings Panel ──────────────────────────────────────── */
.settings-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.settings-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  width: min(600px, 90vw);
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.settings-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

.settings-header h2 {
  font-size: 16px;
  font-weight: 700;
}

.settings-close-btn {
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 22px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}

.settings-close-btn:hover {
  color: var(--text);
}

.settings-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
}

.settings-tab {
  flex: 1;
  padding: 8px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-dim);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}

.settings-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.settings-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.settings-section h3 {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 12px 0 8px;
}

.settings-section h3:first-child {
  margin-top: 0;
}

.settings-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}

.settings-field span {
  font-size: 12px;
  color: var(--text-dim);
}

.settings-field input {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
  font-family: monospace;
  outline: none;
}

.settings-field input:focus {
  border-color: var(--accent);
}

.settings-field-row {
  display: flex;
  gap: 8px;
}

.settings-field-row .settings-field {
  flex: 1;
}

.settings-gauge-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px;
  margin-bottom: 10px;
  background: rgba(0, 0, 0, 0.15);
}

.settings-gauge-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
}

.settings-gauge-actions {
  display: flex;
  gap: 4px;
}

.settings-gauge-actions button {
  background: none;
  border: 1px solid var(--border);
  border-radius: 3px;
  color: var(--text-dim);
  font-size: 13px;
  cursor: pointer;
  padding: 2px 6px;
  font-family: inherit;
}

.settings-gauge-actions button:hover:not(:disabled) {
  color: var(--text);
  border-color: var(--text-dim);
}

.settings-gauge-actions button:disabled {
  opacity: 0.3;
  cursor: default;
}

.settings-remove-btn {
  color: var(--red) !important;
}

.settings-gauge-fields {
  display: flex;
  flex-direction: column;
}

.settings-add-btn {
  width: 100%;
  padding: 8px;
  border: 1px dashed var(--border);
  border-radius: 6px;
  background: none;
  color: var(--text-dim);
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
}

.settings-add-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.settings-error {
  padding: 8px 16px;
  color: var(--red);
  font-size: 13px;
  background: rgba(239, 68, 68, 0.1);
  border-top: 1px solid rgba(239, 68, 68, 0.3);
}

.settings-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  gap: 8px;
}

.settings-footer-right {
  display: flex;
  gap: 8px;
}

.settings-btn {
  padding: 6px 16px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid var(--border);
  font-family: inherit;
}

.settings-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.settings-btn-primary {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}

.settings-btn-secondary {
  background: transparent;
  color: var(--text-dim);
}

.settings-btn-secondary:hover:not(:disabled) {
  color: var(--text);
}

.settings-gear-btn {
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 16px;
  cursor: pointer;
  padding: 2px;
  line-height: 1;
}

.settings-gear-btn:hover {
  color: var(--text);
}
```

**Step 2: Commit**

```
git add web/src/App.css
git commit -m "feat: add settings panel CSS styles"
```

---

### Task 7: Wire GaugePanel to Accept Config as Prop

**Files:**
- Modify: `web/src/components/GaugePanel.tsx` (all lines)

**Step 1: Change GaugePanel to accept gauges as prop**

Remove the static import and accept gauge config as a prop:

```tsx
import { RadialGauge } from "./RadialGauge";
import type { TelemetryValue } from "../types/telemetry";
import type { GaugeConfigEntry } from "../types/config";

interface GaugePanelProps {
  metrics: Map<string, TelemetryValue>;
  gauges: GaugeConfigEntry[];
  topicPrefix: string;
}

export function GaugePanel({ metrics, gauges, topicPrefix }: GaugePanelProps) {
  return (
    <div className="gauge-panel">
      {gauges.map((cfg) => {
        const key = cfg.topic.replace(topicPrefix, "");
        const telemetry = metrics.get(key);
        const value = telemetry?.value ?? NaN;

        return (
          <div key={cfg.id} className="gauge-cell">
            <RadialGauge config={cfg} value={value} />
          </div>
        );
      })}
    </div>
  );
}
```

Note: `RadialGauge` currently takes `config: GaugeConfig`. The `GaugeConfigEntry` type has the same shape plus an `id` field, so it's compatible. If `RadialGauge` uses a strict type check, update its prop type to accept `GaugeConfigEntry` or make it accept the intersection.

**Step 2: Verify build** (will fail until App.tsx is updated in Task 9)

Skip build verification here -- will verify after Task 9.

**Step 3: Commit**

```
git add web/src/components/GaugePanel.tsx
git commit -m "refactor: GaugePanel accepts gauge config and topic prefix as props"
```

---

### Task 8: Wire useMqtt and useGoPro to Accept Config Params

**Files:**
- Modify: `web/src/hooks/useMqtt.ts` (lines 4, 14, 24-39)
- Modify: `web/src/hooks/useTelemetry.ts` (lines 7, 41, 127)
- Modify: `web/src/hooks/useGoPro.ts` (lines 1-5, 8)

**Step 1: Update useMqtt to accept url and topicPrefix as params**

```ts
import { useEffect, useRef, useCallback, useState } from "react";
import mqtt, { type MqttClient } from "mqtt";
import type { MqttConnectionStatus } from "../types/telemetry";

type MessageHandler = (topic: string, payload: string) => void;

const RECONNECT_INTERVAL = 5000;

export function useMqtt(
  brokerUrl: string,
  topicPrefix: string,
  onMessage: MessageHandler,
) {
  const [status, setStatus] = useState<MqttConnectionStatus>("disconnected");
  const clientRef = useRef<MqttClient | null>(null);
  const onMessageRef = useRef(onMessage);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const connect = useCallback(() => {
    if (clientRef.current?.connected) return;

    setStatus("connecting");

    const client = mqtt.connect(brokerUrl, {
      reconnectPeriod: RECONNECT_INTERVAL,
      keepalive: 60,
      clean: true,
      clientId: `vtms-web-${Math.random().toString(16).slice(2, 8)}`,
    });

    client.on("connect", () => {
      setStatus("connected");
      client.subscribe(`${topicPrefix}#`, { qos: 0 });
    });

    client.on("message", (_topic, payload) => {
      onMessageRef.current(_topic, payload.toString());
    });

    client.on("error", () => setStatus("error"));
    client.on("close", () => setStatus("disconnected"));
    client.on("reconnect", () => setStatus("connecting"));

    clientRef.current = client;
  }, [brokerUrl, topicPrefix]);

  useEffect(() => {
    connect();
    return () => {
      if (clientRef.current) {
        clientRef.current.end(true);
        clientRef.current = null;
      }
    };
  }, [connect]);

  return { status };
}
```

**Step 2: Update useTelemetry to accept and pass mqtt config**

Change the signature and `useMqtt` call:

```ts
import type { MqttConfig } from "../types/config";

// Change line 41:
export function useTelemetry(mqttConfig: MqttConfig) {
  // ... existing code unchanged ...

  // Change line 127:
  const { status: connectionStatus } = useMqtt(mqttConfig.url, mqttConfig.topicPrefix, handleMessage);

  // ... rest unchanged ...
}
```

Also update topic matching in `handleMessage` to use a dynamic prefix. The current code hardcodes `"lemons/"` in `topic.startsWith(...)` and `.replace(...)` calls. Replace all `"lemons/"` references with a ref to `mqttConfig.topicPrefix`:

```ts
export function useTelemetry(mqttConfig: MqttConfig) {
  // ... state declarations ...
  const prefixRef = useRef(mqttConfig.topicPrefix);
  prefixRef.current = mqttConfig.topicPrefix;

  const handleMessage = useCallback((topic: string, payload: string) => {
    const now = Date.now();
    const prefix = prefixRef.current;

    if (topic.startsWith(`${prefix}gps/`)) {
      const field = topic.replace(`${prefix}gps/`, "");
      // ... existing GPS handling ...
    }

    if (topic.startsWith(`${prefix}DTC/`)) {
      const code = topic.replace(`${prefix}DTC/`, "");
      // ... existing DTC handling ...
    }

    if (topic.startsWith(prefix)) {
      const key = topic.replace(prefix, "");
      // ... existing metric handling ...
    }
  }, []);

  const { status: connectionStatus } = useMqtt(mqttConfig.url, mqttConfig.topicPrefix, handleMessage);
  // ... return ...
}
```

**Step 3: Update useGoPro to accept apiUrl as param**

```ts
export function useGoPro(apiUrl: string) {
  // Replace all `${API_BASE}/...` with `${apiUrl}/...`
  // Remove the `const API_BASE = ...` line at the top
  // ... rest of hook unchanged ...
}
```

**Step 4: Commit**

```
git add web/src/hooks/useMqtt.ts web/src/hooks/useTelemetry.ts web/src/hooks/useGoPro.ts
git commit -m "refactor: useMqtt, useTelemetry, useGoPro accept config as params"
```

---

### Task 9: Wire Everything Together in App.tsx and StatusBar

**Files:**
- Modify: `web/src/App.tsx` (all lines)
- Modify: `web/src/components/StatusBar.tsx` (add gear icon + onOpenSettings prop)

**Step 1: Update StatusBar to include gear icon**

Add an `onOpenSettings` prop and render a gear button in the right section:

```tsx
import type { MqttConnectionStatus, DtcEntry } from "../types/telemetry";

interface StatusBarProps {
  connectionStatus: MqttConnectionStatus;
  hasGpsFix: boolean;
  dtcs: DtcEntry[];
  onOpenSettings: () => void;
}

// ... statusIndicator unchanged ...

export function StatusBar({ connectionStatus, hasGpsFix, dtcs, onOpenSettings }: StatusBarProps) {
  const mqttStatus = statusIndicator[connectionStatus];

  return (
    <div className="status-bar">
      <div className="status-bar-left">
        {/* ... existing status items unchanged ... */}
      </div>

      <div className="status-bar-center">
        <span className="app-title">VTMS Live</span>
      </div>

      <div className="status-bar-right">
        {dtcs.length > 0 && (
          <span className="status-item dtc-alert">
            <span className="status-dot" style={{ backgroundColor: "#ef4444" }} />
            {dtcs.length} DTC{dtcs.length !== 1 ? "s" : ""}:{" "}
            {dtcs.map((d) => d.code).join(", ")}
          </span>
        )}
        <button className="settings-gear-btn" onClick={onOpenSettings} aria-label="Open settings" title="Settings">
          &#9881;
        </button>
      </div>
    </div>
  );
}
```

**Step 2: Update App.tsx to use config and settings panel**

```tsx
import { useState } from "react";
import { Layout } from "./components/Layout";
import { StatusBar } from "./components/StatusBar";
import { MapView } from "./components/MapView";
import { GaugePanel } from "./components/GaugePanel";
import { GoProView } from "./components/GoProView";
import { SettingsPanel } from "./components/SettingsPanel";
import { useTelemetry } from "./hooks/useTelemetry";
import { useGoPro } from "./hooks/useGoPro";
import { useConfig } from "./hooks/useConfig";
import "./App.css";

function App() {
  const { config, saveConfig, resetToDefaults } = useConfig();
  const [settingsOpen, setSettingsOpen] = useState(false);

  const { metrics, gps, trail, dtcs, connectionStatus } = useTelemetry(config.mqtt);
  const gopro = useGoPro(config.gopro.apiUrl);

  const hasGpsFix = gps.latitude !== null && gps.longitude !== null;

  return (
    <>
      <Layout
        statusBar={
          <StatusBar
            connectionStatus={connectionStatus}
            hasGpsFix={hasGpsFix}
            dtcs={dtcs}
            onOpenSettings={() => setSettingsOpen(true)}
          />
        }
        gopro={
          <GoProView
            streamWsUrl={config.gopro.streamWsUrl}
            connectionStatus={gopro.connectionStatus}
            isRecording={gopro.isRecording}
            activePreset={gopro.activePreset}
            batteryPercent={gopro.batteryPercent}
            remainingStorageGB={gopro.remainingStorageGB}
            onToggleRecord={gopro.toggleRecord}
            onSetPreset={gopro.setPreset}
          />
        }
        map={<MapView gps={gps} trail={trail} />}
        gauges={
          <GaugePanel
            metrics={metrics}
            gauges={config.gauges}
            topicPrefix={config.mqtt.topicPrefix}
          />
        }
      />
      {settingsOpen && (
        <SettingsPanel
          config={config}
          onSave={saveConfig}
          onReset={resetToDefaults}
          onClose={() => setSettingsOpen(false)}
        />
      )}
    </>
  );
}

export default App;
```

**Step 3: Verify build**

Run: `cd web && npm run build`
Expected: Build succeeds

**Step 4: Run e2e tests**

Run: `cd web && npx playwright test`
Expected: 10 tests pass (e2e tests use env vars for MQTT which still work as defaults)

**Step 5: Commit**

```
git add web/src/App.tsx web/src/components/StatusBar.tsx
git commit -m "feat: wire config panel into App with gear icon in StatusBar"
```

---

### Task 10: RadialGauge Type Compatibility Check

**Files:**
- Possibly modify: `web/src/components/RadialGauge.tsx`

**Step 1: Check RadialGauge prop type**

`RadialGauge` currently accepts `config: GaugeConfig`. The new `GaugeConfigEntry` is a superset (same fields + `id`). If TypeScript accepts this, no change needed. If it uses an exact type or explicit interface, update the prop type:

```tsx
// Change from:
import type { GaugeConfig } from "../types/telemetry";
// To:
import type { GaugeConfigEntry } from "../types/config";

// And update the prop interface accordingly.
```

This is a build-verification step -- if the build passes in Task 9, this task can be skipped.

**Step 2: Commit if changed**

```
git add web/src/components/RadialGauge.tsx
git commit -m "refactor: RadialGauge accepts GaugeConfigEntry type"
```

---

### Task 11: E2E Test for Settings Panel

**Files:**
- Modify: `web/e2e/dashboard.spec.ts` (append new test)

**Step 1: Add settings panel e2e test**

Append to the test suite:

```ts
// ---------- Test 11: Settings panel opens and closes ----------
test("settings panel opens via gear icon and closes", async ({ dashboardPage }) => {
  // Gear icon should be visible in status bar
  const gearBtn = dashboardPage.locator(".settings-gear-btn");
  await expect(gearBtn).toBeVisible();

  // Click gear icon to open settings
  await gearBtn.click();

  // Settings panel should be visible
  const panel = dashboardPage.locator(".settings-panel");
  await expect(panel).toBeVisible();

  // Should show Connection tab by default
  await expect(panel.locator(".settings-tab.active")).toHaveText("Connection");

  // Should show MQTT URL field
  await expect(panel.locator('input[placeholder="ws://host:port"]')).toBeVisible();

  // Switch to Gauges tab
  await panel.locator(".settings-tab", { hasText: "Gauges" }).click();

  // Should show gauge cards
  const gaugeCards = panel.locator(".settings-gauge-card");
  await expect(gaugeCards).toHaveCount(6); // 6 default gauges

  // Close via X button
  await panel.locator(".settings-close-btn").click();
  await expect(panel).not.toBeVisible();
});
```

**Step 2: Run e2e tests**

Run: `cd web && npx playwright test`
Expected: 11 tests pass

**Step 3: Commit**

```
git add web/e2e/dashboard.spec.ts
git commit -m "test: add e2e test for settings panel open/close and tabs"
```

---

### Task 12: Final Verification

**Step 1: Full build check**

Run: `cd web && npm run build`
Expected: Build succeeds

**Step 2: Server type check**

Run: `cd server && npx tsc --noEmit`
Expected: No errors

**Step 3: Full e2e suite**

Run: `cd web && npx playwright test`
Expected: 11 tests pass

**Step 4: Manual smoke test** (optional)

Start the server and frontend:
```
cd server && npm run dev &
cd web && npm run dev
```

Verify:
- Dashboard loads with default gauges
- Gear icon visible in status bar
- Clicking gear opens settings modal
- Can edit MQTT URL, GoPro URL
- Can add/remove/reorder gauges
- Save persists to `server/data/config.json`
- Reload picks up saved config
- Reset to Defaults restores original gauges
