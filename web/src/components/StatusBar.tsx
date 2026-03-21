import type { MqttConnectionStatus, DtcEntry } from "../types/telemetry";

interface StatusBarProps {
  connectionStatus: MqttConnectionStatus;
  hasGpsFix: boolean;
  dtcs: DtcEntry[];
  onOpenSettings: () => void;
}

const statusIndicator: Record<MqttConnectionStatus, { color: string; label: string }> = {
  connected: { color: "#4ade80", label: "MQTT Connected" },
  connecting: { color: "#facc15", label: "MQTT Connecting..." },
  disconnected: { color: "#ef4444", label: "MQTT Disconnected" },
  error: { color: "#ef4444", label: "MQTT Error" },
};

export function StatusBar({ connectionStatus, hasGpsFix, dtcs, onOpenSettings }: StatusBarProps) {
  const mqttStatus = statusIndicator[connectionStatus];

  return (
    <div className="status-bar">
      <div className="status-bar-left">
        <span className="status-item">
          <span className="status-dot" style={{ backgroundColor: mqttStatus.color }} />
          {mqttStatus.label}
        </span>
        <span className="status-item">
          <span
            className="status-dot"
            style={{ backgroundColor: hasGpsFix ? "#4ade80" : "#64748b" }}
          />
          {hasGpsFix ? "GPS Fix" : "No GPS"}
        </span>
      </div>

      <div className="status-bar-center">
        <span className="app-title">VTMS Live</span>
      </div>

      <div className="status-bar-right">
        {dtcs.length > 0 && (
          <span className="status-item dtc-alert">
            <span className="status-dot" style={{ backgroundColor: "#ef4444" }} />
            {dtcs.length} DTC{dtcs.length !== 1 ? "s" : ""}:{" "}
            {dtcs.map((d) => d.code).join(", ")}
          </span>
        )}
        <button className="settings-gear-btn" onClick={onOpenSettings} aria-label="Open settings" title="Settings">
          &#9881;
        </button>
      </div>
    </div>
  );
}
