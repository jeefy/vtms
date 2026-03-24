import { useCallback, useEffect, useRef, useState } from "react";

interface SDRAudioPlayerProps {
  /** WebSocket URL for the audio stream (e.g. "ws://localhost:9003") */
  wsUrl: string;
  /** Whether the SDR session is active */
  isActive: boolean;
}

/** PCM sample rate from the SDR audio WebSocket */
const SAMPLE_RATE = 48_000;

/**
 * Web Audio API player for live PCM audio from the SDR WebSocket.
 *
 * Connects to the audio WebSocket when active, decodes float32 PCM
 * frames, and plays them through a GainNode for volume control.
 * Provides mute/unmute toggle and volume slider.
 */
export function SDRAudioPlayer({ wsUrl, isActive }: SDRAudioPlayerProps) {
  const [muted, setMuted] = useState(true);
  const [volume, setVolume] = useState(0.5);
  const [connected, setConnected] = useState(false);

  const audioCtxRef = useRef<AudioContext | null>(null);
  const gainNodeRef = useRef<GainNode | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const nextTimeRef = useRef(0);

  // Update gain when volume or muted state changes
  useEffect(() => {
    if (gainNodeRef.current) {
      gainNodeRef.current.gain.value = muted ? 0 : volume;
    }
  }, [volume, muted]);

  // Manage WebSocket connection
  useEffect(() => {
    if (!isActive || !wsUrl) {
      return;
    }

    // Lazy-init AudioContext (requires user gesture on some browsers,
    // but we start muted so autoplay policy is satisfied)
    if (!audioCtxRef.current) {
      const ctx = new AudioContext({ sampleRate: SAMPLE_RATE });
      const gain = ctx.createGain();
      gain.gain.value = muted ? 0 : volume;
      gain.connect(ctx.destination);
      audioCtxRef.current = ctx;
      gainNodeRef.current = gain;
    }

    const ctx = audioCtxRef.current;
    const gainNode = gainNodeRef.current!;

    // Reset scheduling timeline
    nextTimeRef.current = 0;

    const ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.addEventListener("open", () => {
      setConnected(true);
      // Resume AudioContext if suspended (autoplay policy)
      if (ctx.state === "suspended") {
        ctx.resume();
      }
    });

    ws.addEventListener("close", () => {
      setConnected(false);
    });

    ws.addEventListener("error", () => {
      setConnected(false);
    });

    ws.addEventListener("message", (event: MessageEvent) => {
      if (!(event.data instanceof ArrayBuffer)) return;

      const float32 = new Float32Array(event.data);
      const numSamples = float32.length;
      if (numSamples === 0) return;

      // Create an AudioBuffer from the PCM data
      const buffer = ctx.createBuffer(1, numSamples, SAMPLE_RATE);
      buffer.getChannelData(0).set(float32);

      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(gainNode);

      // Schedule playback — ensure frames play back-to-back
      const now = ctx.currentTime;
      if (nextTimeRef.current < now) {
        // Fallen behind or first frame — start from now with small buffer
        nextTimeRef.current = now + 0.05;
      }
      source.start(nextTimeRef.current);
      nextTimeRef.current += numSamples / SAMPLE_RATE;
    });

    return () => {
      ws.close();
      wsRef.current = null;
      setConnected(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive, wsUrl]);

  const toggleMute = useCallback(() => {
    // Resume AudioContext on user gesture if needed
    if (audioCtxRef.current?.state === "suspended") {
      audioCtxRef.current.resume();
    }
    setMuted((prev) => !prev);
  }, []);

  const handleVolumeChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const v = parseFloat(e.target.value);
      setVolume(v);
      if (v > 0 && muted) {
        setMuted(false);
      }
    },
    [muted],
  );

  return (
    <div className="sdr-audio-player">
      <button
        className={`sdr-audio-player__mute ${muted ? "sdr-audio-player__mute--muted" : ""}`}
        onClick={toggleMute}
        disabled={!isActive}
        title={muted ? "Unmute audio" : "Mute audio"}
        aria-label={muted ? "Unmute audio" : "Mute audio"}
      >
        {muted ? "Unmute" : "Mute"}
      </button>
      <input
        className="sdr-audio-player__volume"
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={volume}
        onChange={handleVolumeChange}
        disabled={!isActive}
        aria-label="Audio volume"
      />
      <span className="sdr-audio-player__status">
        {connected ? "Live" : "Off"}
      </span>
    </div>
  );
}
