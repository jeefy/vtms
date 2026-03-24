import type { SDRState, TranscriptionLine, SDRControlAction } from "../types/sdr";
import type { MqttConnectionStatus } from "../types/telemetry";
import { SignalMeter } from "./SignalMeter";
import { SDRControls } from "./SDRControls";
import { TranscriptionLog } from "./TranscriptionLog";
import { SDRAudioPlayer } from "./SDRAudioPlayer";

interface SDRPanelProps {
  /** SDR state from useSDR hook */
  state: SDRState;
  /** Transcription lines from useSDR hook */
  transcriptions: TranscriptionLine[];
  /** MQTT connection status */
  connectionStatus: MqttConnectionStatus;
  /** Publish a control command */
  onPublish: (action: SDRControlAction, value: string | number | Record<string, unknown>) => void;
  /** WebSocket URL for audio streaming */
  audioWsUrl: string;
}

/**
 * SDR panel container that assembles SignalMeter, SDRControls,
 * TranscriptionLog, and SDRAudioPlayer.
 *
 * Shows "SDR Offline" overlay when the session is not active.
 */
export function SDRPanel({
  state,
  transcriptions,
  connectionStatus,
  onPublish,
  audioWsUrl,
}: SDRPanelProps) {
  const isActive = state.status === "recording" && connectionStatus === "connected";

  return (
    <div className="sdr-panel">
      <h2 className="sdr-panel__title">SDR Radio</h2>

      {!isActive && (
        <div className="sdr-panel__offline">
          {connectionStatus !== "connected" ? "MQTT Disconnected" : "SDR Offline"}
        </div>
      )}

      <SignalMeter
        signalPower={state.signal_power}
        squelchDb={state.squelch_db}
      />

      <SDRControls
        freq={state.freq}
        mod={state.mod}
        squelchDb={state.squelch_db}
        gain={state.gain}
        ppm={state.ppm}
        isActive={isActive}
        onPublish={onPublish}
      />

      <SDRAudioPlayer wsUrl={audioWsUrl} isActive={isActive} />

      <TranscriptionLog lines={transcriptions} />
    </div>
  );
}
