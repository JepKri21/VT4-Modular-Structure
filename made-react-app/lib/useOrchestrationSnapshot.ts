"use client";

import { useEffect, useState } from "react";
import mqtt, { type MqttClient } from "mqtt";
import {
  OrchestrationSnapshot,
  SNAPSHOT_TOPIC,
} from "./orchestration-snapshot";

// Override via NEXT_PUBLIC_MQTT_WS_URL in .env.local if your broker uses a
// different port or host. The default assumes the dev-machine convention of
// listener 9001 + protocol websockets in mosquitto.conf.
const DEFAULT_BROKER_WS =
  process.env.NEXT_PUBLIC_MQTT_WS_URL ?? "ws://localhost:9001";

export type SnapshotStatus = "connecting" | "connected" | "error";

/**
 * Subscribe to the Line Controller orchestration snapshot via MQTT-over-WS.
 * Returns the latest snapshot (or null until the first message), plus
 * connection status for the UI to render a banner.
 *
 * The snapshot topic is retained on the broker, so this hook receives the
 * current picture immediately on connect — no warm-up wait.
 */
export function useOrchestrationSnapshot(
  brokerUrl: string = DEFAULT_BROKER_WS,
) {
  const [snapshot, setSnapshot] = useState<OrchestrationSnapshot | null>(null);
  const [status, setStatus] = useState<SnapshotStatus>("connecting");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let client: MqttClient | null = null;
    try {
      client = mqtt.connect(brokerUrl, {
        reconnectPeriod: 2000,
        connectTimeout: 5000,
      });
    } catch (e) {
      setStatus("error");
      setError(String(e));
      return;
    }

    client.on("connect", () => {
      setStatus("connected");
      setError(null);
      client?.subscribe(SNAPSHOT_TOPIC, { qos: 0 }, (err) => {
        if (err) {
          setStatus("error");
          setError(`subscribe failed: ${err.message}`);
        }
      });
    });

    client.on("message", (topic, payload) => {
      if (topic !== SNAPSHOT_TOPIC) return;
      try {
        const parsed = JSON.parse(payload.toString()) as OrchestrationSnapshot;
        setSnapshot(parsed);
      } catch (e) {
        console.error("[snapshot] malformed JSON:", e);
      }
    });

    client.on("error", (err) => {
      setStatus("error");
      setError(err.message);
    });

    client.on("close", () => {
      setStatus((s) => (s === "error" ? s : "connecting"));
    });

    return () => {
      client?.end(true);
    };
  }, [brokerUrl]);

  return { snapshot, status, error };
}
