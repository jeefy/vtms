import { GOPRO_BASE_URL } from "./gopro-proxy.js";

const KEEP_ALIVE_INTERVAL_MS = 3_000;
const KEEP_ALIVE_TIMEOUT_MS = 2_000;

export class KeepAliveService {
  private _connected = false;
  private timer: ReturnType<typeof setInterval> | null = null;

  /** Whether the last keep-alive ping succeeded. */
  get connected(): boolean {
    return this._connected;
  }

  /** Start sending periodic keep-alive pings. */
  start(): void {
    if (this.timer) return;
    console.log("KeepAlive service started");

    // Fire immediately, then on interval
    this.ping();
    this.timer = setInterval(() => this.ping(), KEEP_ALIVE_INTERVAL_MS);
  }

  /** Stop the keep-alive loop. */
  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    this._connected = false;
    console.log("KeepAlive service stopped");
  }

  private async ping(): Promise<void> {
    try {
      await fetch(`${GOPRO_BASE_URL}/gopro/camera/keep_alive`, {
        signal: AbortSignal.timeout(KEEP_ALIVE_TIMEOUT_MS),
      });
      if (!this._connected) {
        console.log("GoPro connection established");
      }
      this._connected = true;
    } catch {
      if (this._connected) {
        console.warn("GoPro connection lost");
      }
      this._connected = false;
    }
  }
}
