import { pool } from "@/lib/db";
import { publish, lineTopic } from "@/lib/mqttPublisher";

// Resolve = "the underlying problem is fixed". For most categories this is
// just a UI marker (sets cleared_at). For STUCK_CARGO it has a side effect:
// we publish ClearStuckCargo to MQTT so the Line Controller calls
// OccupancyManager.clear_stuck() on the (resource, actor) pair, freeing
// the actor for new orders and clearing the live production-monitoring
// flag on the next snapshot tick.

export async function POST(req: Request) {
  const { id } = await req.json();

  // Look up the alarm BEFORE updating so we know whether the side effect
  // applies. One round trip; cleared_at column is small.
  const before = await pool.query(
    `SELECT category, resource_id, actor_name
     FROM alarms
     WHERE id = $1`,
    [id],
  );
  const row = before.rows[0];

  await pool.query(
    `UPDATE alarms
     SET cleared_at = NOW()
     WHERE id = $1
       AND cleared_at IS NULL`,
    [id],
  );

  if (
    row?.category === "STUCK_CARGO" &&
    row.resource_id &&
    row.actor_name
  ) {
    try {
      await publish(lineTopic("Controller/ClearStuckCargo"), {
        resource_id: row.resource_id,
        actor_name: row.actor_name,
      });
    } catch (err) {
      // Surface but don't fail the request — the DB row is already
      // marked cleared so the UI stays in sync; the operator can retry
      // if the actor doesn't actually free up.
      console.error("[resolve] MQTT publish failed:", err);
    }
  }

  return Response.json({ success: true });
}
