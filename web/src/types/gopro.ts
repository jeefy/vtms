export type GoProConnectionStatus = "disconnected" | "connecting" | "connected" | "error";

export type GoProPreset = "video" | "photo" | "timelapse";

export const PRESET_GROUP_IDS: Record<GoProPreset, number> = {
  video: 1000,
  photo: 1001,
  timelapse: 1002,
};

export interface GoProState {
  connectionStatus: GoProConnectionStatus;
  isRecording: boolean;
  activePreset: GoProPreset;
  batteryPercent: number | null;
  remainingStorageGB: number | null;
}
