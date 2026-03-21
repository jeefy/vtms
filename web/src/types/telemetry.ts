/** A single telemetry value received from MQTT */
export interface TelemetryValue {
  /** Raw string payload from MQTT */
  raw: string;
  /** Parsed numeric value (NaN if not parseable) */
  value: number;
  /** Timestamp when received (ms since epoch) */
  timestamp: number;
}

/** GPS position data */
export interface GpsData {
  latitude: number | null;
  longitude: number | null;
  altitude: number | null;
  /** Speed in m/s */
  speed: number | null;
  /** Track/heading in degrees */
  track: number | null;
  geohash: string | null;
  timestamp: number;
}

/** A single DTC (Diagnostic Trouble Code) */
export interface DtcEntry {
  code: string;
  description: string;
  timestamp: number;
}

/** MQTT connection states */
export type MqttConnectionStatus = "disconnected" | "connecting" | "connected" | "error";

/** Color zone for gauge rendering */
export interface GaugeZone {
  /** Start value (inclusive) */
  from: number;
  /** End value (inclusive) */
  to: number;
  /** CSS color */
  color: string;
}

/** Complete telemetry store state */
export interface TelemetryState {
  /** All metric values keyed by topic suffix (e.g. "RPM", "SPEED") */
  metrics: Map<string, TelemetryValue>;
  /** GPS position data */
  gps: GpsData;
  /** Active DTCs */
  dtcs: DtcEntry[];
  /** MQTT connection status */
  connectionStatus: MqttConnectionStatus;
}
