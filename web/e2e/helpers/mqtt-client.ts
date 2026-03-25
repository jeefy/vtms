/**
 * MQTT test client helper.
 *
 * Connects to the Aedes broker started by global-setup and provides
 * helpers for publishing test messages and waiting for delivery.
 */
import mqtt, { type MqttClient } from "mqtt";

export class MqttTestClient {
  private client: MqttClient | null = null;
  private url: string;

  constructor(url?: string) {
    this.url = url ?? process.env.VTMS_MQTT_URL ?? "ws://localhost:9090";
  }

  /** Connect to the broker. Resolves when connected. */
  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.client = mqtt.connect(this.url, {
        clientId: `test-publisher-${Math.random().toString(16).slice(2, 8)}`,
        clean: true,
      });

      this.client.on("connect", () => resolve());
      this.client.on("error", (err) => reject(err));

      // Timeout after 5 seconds
      setTimeout(() => reject(new Error("MQTT test client connect timeout")), 5000);
    });
  }

  /** Publish a message and wait for it to be delivered. */
  async publish(topic: string, payload: string): Promise<void> {
    if (!this.client) throw new Error("Not connected");

    return new Promise((resolve, reject) => {
      this.client!.publish(topic, payload, { qos: 0 }, (err) => {
        if (err) reject(err);
        else resolve();
      });
    });
  }

  /**
   * Publish an OBD-style metric value.
   * Format: "3500 revolutions_per_minute" -> topic "lemons/RPM"
   */
  async publishMetric(key: string, value: number, unit: string): Promise<void> {
    return this.publish(`lemons/${key}`, `${value} ${unit}`);
  }

  /** Publish a GPS position (lat,lon on lemons/gps/pos). */
  async publishGpsPos(lat: number, lon: number): Promise<void> {
    return this.publish("lemons/gps/pos", `${lat},${lon}`);
  }

  /** Publish a GPS field (e.g. speed, altitude). */
  async publishGpsField(field: string, value: number): Promise<void> {
    return this.publish(`lemons/gps/${field}`, String(value));
  }

  /** Publish a DTC (Diagnostic Trouble Code). */
  async publishDtc(code: string, description: string): Promise<void> {
    return this.publish(`lemons/DTC/${code}`, description);
  }

  /** Publish an SDR state value (e.g. freq, status, signal_power). */
  async publishSDRState(key: string, value: string | number): Promise<void> {
    return this.publish(`lemons/sdr/state/${key}`, String(value));
  }

  /** Disconnect from the broker. */
  async disconnect(): Promise<void> {
    if (!this.client) return;
    return new Promise((resolve) => {
      this.client!.end(false, {}, () => resolve());
      this.client = null;
    });
  }
}
