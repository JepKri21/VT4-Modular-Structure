import { NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { readPresetBom, bomByParent } from "@/lib/presetBom";

// POST /api/mrp/run — execute one MRP cycle.
//
// BOM source = AAS preset YAMLs (authored in the Configurator).
//
// Pipeline:
//   1. Read upcoming MPS rows (this week or later).
//   2. Look up each row's product in the preset BOM, recursively explode
//      to leaf RAW children. Quantities multiply along the chain.
//   3. Inventory match is by *prefix*: a BOM line for /TopCover consumes
//      any /TopCover/<variant> in stock. The lookup also tolerates the
//      preset's parent IRI being either type-only or with asset name.
//   4. Subtract on-hand + open POs (PROPOSED/APPROVED) and emit POs for
//      anything still net-positive, honouring each material's strategy:
//        LOT_FOR_LOT — order exactly `net`.
//        JIT         — round `net` up to a multiple of reorder_quantity.

interface MaterialCfg {
  kind: string | null;
  reorder_strategy: string;
  reorder_quantity: number;
  unit_cost: string | null;
  lead_time_days: number;
}

export async function POST() {
  // Build the preset BOM tree first; if presets can't be read we bail
  // before touching the DB.
  let presetEntries;
  try {
    presetEntries = await readPresetBom();
  } catch (err) {
    return NextResponse.json(
      { error: `cannot read preset BOM: ${String(err)}` },
      { status: 500 },
    );
  }
  const bomLookup = bomByParent(presetEntries);

  // Database fetches in parallel.
  const [mpsRes, materialsRes, openPoRes] = await Promise.all([
    pool.query(`
      SELECT week_start, finished_product_type_iri, quantity_target
      FROM mrp_mps_entries
      WHERE week_start >= date_trunc('week', NOW())::date
      ORDER BY week_start
    `),
    pool.query(`
      SELECT component_type_iri, kind, reorder_strategy, reorder_quantity,
             unit_cost, lead_time_days
      FROM mrp_materials
    `),
    pool.query(`
      SELECT component_type_iri, SUM(quantity)::int AS qty
      FROM mrp_purchase_orders
      WHERE status IN ('PROPOSED', 'APPROVED')
      GROUP BY component_type_iri
    `),
  ]);

  const materials = new Map<string, MaterialCfg>();
  for (const m of materialsRes.rows) {
    materials.set(m.component_type_iri, {
      kind: m.kind,
      reorder_strategy: m.reorder_strategy,
      reorder_quantity: Number(m.reorder_quantity) || 0,
      unit_cost: m.unit_cost,
      lead_time_days: Number(m.lead_time_days) || 0,
    });
  }

  const onOrder = new Map<string, number>();
  for (const r of openPoRes.rows) onOrder.set(r.component_type_iri, r.qty);

  // Prefix match for on-hand: a BOM iri /Component/TopCover consumes any
  // /Component/TopCover/<variant>. Sum across all variants.
  async function onHandFor(typeIri: string): Promise<number> {
    const res = await pool.query<{ sum: string }>(
      `
        SELECT COALESCE(SUM(on_hand)::int, 0) AS sum
        FROM mrp_inventory
        WHERE component_type_iri = $1
           OR component_type_iri LIKE $2
      `,
      [typeIri, typeIri + "/%"],
    );
    return Number(res.rows[0]?.sum ?? 0);
  }

  // Recursive explosion. Look up BOM by either form of parent IRI —
  // type-only is the canonical key, but a MPS row may carry the full IRI.
  const gross = new Map<string, number>();
  const trace: Array<{ parent: string; child: string; qty: number }> = [];
  const MAX_DEPTH = 8;

  function findBom(iri: string) {
    return bomLookup.get(iri) ?? null;
  }

  function explode(parentIri: string, qty: number, depth: number) {
    if (depth > MAX_DEPTH) return;
    // Try the iri as-is and (if it has a trailing /name) one segment up,
    // since the MPS row may use the full form and the preset key is
    // type-only.
    let entry = findBom(parentIri);
    if (!entry) {
      const trimmed = parentIri.replace(/\/[^/]+$/, "");
      if (trimmed !== parentIri) entry = findBom(trimmed);
    }
    if (!entry) return;
    for (const child of entry.children) {
      const need = qty * child.quantity;
      gross.set(child.iri, (gross.get(child.iri) ?? 0) + need);
      trace.push({ parent: parentIri, child: child.iri, qty: need });
      explode(child.iri, need, depth + 1);
    }
  }

  for (const m of mpsRes.rows) {
    explode(m.finished_product_type_iri, m.quantity_target, 0);
  }

  // Net out and decide PO quantities.
  const proposed: Array<{
    component_type_iri: string;
    quantity: number;
    strategy: string;
    unit_cost: string | null;
    needed_by: string;
    notes: string;
  }> = [];
  const now = Date.now();

  for (const [iri, gQty] of gross) {
    const material = materials.get(iri);
    // Intermediates we produce ourselves and finished goods don't get
    // POs. Anything else (or a material we've never seen) is a candidate.
    if (material?.kind === "INTERMEDIATE" || material?.kind === "FINISHED") {
      continue;
    }
    const onHand = await onHandFor(iri);
    const net = Math.max(
      0,
      Math.ceil(gQty) - onHand - (onOrder.get(iri) ?? 0),
    );
    if (net <= 0) continue;

    const strategy = material?.reorder_strategy ?? "JIT";
    let qty = net;
    if (strategy === "JIT") {
      const lot = material?.reorder_quantity ?? 1;
      if (lot > 1) qty = Math.ceil(net / lot) * lot;
    }
    proposed.push({
      component_type_iri: iri,
      quantity: qty,
      strategy,
      unit_cost: material?.unit_cost ?? null,
      needed_by: new Date(
        now + (material?.lead_time_days ?? 0) * 86_400_000,
      ).toISOString(),
      notes: `Auto-proposed · gross=${gQty.toFixed(2)} on-hand=${onHand} on-order=${onOrder.get(iri) ?? 0}`,
    });
  }

  const client = await pool.connect();
  const created: number[] = [];
  try {
    await client.query("BEGIN");
    for (const p of proposed) {
      const res = await client.query(
        `INSERT INTO mrp_purchase_orders
           (component_type_iri, quantity, strategy, status, unit_cost, needed_by, notes)
         VALUES ($1, $2, $3, 'PROPOSED', $4, $5, $6)
         RETURNING id`,
        [
          p.component_type_iri,
          p.quantity,
          p.strategy,
          p.unit_cost,
          p.needed_by,
          p.notes,
        ],
      );
      created.push(res.rows[0].id);
    }
    await client.query("COMMIT");
  } catch (err) {
    await client.query("ROLLBACK");
    return NextResponse.json(
      { error: "MRP run failed", detail: String(err) },
      { status: 500 },
    );
  } finally {
    client.release();
  }

  return NextResponse.json({
    success: true,
    mps_entries_considered: mpsRes.rows.length,
    bom_edges_walked: trace.length,
    materials_with_gross_requirement: gross.size,
    proposed_pos_created: created.length,
    proposed_po_ids: created,
  });
}
