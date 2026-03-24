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
      case "freq":
        setState((prev) => ({ ...prev, freq: parseFloat(payload) || null }));
        break;
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
      case "squelch_db":
        setState((prev) => ({
          ...prev,
          squelch_db: parseFloat(payload) || null,
        }));
        break;
      case "status":
        setState((prev) => ({
          ...prev,
          status: (payload as SDRStatus) || "offline",
        }));
        break;
      case "signal_power":
        setState((prev) => ({
          ...prev,
          signal_power: parseFloat(payload),
        }));
        break;
      case "ppm":
        setState((prev) => ({
          ...prev,
          ppm: parseInt(payload, 10) || null,
        }));
        break;
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

  const { status: connectionStatus } = useMqtt(
    mqttConfig.url,
    mqttConfig.topicPrefix,
    handleMessage,
  );

  /**
   * Publish a control command to `{prefix}sdr/control/{action}`.
   *
   * This is a no-op stub — the `useMqtt` hook doesn't expose the client
   * for publishing. For now, control messages are sent via the REST API
   * or by creating a separate MQTT publish connection. This placeholder
   * keeps the API surface ready for when we add publish support to useMqtt.
   */
  const publish = useCallback(
    (_action: SDRControlAction, _value: string | number | Record<string, unknown>) => {
      // TODO: implement when useMqtt exposes publish capability
      console.warn("useSDR.publish() not yet wired — useMqtt needs publish support");
    },
    [],
  );

  return {
    ...state,
    transcriptions,
    connectionStatus,
    publish,
  };
}
