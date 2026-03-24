import { useCallback } from "react";
import type { SDRControlAction } from "../types/sdr";

interface SDRControlsProps {
  /** Current tuned frequency in Hz */
  freq: number | null;
  /** Current modulation type */
  mod: string | null;
  /** Current squelch threshold in dB */
  squelchDb: number | null;
  /** Current gain setting */
  gain: number | string | null;
  /** Current PPM correction */
  ppm: number | null;
  /** Whether the SDR session is active */
  isActive: boolean;
  /** Publish a control command to MQTT */
  onPublish: (action: SDRControlAction, value: string | number | Record<string, unknown>) => void;
}

function formatFrequency(hz: number): string {
  if (hz >= 1_000_000) {
    return `${(hz / 1_000_000).toFixed(3)} MHz`;
  }
  if (hz >= 1_000) {
    return `${(hz / 1_000).toFixed(1)} kHz`;
  }
  return `${hz} Hz`;
}

/**
 * SDR control panel with frequency display, squelch/gain/PPM sliders,
 * and an autotune button.
 *
 * Publishes control messages via the `onPublish` callback.
 */
export function SDRControls({
  freq,
  mod,
  squelchDb,
  gain,
  ppm,
  isActive,
  onPublish,
}: SDRControlsProps) {
  const handleSquelchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      onPublish("set_squelch", parseFloat(e.target.value));
    },
    [onPublish],
  );

  const handleGainChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      onPublish("set_gain", parseFloat(e.target.value));
    },
    [onPublish],
  );

  const handlePpmChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      onPublish("set_ppm", parseInt(e.target.value, 10));
    },
    [onPublish],
  );

  const handleAutotune = useCallback(() => {
    onPublish("autotune", "");
  }, [onPublish]);

  const numericGain = typeof gain === "number" ? gain : 0;

  return (
    <div className="sdr-controls">
      <div className="sdr-controls__freq">
        <span className="sdr-controls__freq-value">
          {freq != null ? formatFrequency(freq) : "—"}
        </span>
        {mod && <span className="sdr-controls__mod">{mod.toUpperCase()}</span>}
      </div>

      <div className="sdr-controls__sliders">
        <label className="sdr-controls__slider">
          <span>Squelch</span>
          <input
            type="range"
            min={-60}
            max={0}
            step={0.5}
            value={squelchDb ?? -30}
            onChange={handleSquelchChange}
            disabled={!isActive}
          />
          <span className="sdr-controls__slider-value">
            {squelchDb != null ? `${squelchDb.toFixed(1)} dB` : "—"}
          </span>
        </label>

        <label className="sdr-controls__slider">
          <span>Gain</span>
          <input
            type="range"
            min={0}
            max={50}
            step={1}
            value={numericGain}
            onChange={handleGainChange}
            disabled={!isActive || typeof gain === "string"}
          />
          <span className="sdr-controls__slider-value">
            {gain != null ? (typeof gain === "string" ? gain : `${gain}`) : "—"}
          </span>
        </label>

        <label className="sdr-controls__slider">
          <span>PPM</span>
          <input
            type="range"
            min={-100}
            max={100}
            step={1}
            value={ppm ?? 0}
            onChange={handlePpmChange}
            disabled={!isActive}
          />
          <span className="sdr-controls__slider-value">{ppm ?? 0}</span>
        </label>
      </div>

      <button
        className="sdr-controls__autotune"
        onClick={handleAutotune}
        disabled={!isActive}
        title="Auto-tune gain, squelch, and modulation"
      >
        Autotune
      </button>
    </div>
  );
}
