import { publish, lineTopic } from "@/lib/mqttPublisher";

// POST body:
//   { resource_id: "Drilling_12345678",
//     command: "DROP_ACKS" | "NEXT_INCOMPLETE" | "GO_SILENT",
//     count?: number,       // DROP_ACKS only
//     duration_s?: number } // GO_SILENT only
//
// Publishes to AAUSmartLab/<line>/<resource_id>/TestInjection.
// Stations that opt in via `enable_fault_injection()` pick it up.

type Command = "DROP_ACKS" | "NEXT_INCOMPLETE" | "GO_SILENT";
const ALLOWED: Command[] = ["DROP_ACKS", "NEXT_INCOMPLETE", "GO_SILENT"];

export async function POST(req: Request) {
  let body: {
    resource_id?: string;
    command?: Command;
    count?: number;
    duration_s?: number;
  };
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "invalid JSON" }, { status: 400 });
  }

  const { resource_id, command, count, duration_s } = body;
  if (!resource_id || !command || !ALLOWED.includes(command)) {
    return Response.json(
      { error: "resource_id and a valid command are required" },
      { status: 400 },
    );
  }

  const topic = lineTopic(`${resource_id}/TestInjection`);
  const payload: Record<string, unknown> = {
    timestamp: new Date().toISOString(),
    command,
  };
  if (command === "DROP_ACKS") payload.count = count ?? 1;
  if (command === "GO_SILENT") payload.duration_s = duration_s ?? 60;

  try {
    await publish(topic, payload);
  } catch (err) {
    console.error("[inject] MQTT publish failed:", err);
    return Response.json(
      { error: "MQTT publish failed" },
      { status: 502 },
    );
  }

  return Response.json({ success: true, topic, payload });
}
