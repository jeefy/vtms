import { useEffect, useRef } from "react";
import JSMpeg from "@cycjimmy/jsmpeg-player";
import { GoProControls } from "./GoProControls";
import type { GoProState, GoProPreset } from "../types/gopro";

interface GoProViewProps extends GoProState {
  streamWsUrl: string;
  onToggleRecord: () => void;
  onSetPreset: (preset: GoProPreset) => void;
}

export function GoProView({
  streamWsUrl,
  connectionStatus,
  isRecording,
  activePreset,
  batteryPercent,
  remainingStorageGB,
  onToggleRecord,
  onSetPreset,
}: GoProViewProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const playerRef = useRef<InstanceType<typeof JSMpeg.VideoElement> | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !canvas.parentElement || connectionStatus !== "connected") return;

    playerRef.current = new JSMpeg.VideoElement(
      canvas.parentElement,
      streamWsUrl,
      { canvas },
      { audio: false, videoBufferSize: 512 * 1024 }
    );

    return () => {
      playerRef.current?.destroy();
      playerRef.current = null;
    };
  }, [streamWsUrl, connectionStatus]);

  if (connectionStatus !== "connected") {
    const message =
      connectionStatus === "connecting"
        ? "Connecting to GoPro..."
        : connectionStatus === "error"
          ? "GoPro Communication Error"
          : "No Camera Connected";
    return (
      <div className="gopro-view gopro-disconnected">
        <div className="gopro-placeholder">
          <span className="gopro-placeholder-icon">CAM</span>
          <span className="gopro-placeholder-text">{message}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="gopro-view">
      <canvas ref={canvasRef} className="gopro-canvas" />
      <GoProControls
        isRecording={isRecording}
        activePreset={activePreset}
        batteryPercent={batteryPercent}
        remainingStorageGB={remainingStorageGB}
        onToggleRecord={onToggleRecord}
        onSetPreset={onSetPreset}
      />
    </div>
  );
}
