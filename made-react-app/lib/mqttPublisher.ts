// One shared MQTT client used by Next.js API routes to publish operator
// actions (e.g. ClearStuckCargo) into the broker.
//
// The connection is lazily created on first publish and kept open for the
// lifetime of the server process. Reconnects are handled by the mqtt
// library automatically.

import mqtt, { MqttClient } from "mqtt";

const MQTT_URL = process.env.MQTT_URL ?? "mqtt://localhost:1883";
const LINE_ID = process.env.LINE_ID ?? "ProductionLine1";

let client: MqttClient | null = null;
let connecting: Promise<MqttClient> | null = null;

async function getClient(): Promise<MqttClient> {
  if (client && client.connected) return client;
  if (connecting) return connecting;

  connecting = new Promise<MqttClient>((resolve, reject) => {
    const c = mqtt.connect(MQTT_URL, {
      clientId: `mes-dashboard-${Math.random().toString(16).slice(2)}`,
      reconnectPeriod: 2000,
    });
    c.once("connect", () => {
      client = c;
      connecting = null;
      console.log(`[mqtt] connected to ${MQTT_URL}`);
      resolve(c);
    });
    c.once("error", (err) => {
      connecting = null;
      reject(err);
    });
  });

  return connecting;
}

export async function publish(topic: string, payload: object): Promise<void> {
  const c = await getClient();
  return new Promise((resolve, reject) => {
    c.publish(topic, JSON.stringify(payload), { qos: 0 }, (err) =>
      err ? reject(err) : resolve(),
    );
  });
}

export function lineTopic(suffix: string): string {
  return `AAUSmartLab/${LINE_ID}/${suffix}`;
}
