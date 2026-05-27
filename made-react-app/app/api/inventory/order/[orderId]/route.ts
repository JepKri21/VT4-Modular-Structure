import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { MIGRATE_ORDERS_SQL } from "@/lib/inventory";

async function ensureMigrations() {
  for (const sql of MIGRATE_ORDERS_SQL) {
    await pool.query(sql);
  }
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ orderId: string }> }
) {
  await ensureMigrations();

  const { orderId } = await params;
  const res = await pool.query(
    `SELECT order_id, status, cancelled_at, cancellation_reason
     FROM aas_orders WHERE order_id = $1`,
    [orderId]
  );

  if (res.rows.length === 0) {
    return NextResponse.json({ error: "Order not found" }, { status: 404 });
  }

  const row = res.rows[0];
  return NextResponse.json({
    orderId: row.order_id,
    status: row.status,
    cancelledAt: row.cancelled_at ?? null,
    cancellationReason: row.cancellation_reason ?? null,
  });
}
