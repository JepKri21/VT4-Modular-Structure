const mqtt = require("mqtt");
const client = mqtt.connect("mqtt://localhost:1883");

const CMD_TOPIC = "smartlab/line1/drillstation1/command";
const STATUS_TOPIC = "smartlab/line1/drillstation1/status";
const EVENT_TOPIC = "smartlab/line1/drillstation1/event";

client.on("connect", () => {
  console.log("Drilling 1 Connected to MQTT Broker 🏭");
  client.subscribe(CMD_TOPIC);
});

client.on("message", (topic, message) => {
  const payload = JSON.parse(message.toString());
  console.log("Recieved command: ", payload);

  // Publishing RUNNING state to topic:
  client.publish(
    STATUS_TOPIC,
    JSON.stringify({
      state: "RUNNING", // RUNNING, IDLE, COMPLETE ???
      workOrderId: payload.workOrderId,
    }),
  );

  // Simulating a Process being executed:
  setTimeout(() => {
    client.publish(
      STATUS_TOPIC,
      JSON.stringify({
        status: "COMPLETE",
        workOrderId: payload.workOrderId,
        duration: 5.0,
      }),
    );
  }, 5000);
});
