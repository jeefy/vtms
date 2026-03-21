import { type ChildProcess, spawn } from "node:child_process";
import { WebSocketServer, WebSocket } from "ws";
import { GOPRO_BASE_URL } from "./gopro-proxy.js";

const STREAM_WS_PORT = parseInt(
  process.env.STREAM_WS_PORT ?? "9002",
  10,
);

export class StreamManager {
  private wss: WebSocketServer | null = null;
  private ffmpeg: ChildProcess | null = null;
  private backoffMs = 1000;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private running = false;

  /** Create the WebSocket server and listen for clients. */
  init(): void {
    this.wss = new WebSocketServer({ port: STREAM_WS_PORT });
    console.log(`Stream WebSocket server listening on ws://0.0.0.0:${STREAM_WS_PORT}`);

    this.wss.on("connection", (ws) => {
      console.log("Stream client connected");
      ws.on("close", () => console.log("Stream client disconnected"));
    });
  }

  /** Tell the GoPro to start streaming and launch FFmpeg. */
  async startStream(): Promise<void> {
    if (this.running) return;
    this.running = true;
    this.backoffMs = 1000;

    await this.requestGoProStream();
    this.spawnFfmpeg();
  }

  /** Stop streaming: kill FFmpeg, clear timers. */
  stopStream(): void {
    this.running = false;
    this.clearReconnect();

    if (this.ffmpeg) {
      this.ffmpeg.kill("SIGTERM");
      this.ffmpeg = null;
    }
  }

  /** Tear everything down. */
  destroy(): void {
    this.stopStream();
    if (this.wss) {
      this.wss.close();
      this.wss = null;
    }
  }

  // ── Private helpers ──────────────────────────────────

  private async requestGoProStream(): Promise<void> {
    try {
      await fetch(`${GOPRO_BASE_URL}/gopro/camera/stream/start`, {
        signal: AbortSignal.timeout(5000),
      });
      console.log("GoPro stream/start sent");
    } catch (err) {
      console.warn("Failed to send stream/start to GoPro:", String(err));
    }
  }

  private spawnFfmpeg(): void {
    if (!this.running) return;

    console.log("Spawning FFmpeg...");
    const proc = spawn("ffmpeg", [
      "-i", "udp://@0.0.0.0:8554",
      "-f", "mpegts",
      "-codec:v", "mpeg1video",
      "-b:v", "1500k",
      "-r", "30",
      "-s", "640x480",
      "-bf", "0",
      "-q:v", "5",
      "pipe:1",
    ], { stdio: ["ignore", "pipe", "pipe"] });

    proc.stdout!.on("data", (chunk: Buffer) => {
      this.broadcast(chunk);
    });

    proc.stderr!.on("data", (data: Buffer) => {
      // FFmpeg writes progress info to stderr — log sparingly
      const line = data.toString().trim();
      if (line) console.log("[ffmpeg]", line);
    });

    proc.on("close", (code) => {
      console.log(`FFmpeg exited with code ${code}`);
      this.ffmpeg = null;
      if (this.running) {
        this.scheduleReconnect();
      }
    });

    proc.on("error", (err) => {
      console.error("FFmpeg spawn error:", err.message);
      this.ffmpeg = null;
      if (this.running) {
        this.scheduleReconnect();
      }
    });

    this.ffmpeg = proc;
  }

  private broadcast(data: Buffer): void {
    if (!this.wss) return;
    for (const client of this.wss.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(data);
      }
    }
  }

  private scheduleReconnect(): void {
    this.clearReconnect();
    console.log(`Reconnecting FFmpeg in ${this.backoffMs}ms...`);
    this.reconnectTimer = setTimeout(async () => {
      await this.requestGoProStream();
      this.spawnFfmpeg();
      // Exponential backoff capped at 30 s
      this.backoffMs = Math.min(this.backoffMs * 2, 30_000);
    }, this.backoffMs);
  }

  private clearReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}
