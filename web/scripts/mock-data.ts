#!/usr/bin/env tsx
/**
 * Mock Data Generator for VTMS.
 *
 * Simulates a drive session by publishing realistic telemetry data
 * to an MQTT broker over WebSocket. Useful for development, demos,
 * and as a data source importable by tests.
 *
 * Usage:
 *   npx tsx scripts/mock-data.ts                         # defaults to ws://localhost:9001
 *   npx tsx scripts/mock-data.ts --url ws://host:port    # custom broker
 *   npx tsx scripts/mock-data.ts --rate 200              # publish every 200ms
 *   npx tsx scripts/mock-data.ts --duration 60           # run for 60 seconds
 */
import mqtt from "mqtt";

// ---------- CLI args ----------
const args = process.argv.slice(2);
function getArg(name: string, fallback: string): string {
  const idx = args.indexOf(`--${name}`);
  return idx >= 0 && args[idx + 1] ? args[idx + 1] : fallback;
}

const BROKER_URL = getArg("url", process.env.VITE_MQTT_URL ?? "ws://192.168.50.24:9001");
const RATE_MS = parseInt(getArg("rate", "500"), 10);
const DURATION_S = parseInt(getArg("duration", "0"), 10); // 0 = infinite
const TOPIC_PREFIX = "lemons/";

// ---------- Drive simulation state ----------
interface DriveState {
  phase: "idle" | "accelerating" | "cruising" | "decelerating" | "braking";
  rpm: number;
  speed: number; // km/h
  throttle: number; // %
  engineLoad: number; // %
  coolantTemp: number; // °C
  oilTemp: number; // °C
  gpsLat: number;
  gpsLon: number;
  gpsSpeed: number; // m/s
  gpsAlt: number; // meters
  heading: number; // degrees
  tick: number;
}

/** Generate realistic initial state */
function initialState(): DriveState {
  return {
    phase: "idle",
    rpm: 800,
    speed: 0,
    throttle: 0,
    engineLoad: 15,
    coolantTemp: 45,
    oilTemp: 35,
    // Start near Sonoma Raceway (common for Lemons)
    gpsLat: 38.161,
    gpsLon: -122.455,
    gpsSpeed: 0,
    gpsAlt: 5,
    heading: 45,
    tick: 0,
  };
}

/** Phase durations in ticks */
const PHASE_TICKS: Record<DriveState["phase"], number> = {
  idle: 10,
  accelerating: 20,
  cruising: 30,
  decelerating: 15,
  braking: 8,
};

/** Advance the drive simulation one tick */
export function advanceDriveState(state: DriveState): DriveState {
  const s = { ...state, tick: state.tick + 1 };

  // Phase transitions
  const ticksInPhase = PHASE_TICKS[s.phase];
  if (s.tick % ticksInPhase === 0) {
    const phases: DriveState["phase"][] = ["idle", "accelerating", "cruising", "decelerating", "braking"];
    const currentIdx = phases.indexOf(s.phase);
    s.phase = phases[(currentIdx + 1) % phases.length];
  }

  // Engine simulation
  const jitter = () => (Math.random() - 0.5) * 2;

  switch (s.phase) {
    case "idle":
      s.rpm = clamp(800 + jitter() * 50, 600, 1000);
      s.speed = clamp(s.speed - 2, 0, 200);
      s.throttle = clamp(5 + jitter() * 3, 0, 15);
      s.engineLoad = clamp(15 + jitter() * 5, 10, 25);
      break;
    case "accelerating":
      s.rpm = clamp(s.rpm + 150 + jitter() * 50, 800, 7500);
      s.speed = clamp(s.speed + 5 + jitter() * 2, 0, 180);
      s.throttle = clamp(60 + jitter() * 20, 30, 100);
      s.engineLoad = clamp(70 + jitter() * 15, 40, 100);
      break;
    case "cruising":
      s.rpm = clamp(3200 + jitter() * 200, 2800, 3800);
      s.speed = clamp(s.speed + jitter() * 3, s.speed - 5, s.speed + 5);
      s.throttle = clamp(35 + jitter() * 10, 20, 55);
      s.engineLoad = clamp(45 + jitter() * 10, 30, 60);
      break;
    case "decelerating":
      s.rpm = clamp(s.rpm - 100 + jitter() * 30, 800, 5000);
      s.speed = clamp(s.speed - 4 + jitter(), 20, 200);
      s.throttle = clamp(10 + jitter() * 5, 0, 25);
      s.engineLoad = clamp(25 + jitter() * 8, 10, 40);
      break;
    case "braking":
      s.rpm = clamp(s.rpm - 200 + jitter() * 40, 800, 4000);
      s.speed = clamp(s.speed - 8 + jitter(), 0, 200);
      s.throttle = clamp(jitter() * 3, 0, 10);
      s.engineLoad = clamp(12 + jitter() * 4, 5, 25);
      break;
  }

  // Temperature simulation (slowly rises to operating temp, then fluctuates)
  const targetCoolant = s.phase === "idle" ? 85 : 95;
  s.coolantTemp = clamp(s.coolantTemp + (targetCoolant - s.coolantTemp) * 0.02 + jitter() * 0.5, 40, 120);

  const targetOil = s.phase === "idle" ? 80 : 110;
  s.oilTemp = clamp(s.oilTemp + (targetOil - s.oilTemp) * 0.015 + jitter() * 0.3, 30, 140);

  // GPS simulation - move along heading with some curve
  s.heading = (s.heading + jitter() * 5 + 360) % 360;
  const speedMs = (s.speed / 3.6); // km/h -> m/s
  const distMeters = speedMs * (RATE_MS / 1000);
  const distDegLat = distMeters / 111_320;
  const distDegLon = distMeters / (111_320 * Math.cos(s.gpsLat * Math.PI / 180));

  s.gpsLat += distDegLat * Math.cos(s.heading * Math.PI / 180);
  s.gpsLon += distDegLon * Math.sin(s.heading * Math.PI / 180);
  s.gpsSpeed = speedMs;
  s.gpsAlt = clamp(s.gpsAlt + jitter() * 0.5, 0, 50);

  return s;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

/** Get all MQTT messages for the current state */
export function stateToMessages(state: DriveState): Array<{ topic: string; payload: string }> {
  return [
    { topic: `${TOPIC_PREFIX}RPM`, payload: `${Math.round(state.rpm)} revolutions_per_minute` },
    { topic: `${TOPIC_PREFIX}SPEED`, payload: `${Math.round(state.speed)} kph` },
    { topic: `${TOPIC_PREFIX}COOLANT_TEMP`, payload: `${state.coolantTemp.toFixed(1)} degC` },
    { topic: `${TOPIC_PREFIX}OIL_TEMP`, payload: `${state.oilTemp.toFixed(1)} degC` },
    { topic: `${TOPIC_PREFIX}THROTTLE_POS`, payload: `${Math.round(state.throttle)} percent` },
    { topic: `${TOPIC_PREFIX}ENGINE_LOAD`, payload: `${Math.round(state.engineLoad)} percent` },
    { topic: `${TOPIC_PREFIX}gps/pos`, payload: `${state.gpsLat.toFixed(6)},${state.gpsLon.toFixed(6)}` },
    { topic: `${TOPIC_PREFIX}gps/speed`, payload: `${state.gpsSpeed.toFixed(2)}` },
    { topic: `${TOPIC_PREFIX}gps/altitude`, payload: `${state.gpsAlt.toFixed(1)}` },
  ];
}

// ---------- Main: standalone execution ----------
async function main() {
  console.log(`Connecting to MQTT broker at ${BROKER_URL}...`);
  console.log(`Publish rate: ${RATE_MS}ms | Duration: ${DURATION_S > 0 ? DURATION_S + "s" : "infinite"}`);

  const client = mqtt.connect(BROKER_URL, {
    clientId: `vtms-mock-${Math.random().toString(16).slice(2, 8)}`,
    clean: true,
  });

  await new Promise<void>((resolve, reject) => {
    client.on("connect", () => {
      console.log("Connected to broker. Starting drive simulation...");
      resolve();
    });
    client.on("error", reject);
    setTimeout(() => reject(new Error("Connection timeout")), 10_000);
  });

  let state = initialState();
  let messageCount = 0;
  const startTime = Date.now();

  const interval = setInterval(() => {
    // Check duration limit
    if (DURATION_S > 0 && (Date.now() - startTime) / 1000 >= DURATION_S) {
      console.log(`\nDuration limit reached (${DURATION_S}s). Stopping.`);
      clearInterval(interval);
      client.end();
      return;
    }

    state = advanceDriveState(state);
    const messages = stateToMessages(state);

    for (const msg of messages) {
      client.publish(msg.topic, msg.payload);
    }

    messageCount += messages.length;
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    process.stdout.write(
      `\r[${elapsed}s] Phase: ${state.phase.padEnd(13)} | RPM: ${Math.round(state.rpm).toString().padStart(5)} | Speed: ${Math.round(state.speed).toString().padStart(3)} km/h | Messages: ${messageCount}`
    );
  }, RATE_MS);

  // Graceful shutdown
  process.on("SIGINT", () => {
    console.log("\n\nStopping mock data generator...");
    clearInterval(interval);
    client.end();
  });

  process.on("SIGTERM", () => {
    clearInterval(interval);
    client.end();
  });
}

// Only run main when executed directly (not imported)
const isMainModule = process.argv[1]?.includes("mock-data");
if (isMainModule) {
  main().catch((err) => {
    console.error("Fatal error:", err.message);
    process.exit(1);
  });
}
