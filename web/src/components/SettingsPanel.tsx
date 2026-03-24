import { useState } from "react";
import type { AppConfig, GaugeConfigEntry, GoProConfig, MqttConfig } from "../types/config";

interface SettingsPanelProps {
  config: AppConfig;
  onSave: (config: AppConfig) => Promise<{ ok: boolean; error?: string }>;
  onReset: () => Promise<{ ok: boolean; error?: string; config?: AppConfig }>;
  onClose: () => void;
}

export function SettingsPanel({ config, onSave, onReset, onClose }: SettingsPanelProps) {
  const [draft, setDraft] = useState<AppConfig>(structuredClone(config));
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"connection" | "gauges">("connection");

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const result = await onSave(draft);
      if (result.ok) {
        onClose();
      } else {
        setError(result.error ?? "Save failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    setResetting(true);
    setError(null);
    try {
      const result = await onReset();
      if (result.ok && result.config) {
        setDraft(structuredClone(result.config));
      } else {
        setError(result.error ?? "Reset failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setResetting(false);
    }
  };

  const updateMqtt = (field: keyof MqttConfig, value: string) => {
    setDraft((d) => ({ ...d, mqtt: { ...d.mqtt, [field]: value } }));
  };

  const updateGoPro = (field: keyof GoProConfig, value: string) => {
    setDraft((d) => ({ ...d, gopro: { ...d.gopro, [field]: value } }));
  };

  const updateGauge = (index: number, field: string, value: string | number) => {
    setDraft((d) => {
      const gauges = [...d.gauges];
      gauges[index] = { ...gauges[index], [field]: value };
      return { ...d, gauges };
    });
  };

  const addGauge = () => {
    const id = `gauge_${Date.now()}`;
    const newGauge: GaugeConfigEntry = {
      id,
      topic: "",
      label: "New Gauge",
      min: 0,
      max: 100,
      unit: "",
    };
    setDraft((d) => ({ ...d, gauges: [...d.gauges, newGauge] }));
  };

  const removeGauge = (index: number) => {
    setDraft((d) => ({
      ...d,
      gauges: d.gauges.filter((_, i) => i !== index),
    }));
  };

  const moveGauge = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= draft.gauges.length) return;
    setDraft((d) => {
      const gauges = [...d.gauges];
      [gauges[index], gauges[target]] = [gauges[target], gauges[index]];
      return { ...d, gauges };
    });
  };

  return (
    <div className="settings-backdrop" onClick={onClose}>
      <div className="settings-panel" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <h2>Settings</h2>
          <button className="settings-close-btn" onClick={onClose} aria-label="Close settings">
            &times;
          </button>
        </div>

        <div className="settings-tabs">
          <button
            className={`settings-tab ${activeTab === "connection" ? "active" : ""}`}
            onClick={() => setActiveTab("connection")}
          >
            Connection
          </button>
          <button
            className={`settings-tab ${activeTab === "gauges" ? "active" : ""}`}
            onClick={() => setActiveTab("gauges")}
          >
            Gauges
          </button>
        </div>

        <div className="settings-body">
          {activeTab === "connection" && (
            <div className="settings-section">
              <h3>MQTT</h3>
              <label className="settings-field">
                <span>Broker URL</span>
                <input
                  type="text"
                  value={draft.mqtt.url}
                  onChange={(e) => updateMqtt("url", e.target.value)}
                  placeholder="ws://host:port"
                />
              </label>
              <label className="settings-field">
                <span>Topic Prefix</span>
                <input
                  type="text"
                  value={draft.mqtt.topicPrefix}
                  onChange={(e) => updateMqtt("topicPrefix", e.target.value)}
                  placeholder="lemons/"
                />
              </label>

              <h3>GoPro</h3>
              <label className="settings-field">
                <span>API URL</span>
                <input
                  type="text"
                  value={draft.gopro.apiUrl}
                  onChange={(e) => updateGoPro("apiUrl", e.target.value)}
                  placeholder="http://host:port"
                />
              </label>
              <label className="settings-field">
                <span>Stream WS URL</span>
                <input
                  type="text"
                  value={draft.gopro.streamWsUrl}
                  onChange={(e) => updateGoPro("streamWsUrl", e.target.value)}
                  placeholder="ws://host:port"
                />
              </label>
            </div>
          )}

          {activeTab === "gauges" && (
            <div className="settings-section">
              {draft.gauges.map((gauge, i) => (
                <div key={gauge.id} className="settings-gauge-card">
                  <div className="settings-gauge-header">
                    <strong>{gauge.label || "Untitled"}</strong>
                    <div className="settings-gauge-actions">
                      <button
                        onClick={() => moveGauge(i, -1)}
                        disabled={i === 0}
                        aria-label="Move up"
                        title="Move up"
                      >
                        &uarr;
                      </button>
                      <button
                        onClick={() => moveGauge(i, 1)}
                        disabled={i === draft.gauges.length - 1}
                        aria-label="Move down"
                        title="Move down"
                      >
                        &darr;
                      </button>
                      <button
                        onClick={() => removeGauge(i)}
                        className="settings-remove-btn"
                        aria-label="Remove gauge"
                        title="Remove"
                      >
                        &times;
                      </button>
                    </div>
                  </div>
                  <div className="settings-gauge-fields">
                    <label className="settings-field">
                      <span>Label</span>
                      <input
                        type="text"
                        value={gauge.label}
                        onChange={(e) => updateGauge(i, "label", e.target.value)}
                      />
                    </label>
                    <label className="settings-field">
                      <span>MQTT Topic</span>
                      <input
                        type="text"
                        value={gauge.topic}
                        onChange={(e) => updateGauge(i, "topic", e.target.value)}
                        placeholder="lemons/RPM"
                      />
                    </label>
                    <div className="settings-field-row">
                      <label className="settings-field">
                        <span>Min</span>
                        <input
                          type="number"
                          value={gauge.min}
                          onChange={(e) => updateGauge(i, "min", Number(e.target.value))}
                        />
                      </label>
                      <label className="settings-field">
                        <span>Max</span>
                        <input
                          type="number"
                          value={gauge.max}
                          onChange={(e) => updateGauge(i, "max", Number(e.target.value))}
                        />
                      </label>
                      <label className="settings-field">
                        <span>Unit</span>
                        <input
                          type="text"
                          value={gauge.unit}
                          onChange={(e) => updateGauge(i, "unit", e.target.value)}
                          placeholder="rpm"
                        />
                      </label>
                    </div>
                  </div>
                </div>
              ))}
              <button className="settings-add-btn" onClick={addGauge}>
                + Add Gauge
              </button>
            </div>
          )}
        </div>

        {error && <div className="settings-error">{error}</div>}

        <div className="settings-footer">
          <button className="settings-btn settings-btn-secondary" onClick={handleReset} disabled={saving || resetting}>
            {resetting ? "Resetting..." : "Reset to Defaults"}
          </button>
          <div className="settings-footer-right">
            <button className="settings-btn settings-btn-secondary" onClick={onClose} disabled={saving || resetting}>
              Cancel
            </button>
            <button className="settings-btn settings-btn-primary" onClick={handleSave} disabled={saving || resetting}>
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
