interface SignalMeterProps {
  /** Current signal power in dB */
  signalPower: number | null;
  /** Squelch threshold in dB */
  squelchDb: number | null;
}

/** Typical signal power range in dB */
const MIN_DB = -60;
const MAX_DB = 0;

function clampPercent(value: number, min: number, max: number): number {
  return Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
}

function signalColor(percent: number): string {
  if (percent < 25) return "var(--signal-low, #ef4444)";
  if (percent < 50) return "var(--signal-med, #f59e0b)";
  return "var(--signal-high, #22c55e)";
}

/**
 * Horizontal bar showing signal power with squelch threshold marker.
 *
 * Uses `role="meter"` for accessibility.
 */
export function SignalMeter({ signalPower, squelchDb }: SignalMeterProps) {
  const power = signalPower ?? MIN_DB;
  const percent = clampPercent(power, MIN_DB, MAX_DB);
  const squelchPercent =
    squelchDb != null ? clampPercent(squelchDb, MIN_DB, MAX_DB) : null;

  return (
    <div className="signal-meter">
      <div className="signal-meter__label">
        Signal: {signalPower != null ? `${power.toFixed(1)} dB` : "—"}
      </div>
      <div className="signal-meter__track">
        <div
          className="signal-meter__fill"
          role="meter"
          aria-valuenow={power}
          aria-valuemin={MIN_DB}
          aria-valuemax={MAX_DB}
          aria-label="Signal power"
          style={{
            width: `${percent}%`,
            backgroundColor: signalColor(percent),
          }}
        />
        {squelchPercent != null && (
          <div
            className="signal-meter__squelch"
            style={{ left: `${squelchPercent}%` }}
            title={`Squelch: ${squelchDb!.toFixed(1)} dB`}
          />
        )}
      </div>
    </div>
  );
}
