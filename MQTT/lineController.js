const mqtt = require("mqtt");
const { Client } = require("pg");

const client = mqtt.connect("mqtt://localhost:1883");

const CMD_TOPIC = "smartlab/line1/drillstation1/command";
const STATUS_TOPIC = "smartlab/line1/drillstation1/status";

const db = new Client({
  user: "postgres",
  host: "localhost",
  database: "thesis_mes",
  password: "password",
  port: 5432,
});

db.connect()
  .then(() => console.log("Connected to PostgreSQL 🐘"))
  .catch((err) => console.error("DB connection error", err));

/* ===========================
   MQTT CONNECT
=========================== */

client.on("connect", () => {
  console.log("Line Controller connected to MQTT Broker 🏭");

  // Subscribe én gang
  client.subscribe(STATUS_TOPIC);

  // Send command én gang
  client.publish(
    CMD_TOPIC,
    JSON.stringify({
      workOrderId: "WO-01",
      skill: "Drilling",
      parameters: {
        DrillDepth: 10,
        RotationalSpeed: 1800,
        Feed: 150,
      },
    }),
  );
});

/* ===========================
   MQTT MESSAGE HANDLER
=========================== */

client.on("message", async (topic, message) => {
  if (topic !== STATUS_TOPIC) return;

  const payload = JSON.parse(message.toString());
  console.log("Status update:", payload);

  if (payload.status === "COMPLETE" && payload.duration) {
    const endTime = new Date();
    const durationMs = Number(payload.duration) * 1000;

    if (!isNaN(durationMs)) {
      const startTime = new Date(endTime.getTime() - durationMs);

      await db.query(
        `INSERT INTO execution_log 
       (asset_id, work_order_id, start_time, end_time, status)
       VALUES ($1, $2, $3, $4, $5)`,
        ["Line-1", payload.workOrderId, startTime, endTime, "COMPLETE"],
      );

      console.log("Execution logged in DB ✅");
    }
  }
});
