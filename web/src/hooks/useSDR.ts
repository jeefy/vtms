import { useState, useCallback, useRef } from "react";
import type { SDRState, SDRStatus, TranscriptionLine, SDRControlAction } from "../types/sdr";
import type { MqttConfig } from "../types/config";
import { useMqtt } from "./useMqtt";

/** Maximum transcription lines to keep in memory */
const MAX_TRANSCRIPTION_LINES = 200;

const initialState: SDRState = {
  freq: null,
  mod: null,
  gain: null,
  squelch_db: null,
  status: "offline",
  signal_power: null,
  ppm: null,
};

/**
 * SDR state hook.
 *
 * Subscribes to `{prefix}sdr/state/#` MQTT topics and exposes the latest
 * SDR state, transcription lines, and a `publish` function for sending
 * control commands back to `{prefix}sdr/control/{action}`.
 *
 * Mirrors the pattern of `useTelemetry` but scoped to SDR topics.
 */
export function useSDR(mqttConfig: MqttConfig) {
  const [state, setState] = useState<SDRState>(initialState);
  const [transcriptions, setTranscriptions] = useState<TranscriptionLine[]>([]);

  const prefixRef = useRef(mqttConfig.topicPrefix);
  prefixRef.current = mqttConfig.topicPrefix;

  const handleMessage = useCallback((topic: string, payload: string) => {
    const prefix = prefixRef.current;
    const sdrStatePrefix = `${prefix}sdr/state/`;

    if (!topic.startsWith(sdrStatePrefix)) {
      return;
    }

    const key = topic.slice(sdrStatePrefix.length);

    switch (key) {
      case "freq": {
        const v = parseFloat(payload);
        setState((prev) => ({ ...prev, freq: isNaN(v) ? null : v }));
        break;
      }
      case "mod":
        setState((prev) => ({ ...prev, mod: payload || null }));
        break;
      case "gain": {
        const numGain = parseFloat(payload);
        setState((prev) => ({
          ...prev,
          gain: isNaN(numGain) ? payload : numGain,
        }));
        break;
      }
      case "squelch_db": {
        const v = parseFloat(payload);
        setState((prev) => ({
          ...prev,
          squelch_db: isNaN(v) ? null : v,
        }));
        break;
      }
      case "status":
        setState((prev) => ({
          ...prev,
          status: (payload as SDRStatus) || "offline",
        }));
        break;
      case "signal_power": {
        const v = parseFloat(payload);
        setState((prev) => ({
          ...prev,
          signal_power: isNaN(v) ? null : v,
        }));
        break;
      }
      case "ppm": {
        const v = parseInt(payload, 10);
        setState((prev) => ({
          ...prev,
          ppm: isNaN(v) ? null : v,
        }));
        break;
      }
      case "last_transcription":
        if (payload) {
          setTranscriptions((prev) => {
            const next = [
              ...prev,
              { text: payload, timestamp: Date.now() },
            ];
            if (next.length > MAX_TRANSCRIPTION_LINES) {
              return next.slice(next.length - MAX_TRANSCRIPTION_LINES);
            }
            return next;
          });
        }
        break;
    }
  }, []);

  const { status: connectionStatus, publish: mqttPublish } = useMqtt(
    mqttConfig.url,
    mqttConfig.topicPrefix,
    handleMessage,
  );

  /**
   * Publish a control command to `{prefix}sdr/control/{action}`.
   *
   * Scalar values are sent as plain strings; objects are JSON-encoded.
   * Returns `true` if the message was sent, `false` if the client was
   * not connected.
   */
  const publish = useCallback(
    (action: SDRControlAction, value: string | number | Record<string, unknown>): boolean => {
      const topic = `${prefixRef.current}sdr/control/${action}`;
      const payload =
        typeof value === "object" ? JSON.stringify(value) : String(value);
      return mqttPublish(topic, payload);
    },
    [mqttPublish],
  );

  return {
    ...state,
    transcriptions,
    connectionStatus,
    publish,
  };
}
