import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

// Manual retry of an ABORTED order. Bumps attempt_count and flips back
// to PENDING (no backoff — operator pressed the button knowing what
// they're doing). The dispatcher's automatic retry uses the same
// mechanism with a delay; this just shortcuts that for "I fixed the
// issue, try again now".
export async function POST(
  _req: Request,
  context: { params: Promise<{ order_id: string }> },
) {
  const { order_id } = await context.params;
  const res = await pool.query(
    `UPDATE mes_orders
     SET status = 'PENDING',
         attempt_count = attempt_count + 1,
         released_at = NULL,
         completed_at = NULL,
         next_attempt_at = NULL
     WHERE order_id = $1
       AND status IN ('ABORTED', 'CANCELLED')
     RETURNING order_id, attempt_count`,
    [order_id],
  );
  if (res.rowCount === 0) {
    return NextResponse.json(
      { error: "order is not in a retryable state" },
      { status: 409 },
    );
  }
  return NextResponse.json({
    success: true,
    order_id,
    attempt_count: res.rows[0].attempt_count,
  });
}
