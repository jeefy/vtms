import { useState } from "react";
import { Layout } from "./components/Layout";
import { StatusBar } from "./components/StatusBar";
import { MapView } from "./components/MapView";
import { GaugePanel } from "./components/GaugePanel";
import { GoProView } from "./components/GoProView";
import { SettingsPanel } from "./components/SettingsPanel";
import { useTelemetry } from "./hooks/useTelemetry";
import { useGoPro } from "./hooks/useGoPro";
import { useConfig } from "./hooks/useConfig";
import "./App.css";

function App() {
  const { config, saveConfig, resetToDefaults } = useConfig();
  const [settingsOpen, setSettingsOpen] = useState(false);

  const { metrics, gps, trail, dtcs, connectionStatus } = useTelemetry(config.mqtt);
  const gopro = useGoPro(config.gopro.apiUrl);

  const hasGpsFix = gps.latitude !== null && gps.longitude !== null;

  return (
    <>
      <Layout
        statusBar={
          <StatusBar
            connectionStatus={connectionStatus}
            hasGpsFix={hasGpsFix}
            dtcs={dtcs}
            onOpenSettings={() => setSettingsOpen(true)}
          />
        }
        gopro={
          <GoProView
            streamWsUrl={config.gopro.streamWsUrl}
            connectionStatus={gopro.connectionStatus}
            isRecording={gopro.isRecording}
            activePreset={gopro.activePreset}
            batteryPercent={gopro.batteryPercent}
            remainingStorageGB={gopro.remainingStorageGB}
            onToggleRecord={gopro.toggleRecord}
            onSetPreset={gopro.setPreset}
          />
        }
        map={<MapView gps={gps} trail={trail} />}
        gauges={
          <GaugePanel
            metrics={metrics}
            gauges={config.gauges}
            topicPrefix={config.mqtt.topicPrefix}
          />
        }
      />
      {settingsOpen && (
        <SettingsPanel
          config={config}
          onSave={saveConfig}
          onReset={resetToDefaults}
          onClose={() => setSettingsOpen(false)}
        />
      )}
    </>
  );
}

export default App;
