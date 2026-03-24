import { useState, useCallback, useRef } from "react";
import type {
  TelemetryValue,
  GpsData,
  DtcEntry,
} from "../types/telemetry";
import type { MqttConfig } from "../types/config";
import { useMqtt } from "./useMqtt";

const TRAIL_MAX_LENGTH = 500;

/**
 * Parse a numeric value from an OBD string payload.
 *
 * python-obd sends values like "3500 revolutions_per_minute" or "85 degC".
 * We extract the leading number.
 */
function parseOBDValue(raw: string): number {
  const match = raw.match(/^-?[\d.]+/);
  return match ? parseFloat(match[0]) : NaN;
}

const emptyGps: GpsData = {
  latitude: null,
  longitude: null,
  altitude: null,
  speed: null,
  track: null,
  geohash: null,
  timestamp: 0,
};

/**
 * Central telemetry state hook.
 *
 * Subscribes to MQTT via `useMqtt`, parses incoming messages, and
 * exposes the latest values for metrics, GPS, and DTCs.
 *
 * This hook is the single source of truth. In the future, a `usePlayback`
 * hook can feed the same state shape from historical data.
 */
export function useTelemetry(mqttConfig: MqttConfig) {
  const [metrics, setMetrics] = useState<Map<string, TelemetryValue>>(
    () => new Map()
  );
  const [gps, setGps] = useState<GpsData>(emptyGps);
  const [trail, setTrail] = useState<[number, number][]>([]);
  const [dtcs, setDtcs] = useState<DtcEntry[]>([]);

  // Use a ref for the trail so we can append without causing re-renders on every GPS update
  const trailRef = useRef<[number, number][]>([]);
  const trailCountRef = useRef(0);
  const prefixRef = useRef(mqttConfig.topicPrefix);
  prefixRef.current = mqttConfig.topicPrefix;

  const handleMessage = useCallback((topic: string, payload: string) => {
    const now = Date.now();
    const prefix = prefixRef.current;

    // GPS topics
    if (topic.startsWith(`${prefix}gps/`)) {
      const field = topic.replace(`${prefix}gps/`, "");
      setGps((prev) => {
        const next = { ...prev, timestamp: now };
        switch (field) {
          case "latitude":
            next.latitude = parseFloat(payload);
            break;
          case "longitude":
            next.longitude = parseFloat(payload);
            break;
          case "altitude":
            next.altitude = parseFloat(payload);
            break;
          case "speed":
            next.speed = parseFloat(payload);
            break;
          case "track":
            next.track = parseFloat(payload);
            break;
          case "geohash":
            next.geohash = payload;
            break;
          case "pos": {
            const [lat, lon] = payload.split(",").map(Number);
            next.latitude = lat;
            next.longitude = lon;
            // Update trail
            if (!isNaN(lat) && !isNaN(lon)) {
              const newTrail = [...trailRef.current, [lat, lon] as [number, number]];
              if (newTrail.length > TRAIL_MAX_LENGTH) {
                newTrail.splice(0, newTrail.length - TRAIL_MAX_LENGTH);
              }
              trailRef.current = newTrail;
              trailCountRef.current++;
              if (trailCountRef.current % 5 === 0) {
                setTrail([...trailRef.current]);
              }
            }
            break;
          }
        }
        return next;
      });
      return;
    }

    // DTC topics
    if (topic.startsWith(`${prefix}DTC/`)) {
      const code = topic.replace(`${prefix}DTC/`, "");
      setDtcs((prev) => {
        // Replace existing DTC with same code, or add new
        const filtered = prev.filter((d) => d.code !== code);
        return [...filtered, { code, description: payload, timestamp: now }];
      });
      return;
    }

    // All other lemons/* topics are metrics
    if (topic.startsWith(prefix)) {
      const key = topic.replace(prefix, "");
      const value: TelemetryValue = {
        raw: payload,
        value: parseOBDValue(payload),
        timestamp: now,
      };
      setMetrics((prev) => {
        const next = new Map(prev);
        next.set(key, value);
        return next;
      });
    }
  }, []);

  const { status: connectionStatus } = useMqtt(mqttConfig.url, mqttConfig.topicPrefix, handleMessage);

  return {
    metrics,
    gps,
    trail,
    dtcs,
    connectionStatus,
  };
}
