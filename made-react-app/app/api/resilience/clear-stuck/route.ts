import { publish, lineTopic } from "@/lib/mqttPublisher";

// POST body:
//   { resource_id: "Transport_4e812e6c-...", actor_name: "Shuttle1" }
//
// Publishes to AAUSmartLab/<line>/Controller/ClearStuckCargo. The Line
// Controller (main.py on_clear_stuck) clears the actor's STUCK flag and its
// cargo ledger, returning it to the available pool. Use only after the
// physical part has actually been removed from the actor.

export async function POST(req: Request) {
  let body: { resource_id?: string; actor_name?: string };
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "invalid JSON" }, { status: 400 });
  }

  const { resource_id, actor_name } = body;
  if (!resource_id || !actor_name) {
    return Response.json(
      { error: "resource_id and actor_name are required" },
      { status: 400 },
    );
  }

  const topic = lineTopic("Controller/ClearStuckCargo");
  const payload = { resource_id, actor_name };

  try {
    await publish(topic, payload);
  } catch (err) {
    console.error("[clear-stuck] MQTT publish failed:", err);
    return Response.json({ error: "MQTT publish failed" }, { status: 502 });
  }

  return Response.json({ success: true, topic, payload });
}
