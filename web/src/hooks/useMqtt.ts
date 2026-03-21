import { useEffect, useRef, useCallback, useState } from "react";
import mqtt, { type MqttClient } from "mqtt";
import type { MqttConnectionStatus } from "../types/telemetry";

type MessageHandler = (topic: string, payload: string) => void;

const RECONNECT_INTERVAL = 5000;

export function useMqtt(
  brokerUrl: string,
  topicPrefix: string,
  onMessage: MessageHandler,
) {
  const [status, setStatus] = useState<MqttConnectionStatus>("disconnected");
  const clientRef = useRef<MqttClient | null>(null);
  const onMessageRef = useRef(onMessage);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const connect = useCallback(() => {
    if (clientRef.current?.connected) return;

    setStatus("connecting");

    const client = mqtt.connect(brokerUrl, {
      reconnectPeriod: RECONNECT_INTERVAL,
      keepalive: 60,
      clean: true,
      clientId: `vtms-web-${Math.random().toString(16).slice(2, 8)}`,
    });

    client.on("connect", () => {
      setStatus("connected");
      client.subscribe(`${topicPrefix}#`, { qos: 0 });
    });

    client.on("message", (_topic, payload) => {
      onMessageRef.current(_topic, payload.toString());
    });

    client.on("error", () => setStatus("error"));
    client.on("close", () => setStatus("disconnected"));
    client.on("reconnect", () => setStatus("connecting"));

    clientRef.current = client;
  }, [brokerUrl, topicPrefix]);

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
