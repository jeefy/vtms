/**
 * VTMS Settings Panel - E2E Test Suite
 *
 * Tests the settings modal: opening, tab navigation, form editing,
 * save/cancel/reset interactions, and gauge management.
 *
 * Uses Playwright route interception to mock the config API endpoints
 * so tests don't depend on the Express server being available.
 */
import { test, expect } from "./fixtures";
import type { AppConfig } from "../src/types/config";

/** Default config returned by the mocked API */
const mockConfig: AppConfig = {
  mqtt: { url: "ws://localhost:9090", topicPrefix: "lemons/" },
  gopro: { apiUrl: "http://localhost:3001", streamWsUrl: "ws://localhost:9002" },
  sdr: { audioWsUrl: "ws://localhost:9003" },
  gauges: [
    { id: "rpm", topic: "lemons/RPM", label: "RPM", min: 0, max: 8000, unit: "rpm" },
    { id: "speed", topic: "lemons/SPEED", label: "Speed", min: 0, max: 200, unit: "km/h" },
  ],
};

/**
 * Intercept config API calls and return mock data.
 * Captures PUT bodies so tests can assert what was saved.
 */
async function mockConfigApi(page: import("@playwright/test").Page) {
  let savedConfig: AppConfig | null = null;

  await page.route("**/api/config/defaults", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mockConfig),
    });
  });

  await page.route("**/api/config", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(savedConfig ?? mockConfig),
      });
    } else if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON() as AppConfig;
      savedConfig = body;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    } else {
      await route.continue();
    }
  });

  return {
    getSavedConfig: () => savedConfig,
  };
}

test.describe("Settings Panel", () => {
  // ---------- Test: Gear icon opens settings modal ----------
  test("gear icon opens settings modal and close button dismisses it", async ({ dashboardPage }) => {
    await mockConfigApi(dashboardPage);
    // Reload after mocking so useConfig picks up the mock
    await dashboardPage.reload();
    await dashboardPage.waitForSelector(".app-title", { timeout: 10_000 });

    // Settings panel should not be visible initially
    await expect(dashboardPage.locator(".settings-backdrop")).toHaveCount(0);

    // Click gear icon
    await dashboardPage.locator(".settings-gear-btn").click();

    // Settings panel should appear
    await expect(dashboardPage.locator(".settings-panel")).toBeVisible();
    await expect(dashboardPage.locator(".settings-header h2")).toHaveText("Settings");

    // Close via X button
    await dashboardPage.locator(".settings-close-btn").click();
    await expect(dashboardPage.locator(".settings-backdrop")).toHaveCount(0);
  });

  // ---------- Test: Connection tab shows MQTT and GoPro fields ----------
  test("connection tab shows MQTT and GoPro fields with current values", async ({ dashboardPage }) => {
    await mockConfigApi(dashboardPage);
    await dashboardPage.reload();
    await dashboardPage.waitForSelector(".app-title", { timeout: 10_000 });
    await dashboardPage.locator(".settings-gear-btn").click();

    // Connection tab is active by default
    const connectionTab = dashboardPage.locator(".settings-tab", { hasText: "Connection" });
    await expect(connectionTab).toHaveClass(/active/);

    // MQTT fields should display mock values
    const mqttUrlInput = dashboardPage.getByRole("textbox", { name: "Broker URL" });
    await expect(mqttUrlInput).toHaveValue("ws://localhost:9090");

    const topicPrefixInput = dashboardPage.getByRole("textbox", { name: "Topic Prefix" });
    await expect(topicPrefixInput).toHaveValue("lemons/");

    // GoPro fields
    const apiUrlInput = dashboardPage.getByRole("textbox", { name: "API URL" });
    await expect(apiUrlInput).toHaveValue("http://localhost:3001");

    const streamUrlInput = dashboardPage.getByRole("textbox", { name: "Stream WS URL" });
    await expect(streamUrlInput).toHaveValue("ws://localhost:9002");
  });

  // ---------- Test: Switch to gauges tab and see gauge cards ----------
  test("gauges tab shows gauge cards with editable fields", async ({ dashboardPage }) => {
    await mockConfigApi(dashboardPage);
    await dashboardPage.reload();
    await dashboardPage.waitForSelector(".app-title", { timeout: 10_000 });
    await dashboardPage.locator(".settings-gear-btn").click();

    // Switch to Gauges tab
    await dashboardPage.locator(".settings-tab", { hasText: "Gauges" }).click();

    // Should show 2 gauge cards (from mock config)
    const gaugeCards = dashboardPage.locator(".settings-gauge-card");
    await expect(gaugeCards).toHaveCount(2);

    // First gauge should be RPM
    const firstCard = gaugeCards.nth(0);
    await expect(firstCard.locator(".settings-gauge-header strong")).toHaveText("RPM");
  });

  // ---------- Test: Add a new gauge ----------
  test("add gauge button creates a new gauge card", async ({ dashboardPage }) => {
    await mockConfigApi(dashboardPage);
    await dashboardPage.reload();
    await dashboardPage.waitForSelector(".app-title", { timeout: 10_000 });
    await dashboardPage.locator(".settings-gear-btn").click();
    await dashboardPage.locator(".settings-tab", { hasText: "Gauges" }).click();

    // Initially 2 gauges
    await expect(dashboardPage.locator(".settings-gauge-card")).toHaveCount(2);

    // Click add
    await dashboardPage.locator(".settings-add-btn").click();

    // Now 3 gauges
    await expect(dashboardPage.locator(".settings-gauge-card")).toHaveCount(3);

    // New gauge should have default label "New Gauge"
    const lastCard = dashboardPage.locator(".settings-gauge-card").last();
    await expect(lastCard.locator(".settings-gauge-header strong")).toHaveText("New Gauge");
  });

  // ---------- Test: Remove a gauge ----------
  test("remove button deletes a gauge card", async ({ dashboardPage }) => {
    await mockConfigApi(dashboardPage);
    await dashboardPage.reload();
    await dashboardPage.waitForSelector(".app-title", { timeout: 10_000 });
    await dashboardPage.locator(".settings-gear-btn").click();
    await dashboardPage.locator(".settings-tab", { hasText: "Gauges" }).click();

    await expect(dashboardPage.locator(".settings-gauge-card")).toHaveCount(2);

    // Remove the first gauge (RPM)
    await dashboardPage.locator('.settings-gauge-card >> nth=0 >> button[aria-label="Remove gauge"]').click();

    // Only 1 gauge remaining
    await expect(dashboardPage.locator(".settings-gauge-card")).toHaveCount(1);
    // Remaining gauge should be Speed
    await expect(dashboardPage.locator(".settings-gauge-header strong")).toHaveText("Speed");
  });

  // ---------- Test: Cancel discards changes ----------
  test("cancel button closes without saving changes", async ({ dashboardPage }) => {
    const api = await mockConfigApi(dashboardPage);
    await dashboardPage.reload();
    await dashboardPage.waitForSelector(".app-title", { timeout: 10_000 });
    await dashboardPage.locator(".settings-gear-btn").click();

    // Modify MQTT URL
    const mqttUrlInput = dashboardPage.getByRole("textbox", { name: "Broker URL" });
    await mqttUrlInput.fill("ws://changed:1234");

    // Click cancel
    await dashboardPage.locator("button", { hasText: "Cancel" }).click();

    // Panel should be closed
    await expect(dashboardPage.locator(".settings-backdrop")).toHaveCount(0);

    // No save should have been sent
    expect(api.getSavedConfig()).toBeNull();
  });

  // ---------- Test: Save persists changes ----------
  test("save button sends updated config to API", async ({ dashboardPage }) => {
    const api = await mockConfigApi(dashboardPage);
    await dashboardPage.reload();
    await dashboardPage.waitForSelector(".app-title", { timeout: 10_000 });
    await dashboardPage.locator(".settings-gear-btn").click();

    // Modify topic prefix
    const topicPrefixInput = dashboardPage.locator('input[placeholder="lemons/"]');
    await topicPrefixInput.fill("test/");

    // Click save
    await dashboardPage.locator("button", { hasText: "Save" }).click();

    // Wait for modal to close (indicates save succeeded)
    await expect(dashboardPage.locator(".settings-backdrop")).toHaveCount(0, { timeout: 5_000 });

    // Verify the saved config has the updated prefix
    const saved = api.getSavedConfig();
    expect(saved).not.toBeNull();
    expect(saved!.mqtt.topicPrefix).toBe("test/");
  });

  // ---------- Test: Backdrop click closes panel ----------
  test("clicking backdrop closes the settings panel", async ({ dashboardPage }) => {
    await mockConfigApi(dashboardPage);
    await dashboardPage.reload();
    await dashboardPage.waitForSelector(".app-title", { timeout: 10_000 });
    await dashboardPage.locator(".settings-gear-btn").click();

    await expect(dashboardPage.locator(".settings-panel")).toBeVisible();

    // Click the backdrop (not the panel itself)
    await dashboardPage.locator(".settings-backdrop").click({ position: { x: 10, y: 10 } });

    await expect(dashboardPage.locator(".settings-backdrop")).toHaveCount(0);
  });
});
