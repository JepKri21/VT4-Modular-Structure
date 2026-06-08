import { NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { publish, lineTopic } from "@/lib/mqttPublisher";

// APPROVED → RECEIVED. The destination station receives a
// ReceiveShipmentMessage on its `<resource>/ReceiveShipment` topic and
// appends fresh instances to its inventory.
//
// Body (all optional):
//   { deliver_to?: string, inventory_name?: string }
//
// `deliver_to` lets the operator pick the receiving station at receive
// time when the PO doesn't have one set. Persists on the PO row so the
// next receive of the same PO knows where it went.

export async function POST(
  req: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const numId = Number(id);
  if (!Number.isFinite(numId)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }

  let body: Record<string, unknown> = {};
  try {
    body = await req.json();
  } catch {
    /* body optional */
  }

  // Fetch + lock the row so two parallel receives can't double-deliver.
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const before = await client.query(
      `SELECT id, status, component_type_iri, quantity, deliver_to
       FROM mrp_purchase_orders
       WHERE id = $1
       FOR UPDATE`,
      [numId],
    );
    if (before.rowCount === 0) {
      await client.query("ROLLBACK");
      return NextResponse.json({ error: "PO not found" }, { status: 404 });
    }
    const po = before.rows[0];
    if (po.status !== "APPROVED") {
      await client.query("ROLLBACK");
      return NextResponse.json(
        { error: "PO must be APPROVED before receiving" },
        { status: 409 },
      );
    }

    const deliverTo = String(body.deliver_to ?? po.deliver_to ?? "");
    if (!deliverTo) {
      await client.query("ROLLBACK");
      return NextResponse.json(
        { error: "deliver_to is required (no default set on the PO)" },
        { status: 400 },
      );
    }
    const inventoryName = body.inventory_name
      ? String(body.inventory_name)
      : null;

    await client.query(
      `UPDATE mrp_purchase_orders
       SET status = 'RECEIVED', received_at = NOW(), deliver_to = $2
       WHERE id = $1`,
      [numId, deliverTo],
    );
    await client.query("COMMIT");

    // Publish AFTER the commit so a failed publish doesn't leave the DB
    // saying "received" while the station never heard of it. Reverse —
    // if MQTT publish fails, surface a 502 and the operator can replay
    // by marking the row received again (we'll be idempotent on the
    // station side via the PO id, eventually).
    try {
      await publish(lineTopic(`${deliverTo}/ReceiveShipment`), {
        timestamp: new Date().toISOString(),
        component_type_iri: po.component_type_iri,
        quantity: po.quantity,
        purchase_order_id: po.id,
        inventory_name: inventoryName,
      });
    } catch (err) {
      console.error("[receive] MQTT publish failed:", err);
      return NextResponse.json(
        {
          success: true,
          warning: "PO marked RECEIVED but MQTT publish failed",
          detail: String(err),
        },
        { status: 502 },
      );
    }

    return NextResponse.json({ success: true, id: numId, deliver_to: deliverTo });
  } catch (err) {
    await client.query("ROLLBACK");
    return NextResponse.json(
      { error: "receive failed", detail: String(err) },
      { status: 500 },
    );
  } finally {
    client.release();
  }
}
