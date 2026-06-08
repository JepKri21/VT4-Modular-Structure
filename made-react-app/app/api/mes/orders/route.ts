import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

// List MES queue items. PENDING first (oldest waiting top), then
// RELEASED (in flight), then everything else newest-first. Capped at
// `limit` (default 100); the queue dashboard polls this every few s.
export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const limit = Math.min(500, Math.max(1, Number(searchParams.get("limit") ?? "100")));

  const sql = `
    SELECT
      id, order_id, line_id, product_ref, priority, status,
      issued_at, released_at, completed_at,
      batch_id, batch_index, batch_total, attempt_count, next_attempt_at
    FROM mes_orders
    ORDER BY
      CASE status
        WHEN 'PENDING'   THEN 0
        WHEN 'RELEASED'  THEN 1
        WHEN 'COMPLETED' THEN 2
        WHEN 'ABORTED'   THEN 3
        ELSE 4
      END,
      CASE WHEN status = 'PENDING' THEN priority ELSE 0 END ASC,
      issued_at DESC
    LIMIT $1
  `;
  const result = await pool.query(sql, [limit]);

  // Summary counts for the dashboard header.
  const counts = await pool.query(
    `SELECT
       SUM(CASE WHEN status = 'PENDING'   THEN 1 ELSE 0 END)::int AS pending,
       SUM(CASE WHEN status = 'RELEASED'  THEN 1 ELSE 0 END)::int AS released,
       SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END)::int AS completed,
       SUM(CASE WHEN status = 'ABORTED'   THEN 1 ELSE 0 END)::int AS aborted,
       SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END)::int AS cancelled
     FROM mes_orders`,
  );

  return NextResponse.json({
    summary: counts.rows[0] ?? {
      pending: 0,
      released: 0,
      completed: 0,
      aborted: 0,
      cancelled: 0,
    },
    orders: result.rows,
  });
}
