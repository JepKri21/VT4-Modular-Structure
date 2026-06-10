import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

// GET: single-order detail (includes payload so an operator can inspect
// what would be published).
// DELETE: cancel a PENDING order. RELEASED/COMPLETED orders can't be
// cancelled through this endpoint — those need to abort via the line
// controller's recovery path.

export async function GET(
  _req: Request,
  context: { params: Promise<{ order_id: string }> },
) {
  const { order_id } = await context.params;
  const res = await pool.query(
    `SELECT id, order_id, line_id, product_ref, priority, payload, status,
            issued_at, released_at, completed_at
     FROM mes_orders
     WHERE order_id = $1`,
    [order_id],
  );
  if (res.rows.length === 0) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json(res.rows[0]);
}

export async function DELETE(
  _req: Request,
  context: { params: Promise<{ order_id: string }> },
) {
  const { order_id } = await context.params;

  // Fetch the batch_id before cancelling so we can cancel siblings and the webshop order.
  const lookup = await pool.query(
    `SELECT batch_id FROM mes_orders WHERE order_id = $1 AND status = 'PENDING'`,
    [order_id],
  );
  if (lookup.rowCount === 0) {
    return NextResponse.json(
      { error: "order not pending (already released or finished)" },
      { status: 409 },
    );
  }
  const batchId: string | null = lookup.rows[0].batch_id;

  // Cancel every PENDING row in the same batch (handles multi-product orders).
  await pool.query(
    `UPDATE mes_orders
     SET status = 'CANCELLED', completed_at = NOW()
     WHERE batch_id = $1
       AND status = 'PENDING'`,
    [batchId],
  );

  // batch_id is "ORD-<first 8 hex chars of the webshop UUID uppercase>".
  // Use that to find and cancel the matching webshop order so its inventory
  // reservation is released in the same action — no need to cancel separately
  // on the orders page.
  if (batchId) {
    const hexPrefix = batchId.replace(/^ORD-/i, "").toLowerCase();
    if (hexPrefix.length === 8) {
      await pool.query(
        `UPDATE aas_orders
         SET cancelled_at = NOW(), status = 'cancelled',
             cancellation_reason = 'Cancelled from scheduling queue'
         WHERE LEFT(order_id::text, 8) = $1
           AND cancelled_at IS NULL`,
        [hexPrefix],
      );

      // Ask the MES to clean up BaSyx shells (fire-and-forget — non-fatal).
      const batchUuidPrefix = hexPrefix;
      const shellCleanupId = `${batchUuidPrefix}`;
      void fetch(`http://localhost:8000/api/v1/orders/${shellCleanupId}/shells`, {
        method: "DELETE",
      }).catch(() => {});
    }
  }

  return NextResponse.json({ success: true, order_id, batch_id: batchId });
}

// PATCH — change priority on a PENDING row. Body: { priority: number }.
// Priorities are user-facing 1..n, lower = higher priority. We clamp to a
// safe range so the UI can't push absurd values.
export async function PATCH(
  req: Request,
  context: { params: Promise<{ order_id: string }> },
) {
  const { order_id } = await context.params;
  let body: { priority?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const raw = Number(body.priority);
  if (!Number.isFinite(raw)) {
    return NextResponse.json(
      { error: "priority must be a number" },
      { status: 400 },
    );
  }
  const priority = Math.max(1, Math.min(999, Math.round(raw)));
  const res = await pool.query(
    `UPDATE mes_orders
     SET priority = $1
     WHERE order_id = $2
       AND status = 'PENDING'
     RETURNING order_id, priority`,
    [priority, order_id],
  );
  if (res.rowCount === 0) {
    return NextResponse.json(
      { error: "order not pending — priority is fixed once released" },
      { status: 409 },
    );
  }
  return NextResponse.json({ success: true, order_id, priority });
}
