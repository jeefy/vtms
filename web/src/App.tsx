import { Layout } from "./components/Layout";
import { StatusBar } from "./components/StatusBar";
import { MapView } from "./components/MapView";
import { GaugePanel } from "./components/GaugePanel";
import { GoProView } from "./components/GoProView";
import { useTelemetry } from "./hooks/useTelemetry";
import { useGoPro } from "./hooks/useGoPro";
import "./App.css";

const STREAM_WS_URL =
  import.meta.env.VITE_GOPRO_STREAM_URL ?? "ws://localhost:9002";

function App() {
  const { metrics, gps, trail, dtcs, connectionStatus } = useTelemetry();
  const gopro = useGoPro();

  const hasGpsFix = gps.latitude !== null && gps.longitude !== null;

  return (
    <Layout
      statusBar={
        <StatusBar
          connectionStatus={connectionStatus}
          hasGpsFix={hasGpsFix}
          dtcs={dtcs}
        />
      }
      gopro={
        <GoProView
          streamWsUrl={STREAM_WS_URL}
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
      gauges={<GaugePanel metrics={metrics} />}
    />
  );
}

export default App;
