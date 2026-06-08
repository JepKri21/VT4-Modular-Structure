import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

// Master Production Schedule. Weekly target quantities per finished
// product. POST upserts on (week_start, finished_product_type_iri) so
// editing an existing target replaces the value rather than duplicating.

export async function GET() {
  const sql = `
    SELECT
      m.id,
      m.week_start,
      m.finished_product_type_iri,
      m.quantity_target,
      m.notes,
      f.name AS product_name,
      f.kind AS product_kind
    FROM mrp_mps_entries m
    LEFT JOIN mrp_materials f
      ON f.component_type_iri = m.finished_product_type_iri
    ORDER BY m.week_start DESC, f.name NULLS LAST;
  `;
  const res = await pool.query(sql);
  return NextResponse.json({ rows: res.rows });
}

// POST body: { week_start: "YYYY-MM-DD", finished_product_type_iri, quantity_target, notes? }
export async function POST(req: Request) {
  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const weekStart = String(body.week_start ?? "");
  const iri = String(body.finished_product_type_iri ?? "");
  const qty = Math.max(0, Math.round(Number(body.quantity_target ?? 0)));
  if (!weekStart || !iri) {
    return NextResponse.json(
      { error: "week_start and finished_product_type_iri are required" },
      { status: 400 },
    );
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(weekStart)) {
    return NextResponse.json(
      { error: "week_start must be YYYY-MM-DD" },
      { status: 400 },
    );
  }
  const notes = body.notes ? String(body.notes) : null;

  const sql = `
    INSERT INTO mrp_mps_entries
      (week_start, finished_product_type_iri, quantity_target, notes)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (week_start, finished_product_type_iri)
    DO UPDATE SET
      quantity_target = EXCLUDED.quantity_target,
      notes = EXCLUDED.notes
    RETURNING id
  `;
  const res = await pool.query(sql, [weekStart, iri, qty, notes]);
  return NextResponse.json({ success: true, id: res.rows[0].id });
}
