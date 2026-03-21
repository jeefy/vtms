import { useEffect, useRef, useCallback, useState } from "react";
import mqtt, { type MqttClient } from "mqtt";
import type { MqttConnectionStatus } from "../types/telemetry";
import { mqttConfig } from "../config/gauges";

type MessageHandler = (topic: string, payload: string) => void;

/**
 * Hook that manages MQTT WebSocket connection and message dispatch.
 *
 * Subscribes to `lemons/#` and forwards every message to `onMessage`.
 * Handles automatic reconnection and exposes connection status.
 */
export function useMqtt(onMessage: MessageHandler) {
  const [status, setStatus] = useState<MqttConnectionStatus>("disconnected");
  const clientRef = useRef<MqttClient | null>(null);
  const onMessageRef = useRef(onMessage);

  // Keep callback ref up to date without re-triggering effect
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const connect = useCallback(() => {
    // Don't reconnect if already connected
    if (clientRef.current?.connected) return;

    setStatus("connecting");

    const client = mqtt.connect(mqttConfig.url, {
      reconnectPeriod: mqttConfig.reconnectInterval,
      keepalive: 60,
      clean: true,
      clientId: `vtms-web-${Math.random().toString(16).slice(2, 8)}`,
    });

    client.on("connect", () => {
      setStatus("connected");
      client.subscribe(`${mqttConfig.topicPrefix}#`, { qos: 0 });
    });

    client.on("message", (_topic, payload) => {
      onMessageRef.current(_topic, payload.toString());
    });

    client.on("error", () => {
      setStatus("error");
    });

    client.on("close", () => {
      setStatus("disconnected");
    });

    client.on("reconnect", () => {
      setStatus("connecting");
    });

    clientRef.current = client;
  }, []);

  useEffect(() => {
    connect();

    return () => {
      if (clientRef.current) {
        clientRef.current.end(true);
        clientRef.current = null;
      }
    };
  }, [connect]);

  return { status };
}
