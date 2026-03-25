#!/usr/bin/env tsx
/**
 * Mock GoPro Server for VTMS.
 *
 * Mimics the GoPro Open API HTTP endpoints so the VTMS server proxy
 * can be pointed at this instead of a real camera.
 *
 * Usage:
 *   npx tsx scripts/mock-gopro.ts                       # HTTP on 8080, WS on 9002
 *   npx tsx scripts/mock-gopro.ts --port 8080           # custom HTTP port
 *   npx tsx scripts/mock-gopro.ts --ws-port 9002        # custom WS video port
 */
import express from "express";
import { WebSocketServer } from "ws";
import { spawn, type ChildProcess } from "child_process";

// ---------- CLI args ----------
const args = process.argv.slice(2);
function getArg(name: string, fallback: string): string {
  const idx = args.indexOf(`--${name}`);
  return idx >= 0 && args[idx + 1] ? args[idx + 1] : fallback;
}

const HTTP_PORT = parseInt(getArg("port", "8080"), 10);
const WS_PORT = parseInt(getArg("ws-port", "9002"), 10);

// ---------- Simulated camera state ----------
interface CameraState {
  recording: boolean;
  presetGroup: number; // 1000=video, 1001=photo, 1002=timelapse
  batteryPercent: number;
  storageMB: number;
}

const camera: CameraState = {
  recording: false,
  presetGroup: 1000,
  batteryPercent: 85,
  storageMB: 51200, // ~50 GB
};

// Battery drains ~1%/min, storage decreases when recording
setInterval(() => {
  camera.batteryPercent = Math.max(0, camera.batteryPercent - 0.017); // ~1%/min
  if (camera.recording) {
    camera.storageMB = Math.max(0, camera.storageMB - 5); // ~300MB/min at 60fps
  }
}, 1000);

// ---------- HTTP server (GoPro API) ----------
const app = express();

// GET /gopro/camera/state
app.get("/gopro/camera/state", (_req, res) => {
  res.json({
    status: {
      "2": Math.round(camera.batteryPercent), // battery %
      "8": camera.recording ? 1 : 0, // recording flag
      "43": camera.presetGroup, // active preset group
      "54": Math.round(camera.storageMB), // remaining storage MB
    },
  });
});

// GET /gopro/camera/shutter/:action
app.get("/gopro/camera/shutter/:action", (req, res) => {
  const action = req.params.action;
  if (action === "start") {
    camera.recording = true;
    console.log("[mock-gopro] Recording started");
  } else if (action === "stop") {
    camera.recording = false;
    console.log("[mock-gopro] Recording stopped");
  } else {
    res.status(400).json({ error: "Invalid action" });
    return;
  }
  res.json({});
});

// GET /gopro/camera/presets/set_group?id=N
app.get("/gopro/camera/presets/set_group", (req, res) => {
  const id = parseInt(req.query.id as string, 10);
  if (isNaN(id)) {
    res.status(400).json({ error: "Missing or invalid id" });
    return;
  }
  camera.presetGroup = id;
  console.log(`[mock-gopro] Preset group set to ${id}`);
  res.json({});
});

// GET /gopro/camera/stream/:action
app.get("/gopro/camera/stream/:action", (req, res) => {
  console.log(`[mock-gopro] Stream ${req.params.action}`);
  res.json({});
});

// GET /gopro/camera/keep_alive
app.get("/gopro/camera/keep_alive", (_req, res) => {
  res.json({});
});

// ---------- WebSocket video stream (MPEG-TS test pattern) ----------
let ffmpegProcess: ChildProcess | null = null;

function startVideoStream(wss: WebSocketServer): void {
  // Generate SMPTE color bars with timestamp overlay via ffmpeg
  ffmpegProcess = spawn(
    "ffmpeg",
    [
      "-re", // real-time output
      "-f",
      "lavfi",
      "-i",
      "smptebars=size=320x240:rate=25",
      "-vf",
      "drawtext=text='%{localtime}':fontsize=20:fontcolor=white:x=10:y=10",
      "-c:v",
      "mpeg1video",
      "-b:v",
      "500k",
      "-f",
      "mpegts",
      "-", // output to stdout
    ],
    { stdio: ["ignore", "pipe", "pipe"] },
  );

  ffmpegProcess.stdout!.on("data", (chunk: Buffer) => {
    for (const client of wss.clients) {
      if (client.readyState === 1) {
        // OPEN
        client.send(chunk);
      }
    }
  });

  ffmpegProcess.stderr!.on("data", (_data: Buffer) => {
    // ffmpeg logs to stderr; suppress per-frame progress lines
  });

  ffmpegProcess.on("error", (err) => {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      console.warn("[mock-gopro] ffmpeg not found -- video stream disabled");
      console.warn("[mock-gopro] Install ffmpeg to enable test pattern video");
    } else {
      console.error("[mock-gopro] ffmpeg error:", err.message);
    }
    ffmpegProcess = null;
  });

  ffmpegProcess.on("close", (code) => {
    if (code !== 0 && code !== null) {
      console.warn(`[mock-gopro] ffmpeg exited with code ${code}`);
    }
    ffmpegProcess = null;
  });
}

// ---------- Main ----------
async function main() {
  // Start HTTP server
  await new Promise<void>((resolve) => {
    app.listen(HTTP_PORT, "0.0.0.0", () => {
      console.log(
        `[mock-gopro] HTTP API listening on http://0.0.0.0:${HTTP_PORT}`,
      );
      console.log(`[mock-gopro] Point VTMS server at GOPRO_IP=127.0.0.1`);
      resolve();
    });
  });

  // Start WebSocket video stream server
  const wss = new WebSocketServer({ port: WS_PORT });
  console.log(`[mock-gopro] Video stream WS on ws://0.0.0.0:${WS_PORT}`);

  wss.on("connection", () => {
    console.log(
      `[mock-gopro] Video client connected (${wss.clients.size} total)`,
    );
  });

  // Try to start ffmpeg video source
  startVideoStream(wss);

  // Status display
  setInterval(() => {
    const bat = Math.round(camera.batteryPercent);
    const stor = (camera.storageMB / 1024).toFixed(1);
    const rec = camera.recording ? "REC" : "IDLE";
    const preset =
      camera.presetGroup === 1000
        ? "Video"
        : camera.presetGroup === 1001
          ? "Photo"
          : "Timelapse";
    const clients = wss.clients.size;
    process.stdout.write(
      `\r[mock-gopro] ${rec} | ${preset} | Bat: ${bat}% | Storage: ${stor}GB | WS clients: ${clients}   `,
    );
  }, 2000);

  // Graceful shutdown
  const shutdown = () => {
    console.log("\n[mock-gopro] Shutting down...");
    if (ffmpegProcess) ffmpegProcess.kill("SIGTERM");
    wss.close();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((err) => {
  console.error("[mock-gopro] Fatal error:", err.message);
  process.exit(1);
});
