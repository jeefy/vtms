import { RadialGauge } from "./RadialGauge";
import type { TelemetryValue } from "../types/telemetry";
import type { GaugeConfigEntry } from "../types/config";

interface GaugePanelProps {
  metrics: Map<string, TelemetryValue>;
  gauges: GaugeConfigEntry[];
  topicPrefix: string;
}

export function GaugePanel({ metrics, gauges, topicPrefix }: GaugePanelProps) {
  return (
    <div className="gauge-panel">
      {gauges.map((cfg) => {
        const key = cfg.topic.replace(topicPrefix, "");
        const telemetry = metrics.get(key);
        const value = telemetry?.value ?? NaN;

        return (
          <div key={cfg.id} className="gauge-cell">
            <RadialGauge config={cfg} value={value} />
          </div>
        );
      })}
    </div>
  );
}
