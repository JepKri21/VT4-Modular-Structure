import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

// Reset a stuck RELEASED order back to PENDING. Used when the controller
// never picked up the WorkOrder — typically because the dispatcher
// published before the controller's persistent MQTT session was
// established. The next dispatch tick republishes it.
export async function POST(
  _req: Request,
  context: { params: Promise<{ order_id: string }> },
) {
  const { order_id } = await context.params;
  const res = await pool.query(
    `UPDATE mes_orders
     SET status = 'PENDING',
         released_at = NULL,
         next_attempt_at = NULL
     WHERE order_id = $1
       AND status = 'RELEASED'
     RETURNING order_id`,
    [order_id],
  );
  if (res.rowCount === 0) {
    return NextResponse.json(
      { error: "order is not RELEASED" },
      { status: 409 },
    );
  }
  return NextResponse.json({ success: true, order_id });
}
