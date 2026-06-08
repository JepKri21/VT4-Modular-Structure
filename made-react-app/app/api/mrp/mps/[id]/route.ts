import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

export async function DELETE(
  _req: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const numId = Number(id);
  if (!Number.isFinite(numId)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }
  const res = await pool.query(`DELETE FROM mrp_mps_entries WHERE id = $1`, [numId]);
  if (res.rowCount === 0) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json({ success: true });
}
