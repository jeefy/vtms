import { readFile, writeFile, mkdir, rename } from "node:fs/promises";
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
    const parsed = JSON.parse(raw);
    validateConfig(parsed);
    return parsed;
  } catch {
    console.warn("Failed to load config, using defaults");
    return structuredClone(DEFAULT_CONFIG);
  }
}

export async function saveConfig(config: AppConfig): Promise<void> {
  validateConfig(config);
  await mkdir(CONFIG_DIR, { recursive: true });
  const tmpPath = CONFIG_PATH + ".tmp";
  await writeFile(tmpPath, JSON.stringify(config, null, 2), "utf-8");
  await rename(tmpPath, CONFIG_PATH);
}

export function getDefaultConfig(): AppConfig {
  return structuredClone(DEFAULT_CONFIG);
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
    if (gauge.zones !== undefined) {
      if (!Array.isArray(gauge.zones)) throw new Error("gauge.zones must be an array");
      for (const z of gauge.zones) {
        if (typeof z !== "object" || z === null) throw new Error("zone must be an object");
        if (typeof z.from !== "number") throw new Error("zone.from must be a number");
        if (typeof z.to !== "number") throw new Error("zone.to must be a number");
        if (typeof z.color !== "string") throw new Error("zone.color must be a string");
      }
    }
    if (gauge.decimals !== undefined && typeof gauge.decimals !== "number") {
      throw new Error("gauge.decimals must be a number");
    }
  }
}
