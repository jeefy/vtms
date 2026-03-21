/**
 * Playwright test fixtures for VTMS e2e tests.
 *
 * Provides:
 * - `mqttClient`: A connected MqttTestClient for publishing test messages
 * - `dashboardPage`: A Page navigated to the dashboard with MQTT connected
 */
import { test as base, type Page } from "@playwright/test";
import { MqttTestClient } from "./helpers/mqtt-client";
import { readFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

/** Read environment written by global-setup */
function readTestEnv(): { VTMS_MQTT_URL: string; VTMS_BASE_URL: string } {
  // Try multiple paths since __dirname may vary
  const candidates = [
    join(dirname(fileURLToPath(import.meta.url)), ".env.test.json"),
    join(process.cwd(), "e2e", ".env.test.json"),
  ];

  for (const p of candidates) {
    try {
      const raw = readFileSync(p, "utf-8");
      return JSON.parse(raw);
    } catch {
      // try next
    }
  }

  return {
    VTMS_MQTT_URL: "ws://localhost:9001",
    VTMS_BASE_URL: "http://localhost:5173",
  };
}

const testEnv = readTestEnv();

type VtmsFixtures = {
  /** Connected MQTT test publisher */
  mqttClient: MqttTestClient;
  /** Page with dashboard loaded */
  dashboardPage: Page;
};

export const test = base.extend<VtmsFixtures>({
  mqttClient: async ({}, use) => {
    const client = new MqttTestClient(testEnv.VTMS_MQTT_URL);
    await client.connect();
    await use(client);
    await client.disconnect();
  },

  dashboardPage: async ({ page }, use) => {
    // Navigate to the app using the dynamically assigned port
    await page.goto(testEnv.VTMS_BASE_URL);
    // Wait for the app to render (status bar title is always present)
    await page.waitForSelector(".app-title", { timeout: 10_000 });
    await use(page);
  },
});

export { expect } from "@playwright/test";
