import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

// PROPOSED → APPROVED. Operator commits to the purchase.
export async function POST(
  _req: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const numId = Number(id);
  if (!Number.isFinite(numId)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }
  const res = await pool.query(
    `UPDATE mrp_purchase_orders
     SET status = 'APPROVED', approved_at = NOW()
     WHERE id = $1 AND status = 'PROPOSED'
     RETURNING id`,
    [numId],
  );
  if (res.rowCount === 0) {
    return NextResponse.json(
      { error: "PO is not PROPOSED" },
      { status: 409 },
    );
  }
  return NextResponse.json({ success: true, id: numId });
}
