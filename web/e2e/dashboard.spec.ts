/**
 * VTMS Live Dashboard - E2E Test Suite
 *
 * Tests the full user experience: MQTT connection, gauge rendering,
 * GPS map updates, DTC alerts, and responsive layout.
 *
 * Uses a real in-process Aedes MQTT broker started by global-setup.
 */
import { test, expect } from "./fixtures";

test.describe("VTMS Live Dashboard", () => {
  // ---------- Test 1: App loads with initial state ----------
  test("app loads with connecting/disconnected state initially", async ({ dashboardPage }) => {
    // Title should be visible
    await expect(dashboardPage.locator(".app-title")).toHaveText("VTMS Live");

    // GPS should show "No GPS" initially
    await expect(dashboardPage.locator(".status-bar")).toContainText("No GPS");

    // All gauge cells should be rendered
    const gaugeCells = dashboardPage.locator(".gauge-cell");
    await expect(gaugeCells).toHaveCount(6); // 6 gauges configured
  });

  // ---------- Test 2: MQTT connection indicator turns green ----------
  test("MQTT connection status shows connected", async ({ dashboardPage, mqttClient }) => {
    // The app should connect to the Aedes broker and show "MQTT Connected"
    // Wait for the MQTT connection to establish (may take a moment)
    await expect(dashboardPage.locator(".status-bar")).toContainText("MQTT Connected", {
      timeout: 10_000,
    });

    // The connection indicator dot should be green (#4ade80)
    const dot = dashboardPage.locator(".status-item .status-dot").first();
    await expect(dot).toHaveCSS("background-color", "rgb(74, 222, 128)"); // #4ade80
  });

  // ---------- Test 3: Gauge values update from OBD metrics ----------
  test("gauge values update when metrics are published", async ({ dashboardPage, mqttClient }) => {
    // Wait for MQTT to connect
    await expect(dashboardPage.locator(".status-bar")).toContainText("MQTT Connected", {
      timeout: 10_000,
    });

    // Publish RPM value in OBD format
    await mqttClient.publishMetric("RPM", 3500, "revolutions_per_minute");

    // Wait a beat for the message to propagate through broker -> browser
    await dashboardPage.waitForTimeout(500);

    // The gauge panel should show the RPM value
    // RadialGauge renders the numeric value in a text element
    await expect(dashboardPage.locator(".gauge-panel")).toContainText("3500");

    // Publish speed
    await mqttClient.publishMetric("SPEED", 85, "kph");
    await dashboardPage.waitForTimeout(500);
    await expect(dashboardPage.locator(".gauge-panel")).toContainText("85");
  });

  // ---------- Test 4: Gauge value clamping and NaN handling ----------
  test("gauges handle edge values correctly", async ({ dashboardPage, mqttClient }) => {
    await expect(dashboardPage.locator(".status-bar")).toContainText("MQTT Connected", {
      timeout: 10_000,
    });

    // Publish a value above max (RPM max is 8000) - RadialGauge clamps to max
    await mqttClient.publishMetric("RPM", 9500, "revolutions_per_minute");
    await dashboardPage.waitForTimeout(500);
    // The gauge clamps the display to the max value (8000)
    await expect(dashboardPage.locator(".gauge-panel")).toContainText("8000");

    // Publish a non-numeric value (should result in "--" display)
    await mqttClient.publish("lemons/COOLANT_TEMP", "NOT_A_NUMBER");
    await dashboardPage.waitForTimeout(500);
    // NaN should be handled gracefully - gauge shows "--" and remains visible
    const coolantGauge = dashboardPage.locator(".gauge-cell").nth(2); // Coolant is 3rd gauge
    await expect(coolantGauge).toBeVisible();
    await expect(coolantGauge).toContainText("--");
  });

  // ---------- Test 5: GPS position updates map marker and fix indicator ----------
  test("GPS position updates map and shows fix indicator", async ({ dashboardPage, mqttClient }) => {
    await expect(dashboardPage.locator(".status-bar")).toContainText("MQTT Connected", {
      timeout: 10_000,
    });

    // Initially no GPS fix
    await expect(dashboardPage.locator(".status-bar")).toContainText("No GPS");

    // Publish GPS position
    await mqttClient.publishGpsPos(37.7749, -122.4194);
    await dashboardPage.waitForTimeout(1000);

    // GPS fix indicator should appear
    await expect(dashboardPage.locator(".status-bar")).toContainText("GPS Fix");

    // Map overlay should show coordinates
    await expect(dashboardPage.locator(".map-overlay")).toContainText("37.774900");
    await expect(dashboardPage.locator(".map-overlay")).toContainText("-122.419400");

    // Leaflet marker should be visible on the map
    const marker = dashboardPage.locator(".leaflet-marker-icon");
    await expect(marker).toBeVisible();
  });

  // ---------- Test 6: GPS trail polyline from position sequence ----------
  test("GPS trail renders polyline from multiple positions", async ({ dashboardPage, mqttClient }) => {
    await expect(dashboardPage.locator(".status-bar")).toContainText("MQTT Connected", {
      timeout: 10_000,
    });

    // Publish a sequence of GPS positions to form a trail
    const positions: [number, number][] = [
      [37.7749, -122.4194],
      [37.7750, -122.4190],
      [37.7751, -122.4186],
      [37.7752, -122.4182],
    ];

    for (const [lat, lon] of positions) {
      await mqttClient.publishGpsPos(lat, lon);
      await dashboardPage.waitForTimeout(200);
    }

    // Wait for trail to render
    await dashboardPage.waitForTimeout(500);

    // Leaflet polyline should be rendered (SVG path element inside map)
    const polyline = dashboardPage.locator(".leaflet-overlay-pane path");
    await expect(polyline).toBeVisible();
  });

  // ---------- Test 7: DTC alerts appear in status bar ----------
  test("DTC alerts appear in status bar", async ({ dashboardPage, mqttClient }) => {
    await expect(dashboardPage.locator(".status-bar")).toContainText("MQTT Connected", {
      timeout: 10_000,
    });

    // No DTCs initially
    const dtcAlert = dashboardPage.locator(".dtc-alert");
    await expect(dtcAlert).toHaveCount(0);

    // Publish a DTC
    await mqttClient.publishDtc("P0301", "Cylinder 1 Misfire Detected");
    await dashboardPage.waitForTimeout(500);

    // DTC should appear in status bar
    await expect(dashboardPage.locator(".status-bar")).toContainText("1 DTC");
    await expect(dashboardPage.locator(".status-bar")).toContainText("P0301");

    // Publish a second DTC
    await mqttClient.publishDtc("P0420", "Catalyst System Efficiency Below Threshold");
    await dashboardPage.waitForTimeout(500);

    // Should show 2 DTCs
    await expect(dashboardPage.locator(".status-bar")).toContainText("2 DTCs");
    await expect(dashboardPage.locator(".status-bar")).toContainText("P0420");
  });

  // ---------- Test 8: Multiple metrics streaming simultaneously ----------
  test("multiple metrics stream and update simultaneously", async ({ dashboardPage, mqttClient }) => {
    await expect(dashboardPage.locator(".status-bar")).toContainText("MQTT Connected", {
      timeout: 10_000,
    });

    // Publish all 6 metrics in quick succession
    await mqttClient.publishMetric("RPM", 4200, "revolutions_per_minute");
    await mqttClient.publishMetric("SPEED", 120, "kph");
    await mqttClient.publishMetric("COOLANT_TEMP", 92, "degC");
    await mqttClient.publishMetric("OIL_TEMP", 105, "degC");
    await mqttClient.publishMetric("THROTTLE_POS", 75, "percent");
    await mqttClient.publishMetric("ENGINE_LOAD", 68, "percent");

    // Wait for all messages to propagate
    await dashboardPage.waitForTimeout(1000);

    // All values should be displayed in gauges
    const gaugePanel = dashboardPage.locator(".gauge-panel");
    await expect(gaugePanel).toContainText("4200");
    await expect(gaugePanel).toContainText("120");
    await expect(gaugePanel).toContainText("92");
    await expect(gaugePanel).toContainText("105");
    await expect(gaugePanel).toContainText("75");
    await expect(gaugePanel).toContainText("68");
  });

  // ---------- Test 9: GPS speed and altitude in overlay ----------
  test("GPS speed and altitude display in map overlay", async ({ dashboardPage, mqttClient }) => {
    await expect(dashboardPage.locator(".status-bar")).toContainText("MQTT Connected", {
      timeout: 10_000,
    });

    // Publish position first (overlay only shows when hasPosition)
    await mqttClient.publishGpsPos(37.7749, -122.4194);
    await dashboardPage.waitForTimeout(500);

    // Publish speed (in m/s, displayed as km/h: 25 m/s * 3.6 = 90.0 km/h)
    await mqttClient.publishGpsField("speed", 25);
    await dashboardPage.waitForTimeout(500);

    // Speed should appear in overlay as km/h
    await expect(dashboardPage.locator(".map-overlay")).toContainText("90.0 km/h");

    // Publish altitude
    await mqttClient.publishGpsField("altitude", 42);
    await dashboardPage.waitForTimeout(500);

    // Altitude should appear in overlay
    await expect(dashboardPage.locator(".map-overlay")).toContainText("42m");
  });

  // ---------- Test 10: Responsive layout at mobile viewport ----------
  test("responsive layout at mobile viewport", async ({ dashboardPage }) => {
    // Resize to mobile viewport
    await dashboardPage.setViewportSize({ width: 375, height: 667 });
    await dashboardPage.waitForTimeout(500);

    // At mobile width (<768px), .status-bar-center (with .app-title) is hidden via CSS
    // but the status bar itself, gauges, and map should still render
    await expect(dashboardPage.locator(".status-bar")).toBeVisible();
    await expect(dashboardPage.locator(".gauge-panel")).toBeVisible();
    await expect(dashboardPage.locator(".map-container")).toBeVisible();

    // At 375px (<480px), gauge grid switches to 2 columns but all 6 cells are still rendered
    const gaugeCells = dashboardPage.locator(".gauge-cell");
    await expect(gaugeCells).toHaveCount(6);

    // MQTT status items should still be visible in the status bar
    await expect(dashboardPage.locator(".status-bar-left")).toBeVisible();
  });
});
