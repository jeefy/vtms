import express from "express";
import { goProRouter, GOPRO_IP } from "./gopro-proxy.js";
import { StreamManager } from "./stream-manager.js";
import { KeepAliveService } from "./keep-alive.js";

const app = express();
const PORT = parseInt(process.env.PORT ?? "3001", 10);
const HOST = process.env.HOST ?? "0.0.0.0";

// ── Services ──────────────────────────────────────────

const streamManager = new StreamManager();
streamManager.init();

const keepAlive = new KeepAliveService();
keepAlive.start();

// ── Routes ────────────────────────────────────────────

app.get("/api/health", (_req, res) => {
  res.json({ status: "ok" });
});

app.use("/api/gopro", goProRouter);

// GoPro connection status
app.get("/api/gopro/connection", (_req, res) => {
  res.json({ connected: keepAlive.connected, ip: GOPRO_IP });
});

// Stream control
app.post("/api/stream/start", async (_req, res) => {
  try {
    await streamManager.startStream();
    res.json({ status: "started" });
  } catch (err) {
    res.status(500).json({ error: "Failed to start stream", detail: String(err) });
  }
});

app.post("/api/stream/stop", (_req, res) => {
  streamManager.stopStream();
  res.json({ status: "stopped" });
});

// ── Start server ──────────────────────────────────────

app.listen(PORT, HOST, () => {
  console.log(`VTMS server listening on http://${HOST}:${PORT}`);
});

// ── Graceful shutdown ─────────────────────────────────

process.on("SIGTERM", () => {
  console.log("SIGTERM received, shutting down...");
  keepAlive.stop();
  streamManager.destroy();
  process.exit(0);
});

process.on("SIGINT", () => {
  console.log("SIGINT received, shutting down...");
  keepAlive.stop();
  streamManager.destroy();
  process.exit(0);
});
