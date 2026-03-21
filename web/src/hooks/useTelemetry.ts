import { useState, useCallback, useRef } from "react";
import type {
  TelemetryValue,
  GpsData,
  DtcEntry,
} from "../types/telemetry";
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
export function useTelemetry() {
  const [metrics, setMetrics] = useState<Map<string, TelemetryValue>>(
    () => new Map()
  );
  const [gps, setGps] = useState<GpsData>(emptyGps);
  const [trail, setTrail] = useState<[number, number][]>([]);
  const [dtcs, setDtcs] = useState<DtcEntry[]>([]);

  // Use a ref for the trail so we can append without causing re-renders on every GPS update
  const trailRef = useRef<[number, number][]>([]);

  const handleMessage = useCallback((topic: string, payload: string) => {
    const now = Date.now();

    // GPS topics
    if (topic.startsWith("lemons/gps/")) {
      const field = topic.replace("lemons/gps/", "");
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
              setTrail(newTrail);
            }
            break;
          }
        }
        return next;
      });
      return;
    }

    // DTC topics
    if (topic.startsWith("lemons/DTC/")) {
      const code = topic.replace("lemons/DTC/", "");
      setDtcs((prev) => {
        // Replace existing DTC with same code, or add new
        const filtered = prev.filter((d) => d.code !== code);
        return [...filtered, { code, description: payload, timestamp: now }];
      });
      return;
    }

    // All other lemons/* topics are metrics
    if (topic.startsWith("lemons/")) {
      const key = topic.replace("lemons/", "");
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

  const { status: connectionStatus } = useMqtt(handleMessage);

  return {
    metrics,
    gps,
    trail,
    dtcs,
    connectionStatus,
  };
}
