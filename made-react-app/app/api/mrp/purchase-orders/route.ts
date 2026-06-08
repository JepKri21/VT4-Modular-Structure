import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

// Purchase orders proposed/approved by the MRP run. MRP-1 just exposes
// the read endpoint — POs are empty until MRP-2 (the MRP run itself)
// or MRP-3 (manual restock workflow) populate them.

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const status = searchParams.get("status"); // optional filter
  const params: unknown[] = [];
  let where = "";
  if (status) {
    where = "WHERE po.status = $1";
    params.push(status.toUpperCase());
  }
  const sql = `
    SELECT
      po.id, po.component_type_iri, po.quantity, po.strategy, po.status,
      po.unit_cost, po.total_cost, po.needed_by,
      po.created_at, po.approved_at, po.received_at,
      po.deliver_to, po.notes,
      m.name AS material_name, m.category AS material_category
    FROM mrp_purchase_orders po
    LEFT JOIN mrp_materials m USING (component_type_iri)
    ${where}
    ORDER BY po.created_at DESC
    LIMIT 500;
  `;
  const result = await pool.query(sql, params);
  return NextResponse.json({ rows: result.rows });
}
