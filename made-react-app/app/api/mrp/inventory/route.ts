import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

// Aggregated on-hand inventory per material type, with per-station
// breakdown so the MRP page can show "Fuse16ASB: 5 total — 3 at
// BCPCBFuseAssembler, 2 at Storage". `material` columns join the
// catalog so the row has a friendly name and the reorder thresholds.

export async function GET() {
  const sql = `
    WITH per_type AS (
      SELECT
        component_type_iri,
        SUM(on_hand)::int AS on_hand_total,
        json_agg(
          json_build_object(
            'resource_id', resource_id,
            'on_hand', on_hand,
            'updated_at', updated_at
          )
          ORDER BY resource_id
        ) AS by_station
      FROM mrp_inventory
      GROUP BY component_type_iri
    )
    SELECT
      m.component_type_iri,
      m.name,
      m.category,
      m.kind,
      m.lead_time_days,
      m.reorder_strategy,
      m.reorder_point,
      m.reorder_quantity,
      m.unit_cost,
      COALESCE(p.on_hand_total, 0) AS on_hand_total,
      COALESCE(p.by_station, '[]'::json) AS by_station
    FROM mrp_materials m
    LEFT JOIN per_type p USING (component_type_iri)
    ORDER BY m.category NULLS LAST, m.name;
  `;
  const result = await pool.query(sql);
  return NextResponse.json({ rows: result.rows });
}
