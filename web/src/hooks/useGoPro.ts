import { useState, useEffect, useCallback, useRef } from "react";
import type { GoProState, GoProPreset } from "../types/gopro";
import { PRESET_GROUP_IDS } from "../types/gopro";

const API_BASE = import.meta.env.VITE_GOPRO_API_URL ?? "http://localhost:3001";
const POLL_INTERVAL = 5000;

export function useGoPro() {
  const [state, setState] = useState<GoProState>({
    connectionStatus: "disconnected",
    isRecording: false,
    activePreset: "video",
    batteryPercent: null,
    remainingStorageGB: null,
  });

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const poll = async () => {
      try {
        const connRes = await fetch(`${API_BASE}/api/gopro/connection`);
        const connData = await connRes.json();

        if (!connData.connected) {
          setState((prev) => ({ ...prev, connectionStatus: "disconnected" }));
          return;
        }

        const stateRes = await fetch(`${API_BASE}/api/gopro/state`);
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
  }, []);

  const toggleRecord = useCallback(async () => {
    const action = state.isRecording ? "stop" : "start";
    try {
      await fetch(`${API_BASE}/api/gopro/shutter/${action}`);
      setState((prev) => ({ ...prev, isRecording: !prev.isRecording }));
    } catch {
      // Will be corrected on next poll
    }
  }, [state.isRecording]);

  const setPreset = useCallback(async (preset: GoProPreset) => {
    try {
      await fetch(`${API_BASE}/api/gopro/presets/set_group?id=${PRESET_GROUP_IDS[preset]}`);
      setState((prev) => ({ ...prev, activePreset: preset }));
    } catch {
      // Will be corrected on next poll
    }
  }, []);

  const startStream = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/api/stream/start`, { method: "POST" });
    } catch {
      console.warn("Failed to start stream");
    }
  }, []);

  const stopStream = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/api/stream/stop`, { method: "POST" });
    } catch {
      console.warn("Failed to stop stream");
    }
  }, []);

  return { ...state, toggleRecord, setPreset, startStream, stopStream };
}

function detectPreset(status: Record<string, number>): GoProPreset {
  const group = status["43"];
  if (group === 1001) return "photo";
  if (group === 1002) return "timelapse";
  return "video";
}
