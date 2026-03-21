import type { GaugeConfig } from "../types/telemetry";

/**
 * Gauge configuration list.
 *
 * To add a new gauge, add an entry here. No component changes needed.
 * The `topic` must match the MQTT topic published by client.py
 * (e.g. "lemons/RPM" publishes values like "3500 revolutions_per_minute").
 */
export const gaugeConfig: GaugeConfig[] = [
  {
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
    topic: "lemons/SPEED",
    label: "Speed",
    min: 0,
    max: 200,
    unit: "km/h",
    zones: [{ from: 0, to: 200, color: "#4ade80" }],
  },
  {
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
    topic: "lemons/THROTTLE_POS",
    label: "Throttle",
    min: 0,
    max: 100,
    unit: "%",
    zones: [{ from: 0, to: 100, color: "#4ade80" }],
  },
  {
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

/**
 * MQTT broker configuration.
 * The broker must have WebSocket support enabled.
 */
export const mqttConfig = {
  /** WebSocket URL for the MQTT broker */
  url: import.meta.env.VITE_MQTT_URL ?? "ws://192.168.50.24:9001",
  /** MQTT topic prefix */
  topicPrefix: "lemons/",
  /** Reconnect interval in ms */
  reconnectInterval: 5000,
};
