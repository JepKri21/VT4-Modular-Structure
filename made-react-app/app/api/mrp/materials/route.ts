import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

// Materials catalog. GET returns everything; the MRP page renders it as
// an editable table. Strategies are validated here so the dropdown can't
// push junk values.

const ALLOWED_STRATEGIES = ["LOT_FOR_LOT", "JIT"] as const;
type Strategy = (typeof ALLOWED_STRATEGIES)[number];

// Auto-classify a material from its IRI shape — mirrors what the bridge
// does on auto-seed, so a row manually added through the UI behaves the
// same as one harvested from an InventoryLevel.
function classifyKind(iri: string): "RAW" | "INTERMEDIATE" | "FINISHED" {
  if (iri.includes("/Shells/Product/")) return "FINISHED";
  if (iri.includes("/Shells/Assembly/")) return "INTERMEDIATE";
  return "RAW";
}

function nameFromIri(iri: string): { name: string; category: string | null } {
  const parts = iri.split("/").filter(Boolean);
  if (parts.length >= 2) {
    return { name: parts[parts.length - 1], category: parts[parts.length - 2] };
  }
  return { name: iri, category: null };
}

// POST: create a catalog entry for an IRI that hasn't been observed yet.
// Used to register intermediates (BottomCoverPCB, BottomCoverPCBFuse) that
// the line produces but never holds in any station's inventory, so the
// bridge never auto-seeds them. Idempotent via ON CONFLICT.
export async function POST(req: Request) {
  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const iri = String(body.component_type_iri ?? "").trim();
  if (!iri) {
    return NextResponse.json(
      { error: "component_type_iri is required" },
      { status: 400 },
    );
  }
  const { name: derivedName, category: derivedCategory } = nameFromIri(iri);
  const name = body.name ? String(body.name) : derivedName;
  const category = body.category ? String(body.category) : derivedCategory;
  const kind = body.kind
    ? String(body.kind).toUpperCase()
    : classifyKind(iri);

  const sql = `
    INSERT INTO mrp_materials (component_type_iri, name, category, kind)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (component_type_iri) DO NOTHING
    RETURNING component_type_iri
  `;
  const res = await pool.query(sql, [iri, name, category, kind]);
  return NextResponse.json({
    success: true,
    created: (res.rowCount ?? 0) > 0,
    component_type_iri: iri,
    kind,
  });
}

export async function GET() {
  const sql = `
    SELECT
      component_type_iri, name, category,
      lead_time_days, reorder_strategy, reorder_point, reorder_quantity,
      unit_cost, created_at, updated_at
    FROM mrp_materials
    ORDER BY category NULLS LAST, name;
  `;
  const result = await pool.query(sql);
  return NextResponse.json({ rows: result.rows });
}

// PATCH: edit catalog entries. Body shape:
//   { component_type_iri, lead_time_days?, reorder_strategy?,
//     reorder_point?, reorder_quantity?, unit_cost? }
export async function PATCH(req: Request) {
  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  const typeIri = String(body.component_type_iri ?? "");
  if (!typeIri) {
    return NextResponse.json(
      { error: "component_type_iri is required" },
      { status: 400 },
    );
  }

  const updates: string[] = [];
  const values: unknown[] = [];

  const intField = (key: string, max: number) => {
    if (body[key] === undefined) return;
    const v = Math.max(0, Math.min(max, Math.round(Number(body[key]))));
    if (!Number.isFinite(v)) return;
    updates.push(`${key} = $${values.length + 1}`);
    values.push(v);
  };

  intField("lead_time_days", 365);
  intField("reorder_point", 100_000);
  intField("reorder_quantity", 100_000);

  if (body.reorder_strategy !== undefined) {
    const s = String(body.reorder_strategy).toUpperCase() as Strategy;
    if (!ALLOWED_STRATEGIES.includes(s)) {
      return NextResponse.json(
        { error: `reorder_strategy must be one of ${ALLOWED_STRATEGIES.join(", ")}` },
        { status: 400 },
      );
    }
    updates.push(`reorder_strategy = $${values.length + 1}`);
    values.push(s);
  }

  if (body.unit_cost !== undefined) {
    const c = Math.max(0, Number(body.unit_cost));
    if (!Number.isFinite(c)) {
      return NextResponse.json({ error: "unit_cost must be numeric" }, { status: 400 });
    }
    updates.push(`unit_cost = $${values.length + 1}`);
    values.push(c.toFixed(2));
  }

  if (updates.length === 0) {
    return NextResponse.json({ error: "no editable fields supplied" }, { status: 400 });
  }

  updates.push(`updated_at = NOW()`);
  values.push(typeIri);

  const sql = `
    UPDATE mrp_materials
    SET ${updates.join(", ")}
    WHERE component_type_iri = $${values.length}
    RETURNING component_type_iri
  `;
  const res = await pool.query(sql, values);
  if (res.rowCount === 0) {
    return NextResponse.json({ error: "material not found" }, { status: 404 });
  }
  return NextResponse.json({ success: true });
}
