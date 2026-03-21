import { useState, useEffect, useCallback, useRef } from "react";
import type { GoProState, GoProPreset } from "../types/gopro";
import { PRESET_GROUP_IDS } from "../types/gopro";

const POLL_INTERVAL = 5000;

export function useGoPro(apiUrl: string) {
  const [state, setState] = useState<GoProState>({
    connectionStatus: "disconnected",
    isRecording: false,
    activePreset: "video",
    batteryPercent: null,
    remainingStorageGB: null,
  });

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  // Auto-start/stop stream when connection changes
  const wasConnected = useRef(false);

  useEffect(() => {
    const poll = async () => {
      try {
        const connRes = await fetch(`${apiUrl}/api/gopro/connection`);
        if (!connRes.ok) {
          setState((prev) => ({ ...prev, connectionStatus: "disconnected" }));
          return;
        }
        const connData = await connRes.json();

        if (!connData.connected) {
          if (wasConnected.current) {
            // Camera disconnected - stop stream
            wasConnected.current = false;
            try {
              await fetch(`${apiUrl}/api/stream/stop`, { method: "POST" });
            } catch {
              // ignore
            }
          }
          setState((prev) => ({ ...prev, connectionStatus: "disconnected" }));
          return;
        }

        // Camera is connected - start stream if not already
        if (!wasConnected.current) {
          wasConnected.current = true;
          try {
            await fetch(`${apiUrl}/api/stream/start`, { method: "POST" });
          } catch {
            // ignore
          }
        }

        const stateRes = await fetch(`${apiUrl}/api/gopro/state`);
        if (!stateRes.ok) {
          setState((prev) => ({ ...prev, connectionStatus: "error" }));
          return;
        }

        const cameraState = await stateRes.json();
        const status = cameraState.status ?? {};

        setState({
          connectionStatus: "connected",
          isRecording: status["8"] === 1,
          activePreset: detectPreset(status),
          batteryPercent: status["2"] ?? null,
          remainingStorageGB: status["54"] != null
            ? Math.round((status["54"] / 1024) * 10) / 10
            : null,
        });
      } catch {
        setState((prev) => ({ ...prev, connectionStatus: "disconnected" }));
      }
    };

    poll();
    pollRef.current = setInterval(poll, POLL_INTERVAL);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [apiUrl]);

  // Use ref to avoid stale closure in toggleRecord
  const toggleRecord = useCallback(async () => {
    const action = stateRef.current.isRecording ? "stop" : "start";
    try {
      const res = await fetch(`${apiUrl}/api/gopro/shutter/${action}`);
      if (res.ok) {
        setState((prev) => ({ ...prev, isRecording: !prev.isRecording }));
      }
    } catch {
      // Will be corrected on next poll
    }
  }, [apiUrl]);

  const setPreset = useCallback(async (preset: GoProPreset) => {
    try {
      const res = await fetch(
        `${apiUrl}/api/gopro/presets/set_group?id=${PRESET_GROUP_IDS[preset]}`
      );
      if (res.ok) {
        setState((prev) => ({ ...prev, activePreset: preset }));
      }
    } catch {
      // Will be corrected on next poll
    }
  }, [apiUrl]);

  return { ...state, toggleRecord, setPreset };
}

function detectPreset(status: Record<string, number>): GoProPreset {
  const group = status["43"];
  if (group === 1001) return "photo";
  if (group === 1002) return "timelapse";
  return "video";
}
