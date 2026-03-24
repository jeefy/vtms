/**
 * SDR Panel - E2E Test Suite
 *
 * Tests the SDR dashboard panel: offline state, signal meter updates,
 * frequency display, transcription log, and control elements.
 *
 * Uses the same Aedes MQTT broker as the dashboard tests.
 */
import { test, expect } from "./fixtures";

test.describe("SDR Panel", () => {
  // ---------- Test 1: SDR panel renders in offline state ----------
  test("SDR panel shows offline state initially", async ({ dashboardPage }) => {
    // SDR panel should be visible
    const sdrPanel = dashboardPage.locator(".sdr-panel");
    await expect(sdrPanel).toBeVisible();

    // Title should be present
    await expect(sdrPanel.locator(".sdr-panel__title")).toHaveText("SDR Radio");

    // Should show offline indicator when MQTT connects but SDR isn't running
    // Wait for MQTT to connect first
    await expect(dashboardPage.locator(".status-bar")).toContainText("MQTT Connected", {
      timeout: 10_000,
    });

    // SDR status defaults to "offline" — panel should show offline message
    await expect(sdrPanel.locator(".sdr-panel__offline")).toBeVisible();
    await expect(sdrPanel.locator(".sdr-panel__offline")).toContainText("SDR Offline");
  });

  // ---------- Test 2: Signal meter updates from MQTT ----------
  test("signal meter updates when signal_power is published", async ({
    dashboardPage,
    mqttClient,
  }) => {
    await expect(dashboardPage.locator(".status-bar")).toContainText("MQTT Connected", {
      timeout: 10_000,
    });

    // Publish SDR state to make it active
    await mqttClient.publishSDRState("status", "recording");
    await dashboardPage.waitForTimeout(300);

    // Publish signal power
    await mqttClient.publishSDRState("signal_power", -25.3);
    await dashboardPage.waitForTimeout(500);

    // Signal meter should show the value
    const signalMeter = dashboardPage.locator(".signal-meter");
    await expect(signalMeter).toBeVisible();
    await expect(signalMeter.locator(".signal-meter__label")).toContainText("-25.3 dB");

    // The meter fill should have a width > 0%
    const fill = signalMeter.locator(".signal-meter__fill");
    await expect(fill).toBeVisible();
    const width = await fill.evaluate((el) => el.style.width);
    expect(parseFloat(width)).toBeGreaterThan(0);
  });

  // ---------- Test 3: Frequency and modulation display ----------
  test("frequency and modulation display from MQTT state", async ({
    dashboardPage,
    mqttClient,
  }) => {
    await expect(dashboardPage.locator(".status-bar")).toContainText("MQTT Connected", {
      timeout: 10_000,
    });

    // Publish frequency and modulation
    await mqttClient.publishSDRState("freq", 146520000);
    await mqttClient.publishSDRState("mod", "fm");
    await mqttClient.publishSDRState("status", "recording");
    await dashboardPage.waitForTimeout(500);

    // Frequency should display as MHz
    const controls = dashboardPage.locator(".sdr-controls");
    await expect(controls.locator(".sdr-controls__freq-value")).toContainText("146.520 MHz");

    // Modulation badge should show FM
    await expect(controls.locator(".sdr-controls__mod")).toHaveText("FM");
  });

  // ---------- Test 4: Squelch threshold marker on signal meter ----------
  test("squelch threshold appears on signal meter", async ({
    dashboardPage,
    mqttClient,
  }) => {
    await expect(dashboardPage.locator(".status-bar")).toContainText("MQTT Connected", {
      timeout: 10_000,
    });

    // Publish squelch threshold
    await mqttClient.publishSDRState("squelch_db", -30);
    await dashboardPage.waitForTimeout(500);

    // Squelch marker should be visible
    const squelchMarker = dashboardPage.locator(".signal-meter__squelch");
    await expect(squelchMarker).toBeVisible();

    // Marker title should show the squelch value
    await expect(squelchMarker).toHaveAttribute("title", "Squelch: -30.0 dB");
  });

  // ---------- Test 5: Transcription log receives entries ----------
  test("transcription log shows entries from MQTT", async ({
    dashboardPage,
    mqttClient,
  }) => {
    await expect(dashboardPage.locator(".status-bar")).toContainText("MQTT Connected", {
      timeout: 10_000,
    });

    const log = dashboardPage.locator(".transcription-log");

    // Initially empty
    await expect(log.locator(".transcription-log__empty")).toContainText("No transcriptions yet");

    // Publish transcription lines
    await mqttClient.publishSDRState("last_transcription", "Tower, this is Alpha Bravo Charlie");
    await dashboardPage.waitForTimeout(500);

    // Empty message should be gone, entry should appear
    await expect(log.locator(".transcription-log__empty")).toHaveCount(0);
    const entries = log.locator(".transcription-log__entry");
    await expect(entries).toHaveCount(1);
    await expect(entries.first()).toContainText("Tower, this is Alpha Bravo Charlie");

    // Publish second transcription
    await mqttClient.publishSDRState("last_transcription", "Roger, Alpha Bravo Charlie, cleared to land");
    await dashboardPage.waitForTimeout(500);

    await expect(entries).toHaveCount(2);
    await expect(entries.nth(1)).toContainText("Roger, Alpha Bravo Charlie, cleared to land");
  });

  // ---------- Test 6: Controls disabled when SDR offline ----------
  test("controls are disabled when SDR is offline", async ({ dashboardPage }) => {
    await expect(dashboardPage.locator(".status-bar")).toContainText("MQTT Connected", {
      timeout: 10_000,
    });

    // SDR is offline by default — sliders and button should be disabled
    const squelchSlider = dashboardPage.locator('.sdr-controls__slider input[type="range"]').first();
    await expect(squelchSlider).toBeDisabled();

    const autotuneBtn = dashboardPage.locator(".sdr-controls__autotune");
    await expect(autotuneBtn).toBeDisabled();

    const muteBtn = dashboardPage.locator(".sdr-audio-player__mute");
    await expect(muteBtn).toBeDisabled();
  });

  // ---------- Test 7: Controls enabled when SDR is recording ----------
  test("controls are enabled when SDR is recording", async ({
    dashboardPage,
    mqttClient,
  }) => {
    await expect(dashboardPage.locator(".status-bar")).toContainText("MQTT Connected", {
      timeout: 10_000,
    });

    // Publish recording status
    await mqttClient.publishSDRState("status", "recording");
    await dashboardPage.waitForTimeout(500);

    // Offline banner should be gone
    await expect(dashboardPage.locator(".sdr-panel__offline")).toHaveCount(0);

    // Sliders and autotune should be enabled
    const squelchSlider = dashboardPage.locator('.sdr-controls__slider input[type="range"]').first();
    await expect(squelchSlider).toBeEnabled();

    const autotuneBtn = dashboardPage.locator(".sdr-controls__autotune");
    await expect(autotuneBtn).toBeEnabled();

    const muteBtn = dashboardPage.locator(".sdr-audio-player__mute");
    await expect(muteBtn).toBeEnabled();
  });

  // ---------- Test 8: Full SDR state stream ----------
  test("full SDR state renders all components correctly", async ({
    dashboardPage,
    mqttClient,
  }) => {
    await expect(dashboardPage.locator(".status-bar")).toContainText("MQTT Connected", {
      timeout: 10_000,
    });

    // Publish a complete SDR state
    await mqttClient.publishSDRState("status", "recording");
    await mqttClient.publishSDRState("freq", 462562500);
    await mqttClient.publishSDRState("mod", "fm");
    await mqttClient.publishSDRState("squelch_db", -25);
    await mqttClient.publishSDRState("gain", 40);
    await mqttClient.publishSDRState("ppm", 2);
    await mqttClient.publishSDRState("signal_power", -18.7);
    await mqttClient.publishSDRState("last_transcription", "Base, all clear on channel 1");
    await dashboardPage.waitForTimeout(1000);

    // Verify frequency
    await expect(dashboardPage.locator(".sdr-controls__freq-value")).toContainText("462.563 MHz");

    // Verify signal meter
    await expect(dashboardPage.locator(".signal-meter__label")).toContainText("-18.7 dB");

    // Verify transcription
    await expect(dashboardPage.locator(".transcription-log__entry")).toHaveCount(1);
    await expect(dashboardPage.locator(".transcription-log__entry").first()).toContainText(
      "Base, all clear on channel 1",
    );

    // No offline banner
    await expect(dashboardPage.locator(".sdr-panel__offline")).toHaveCount(0);
  });
});
