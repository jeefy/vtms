/**
 * Playwright global setup.
 *
 * Starts:
 * 1. An Aedes MQTT broker with WebSocket transport on a random port
 * 2. A Vite dev server with VITE_MQTT_URL pointing to the broker
 *
 * Both ports are written to process.env so tests and config can use them.
 */
import { Aedes } from "aedes";
import { createServer } from "net";
import { createServer as createHttpServer } from "http";
import ws from "websocket-stream";
import { exec } from "child_process";
import { writeFileSync } from "fs";
import { join } from "path";

/** Find a free port by binding to 0 */
function getFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.listen(0, () => {
      const addr = srv.address();
      if (addr && typeof addr !== "string") {
        const port = addr.port;
        srv.close(() => resolve(port));
      } else {
        reject(new Error("Could not get port"));
      }
    });
  });
}

/** Wait for the Vite dev server to respond */
async function waitForVite(url: string, timeoutMs = 30_000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`Vite dev server did not start within ${timeoutMs}ms`);
}

export default async function globalSetup() {
  // 1. Start Aedes MQTT broker with WebSocket transport
  const mqttWsPort = await getFreePort();
  const aedesInstance = await Aedes.createBroker();
  const httpServer = createHttpServer();

  // websocket-stream pipes WebSocket connections into Aedes
  ws.createServer({ server: httpServer }, aedesInstance.handle);

  await new Promise<void>((resolve) => {
    httpServer.listen(mqttWsPort, () => resolve());
  });

  const mqttUrl = `ws://localhost:${mqttWsPort}`;
  console.log(`[global-setup] Aedes MQTT broker listening on ${mqttUrl}`);

  // 2. Start Vite dev server
  const vitePort = await getFreePort();
  const viteProcess = exec(
    `npx vite --port ${vitePort} --strictPort`,
    {
      cwd: process.cwd(),
      env: {
        ...process.env,
        VITE_MQTT_URL: mqttUrl,
      },
    }
  );

  // Log vite output for debugging
  viteProcess.stdout?.on("data", (d) => {
    if (process.env.DEBUG) console.log(`[vite] ${d}`);
  });
  viteProcess.stderr?.on("data", (d) => {
    if (process.env.DEBUG) console.error(`[vite] ${d}`);
  });

  const baseUrl = `http://localhost:${vitePort}`;
  await waitForVite(baseUrl);
  console.log(`[global-setup] Vite dev server ready at ${baseUrl}`);

  // Write port info to a temp file so tests can read it
  // (process.env doesn't persist across Playwright's process boundary)
  const envData = {
    VTMS_MQTT_URL: mqttUrl,
    VTMS_MQTT_PORT: mqttWsPort,
    VTMS_BASE_URL: baseUrl,
    VTMS_VITE_PORT: vitePort,
    VTMS_VITE_PID: viteProcess.pid,
  };
  writeFileSync(
    join(process.cwd(), "e2e/.env.test.json"),
    JSON.stringify(envData, null, 2)
  );

  // Store cleanup references globally (same process for teardown)
  (globalThis as any).__vtms_cleanup = {
    aedesInstance,
    httpServer,
    viteProcess,
  };
}
