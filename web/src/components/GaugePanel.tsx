import { RadialGauge } from "./RadialGauge";
import { gaugeConfig } from "../config/gauges";
import type { TelemetryValue } from "../types/telemetry";

interface GaugePanelProps {
  metrics: Map<string, TelemetryValue>;
}

/**
 * Renders a grid of radial gauges based on the gauge configuration.
 *
 * Each gauge reads its value from the metrics map using the topic suffix
 * (e.g. topic "lemons/RPM" -> key "RPM").
 */
export function GaugePanel({ metrics }: GaugePanelProps) {
  return (
    <div className="gauge-panel">
      {gaugeConfig.map((cfg) => {
        const key = cfg.topic.replace("lemons/", "");
        const telemetry = metrics.get(key);
        const value = telemetry?.value ?? NaN;

        return (
          <div key={cfg.topic} className="gauge-cell">
            <RadialGauge config={cfg} value={value} />
          </div>
        );
      })}
    </div>
  );
}
