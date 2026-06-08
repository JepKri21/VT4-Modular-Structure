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
  const res = await pool.query(
    `UPDATE mes_orders
     SET status = 'CANCELLED', completed_at = NOW()
     WHERE order_id = $1
       AND status = 'PENDING'
     RETURNING order_id, status`,
    [order_id],
  );
  if (res.rowCount === 0) {
    return NextResponse.json(
      { error: "order not pending (already released or finished)" },
      { status: 409 },
    );
  }
  return NextResponse.json({ success: true, order_id });
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
