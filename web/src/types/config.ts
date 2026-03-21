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
