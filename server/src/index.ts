import { existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import express from "express";
import { goProRouter, GOPRO_IP } from "./gopro-proxy.js";
import { StreamManager } from "./stream-manager.js";
import { KeepAliveService } from "./keep-alive.js";
import { loadConfig, saveConfig, getDefaultConfig } from "./config-store.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

const app = express();
const PORT = parseInt(process.env.PORT ?? "3001", 10);
const HOST = process.env.HOST ?? "0.0.0.0";

// ── Services (initialized after listen) ───────────────

const streamManager = new StreamManager();
const keepAlive = new KeepAliveService();

// ── CORS (allow Vite dev server) ──────────────────────

const ALLOWED_ORIGINS = new Set([
  `http://localhost:${PORT}`,
  `http://localhost:5173`, // Vite dev
]);

app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (origin && ALLOWED_ORIGINS.has(origin)) {
    res.header("Access-Control-Allow-Origin", origin);
    res.header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS");
    res.header("Access-Control-Allow-Headers", "Content-Type");
  }
  if (req.method === "OPTIONS") {
    res.sendStatus(204);
    return;
  }
  next();
});

app.use(express.json());

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

// Config API
app.get("/api/config", async (_req, res) => {
  try {
    const config = await loadConfig();
    res.json(config);
  } catch (err) {
    res.status(500).json({ error: "Failed to load config", detail: String(err) });
  }
});

app.put("/api/config", async (req, res) => {
  try {
    await saveConfig(req.body);
    const config = await loadConfig();
    res.json(config);
  } catch (err) {
    res.status(400).json({ error: "Invalid config", detail: String(err) });
  }
});

app.get("/api/config/defaults", (_req, res) => {
  res.json(getDefaultConfig());
});

// ── Static frontend (production) ─────────────────────
// In Docker, web/dist is copied to ../public relative to server dist.
// Serve it if the directory exists; skip in dev (Vite handles it).

const publicDir = join(__dirname, "..", "public");
if (existsSync(publicDir)) {
  app.use(express.static(publicDir));
  // SPA catch-all: serve index.html for any non-API route
  app.get("/{*splat}", (_req, res) => {
    res.sendFile(join(publicDir, "index.html"));
  });
}

// ── Start server ──────────────────────────────────────

app.listen(PORT, HOST, () => {
  console.log(`VTMS server listening on http://${HOST}:${PORT}`);
  streamManager.init();
  keepAlive.start();
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

process.on("unhandledRejection", (reason) => {
  console.error("Unhandled rejection:", reason);
});

process.on("uncaughtException", (err) => {
  console.error("Uncaught exception:", err);
  keepAlive.stop();
  streamManager.destroy();
  process.exit(1);
});
