/** SDR session status as published to MQTT */
export type SDRStatus = "recording" | "stopped" | "offline";

/** SDR state assembled from `{prefix}sdr/state/#` MQTT topics */
export interface SDRState {
  /** Current tuned frequency in Hz */
  freq: number | null;
  /** Modulation type (e.g. "fm", "am") */
  mod: string | null;
  /** Receiver gain setting */
  gain: number | string | null;
  /** Squelch threshold in dB */
  squelch_db: number | null;
  /** Session status */
  status: SDRStatus;
  /** Signal power in dB (debounced to 5 Hz by MQTT bridge) */
  signal_power: number | null;
  /** PPM correction */
  ppm: number | null;
}

/** A single transcription line from the SDR session */
export interface TranscriptionLine {
  /** Transcribed text */
  text: string;
  /** Timestamp when received (ms since epoch) */
  timestamp: number;
}

/** Control actions that can be published to `{prefix}sdr/control/{action}` */
export type SDRControlAction =
  | "set_freq"
  | "set_squelch"
  | "set_gain"
  | "set_ppm"
  | "set_config"
  | "autotune";
