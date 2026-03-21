import { useState, useEffect, useCallback, useRef } from "react";
import type { GoProPreset } from "../types/gopro";

interface GoProControlsProps {
  isRecording: boolean;
  activePreset: GoProPreset;
  batteryPercent: number | null;
  remainingStorageGB: number | null;
  onToggleRecord: () => void;
  onSetPreset: (preset: GoProPreset) => void;
}

export function GoProControls({
  isRecording,
  activePreset,
  batteryPercent,
  remainingStorageGB,
  onToggleRecord,
  onSetPreset,
}: GoProControlsProps) {
  const [visible, setVisible] = useState(true);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const resetHideTimer = useCallback(() => {
    setVisible(true);
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    hideTimerRef.current = setTimeout(() => setVisible(false), 4000);
  }, []);

  useEffect(() => {
    resetHideTimer();
    return () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    };
  }, [resetHideTimer]);

  return (
    <div
      className={`gopro-controls ${visible ? "gopro-controls-visible" : "gopro-controls-hidden"}`}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => resetHideTimer()}
      onTouchStart={() => resetHideTimer()}
    >
      <div className="gopro-controls-row">
        <button
          className={`gopro-record-btn ${isRecording ? "recording" : ""}`}
          onClick={onToggleRecord}
          aria-label={isRecording ? "Stop recording" : "Start recording"}
        >
          <span className="gopro-record-dot" />
          {isRecording ? "STOP" : "REC"}
        </button>

        <div className="gopro-presets">
          {(["video", "photo", "timelapse"] as GoProPreset[]).map((preset) => (
            <button
              key={preset}
              className={`gopro-preset-btn ${activePreset === preset ? "active" : ""}`}
              onClick={() => onSetPreset(preset)}
              aria-label={`Switch to ${preset}`}
            >
              {preset === "video" ? "VID" : preset === "photo" ? "PIC" : "TL"}
            </button>
          ))}
        </div>
      </div>

      <div className="gopro-status-row">
        {batteryPercent != null && (
          <span className="gopro-status-item">BAT {batteryPercent}%</span>
        )}
        {remainingStorageGB != null && (
          <span className="gopro-status-item">SD {remainingStorageGB}G</span>
        )}
      </div>
    </div>
  );
}
