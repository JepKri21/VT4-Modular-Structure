import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import {
  CREATE_COMPONENT_TYPES_TABLE_SQL,
  CREATE_INVENTORY_TABLE_SQL,
  CREATE_ORDERS_TABLE_SQL,
  CREATE_ORDER_ITEMS_TABLE_SQL,
  CREATE_RESOURCE_SLOTS_TABLE_SQL,
  CREATE_RESOURCE_ALLOCATIONS_TABLE_SQL,
  CREATE_ALLOCATED_INSTANCES_TABLE_SQL,
  MIGRATE_COMPONENT_TYPES_SQL,
  RESERVED_BY_TYPE_SUBQUERY,
  rowToComponentType,
  type ComponentType,
} from "@/lib/inventory";
import { allocatedByTypeFromAas, resolveAasBase } from "@/lib/resource-inventory";

async function ensureTables() {
  await pool.query(CREATE_COMPONENT_TYPES_TABLE_SQL);
  await pool.query(CREATE_INVENTORY_TABLE_SQL);
  await pool.query(CREATE_ORDERS_TABLE_SQL);
  await pool.query(CREATE_ORDER_ITEMS_TABLE_SQL);
  for (const sql of MIGRATE_COMPONENT_TYPES_SQL) {
    await pool.query(sql);
  }
  await pool.query(CREATE_RESOURCE_SLOTS_TABLE_SQL);
  await pool.query(CREATE_RESOURCE_ALLOCATIONS_TABLE_SQL);
  await pool.query(CREATE_ALLOCATED_INSTANCES_TABLE_SQL);
}

// Run once per server process lifetime — not on every request.
let _ensureTablesPromise: Promise<void> | null = null;
function ensureTablesOnce() {
  if (!_ensureTablesPromise) _ensureTablesPromise = ensureTables().catch((e) => {
    _ensureTablesPromise = null; // retry on next request if it failed
    throw e;
  });
  return _ensureTablesPromise;
}

export async function GET(req: NextRequest) {
  await ensureTablesOnce();

  // `quantityAllocated` (what the webshop sells from) is derived LIVE from the AAS
  // resource Inventory submodels — a part leaves its slot the instant it is picked,
  // so this can't drift the way the cached resource_allocations table does. The DB
  // sum is kept only as a fallback for when the AAS server is unreachable.
  const serverUrl = new URL(req.url).searchParams.get("serverUrl");
  const base = resolveAasBase(serverUrl);
  // `quantityAllocated` (what the webshop sells from) is derived LIVE from the AAS
  // resource Inventory submodels — a part leaves its slot the instant it is picked,
  // so this can't drift the way the cached resource_allocations table does. The DB
  // sum is kept only as a fallback for when the AAS server is unreachable.
  const aasAllocated = await allocatedByTypeFromAas(base);

  // `quantity_reserved` is derived from open orders (B2 model), not the stored
  // inventory column — so a cancelled/fulfilled order automatically stops counting.
  const res = await pool.query(`
    SELECT
      ct.id, ct.category, ct.material, ct.color, ct.finish, ct.current_rating, ct.voltage_rating,
      ct.version, ct.weight, ct.aas_type_iri, ct.name, ct.description, ct.created_at,
      COALESCE(inv.quantity_available, 0) as quantity_available,
      COALESCE(open_res.reserved, 0) as quantity_reserved,
      COALESCE(SUM(ra.quantity), 0) as quantity_allocated
    FROM component_types ct
    LEFT JOIN inventory inv ON ct.id = inv.component_type_id
    LEFT JOIN resource_allocations ra ON ct.id = ra.component_type_id
    LEFT JOIN (${RESERVED_BY_TYPE_SUBQUERY}) open_res ON open_res.component_type_id = ct.id
    GROUP BY ct.id, ct.category, ct.material, ct.color, ct.finish, ct.current_rating,
             ct.voltage_rating, ct.version, ct.weight, ct.aas_type_iri, ct.name,
             ct.description, ct.created_at, inv.quantity_available, open_res.reserved
    ORDER BY ct.category, ct.created_at DESC
  `);

  return NextResponse.json(
    res.rows.map((row) => ({
      ...rowToComponentType(row),
      quantityAvailable: row.quantity_available,
      quantityReserved: row.quantity_reserved,
      // Live AAS count when reachable (0 for a type with no filled slots), else DB fallback.
      quantityAllocated: aasAllocated
        ? aasAllocated.get(row.id) ?? 0
        : parseInt(row.quantity_allocated) || 0,
    }))
  );
}

export async function POST(req: NextRequest) {
  const body = (await req.json()) as {
    type?: "add_type" | "update_inventory";
    component?: ComponentType;
    componentTypeId?: string;
    quantity?: number;
  };

  await ensureTablesOnce();

  if (body.type === "add_type" && body.component) {
    // Insert a new component type
    const c = body.component;
    await pool.query(
      `INSERT INTO component_types (id, category, material, color, finish, current_rating, voltage_rating, version, weight, aas_type_iri, name, description, created_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
       ON CONFLICT (id) DO UPDATE SET
         weight = EXCLUDED.weight,
         aas_type_iri = EXCLUDED.aas_type_iri`,
      [c.id, c.category, c.material ?? null, c.color ?? null, c.finish ?? null, c.currentRating ?? null, c.voltageRating ?? null, c.version ?? null, c.weight ?? null, c.aasTypeIri ?? null, c.name, c.description ?? null]
    );

    // Initialize inventory for this type
    await pool.query(
      `INSERT INTO inventory (component_type_id, quantity_available, quantity_reserved, last_updated)
       VALUES ($1, $2, 0, NOW())
       ON CONFLICT (component_type_id) DO NOTHING`,
      [c.id, body.quantity ?? 0]
    );

    return NextResponse.json({ ok: true });
  } else if (body.type === "update_inventory" && body.componentTypeId) {
    // Update available quantity for a component type
    await pool.query(
      `UPDATE inventory
       SET quantity_available = $1, last_updated = NOW()
       WHERE component_type_id = $2`,
      [body.quantity ?? 0, body.componentTypeId]
    );

    return NextResponse.json({ ok: true });
  }

  return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
}

export async function DELETE(req: NextRequest) {
  const componentTypeId = new URL(req.url).searchParams.get("id");
  if (!componentTypeId) {
    return NextResponse.json({ error: "id query param is required" }, { status: 400 });
  }

  await ensureTablesOnce();
  await pool.query("DELETE FROM order_items WHERE component_type_id = $1", [componentTypeId]);
  await pool.query("DELETE FROM resource_allocations WHERE component_type_id = $1", [componentTypeId]);
  await pool.query("DELETE FROM inventory WHERE component_type_id = $1", [componentTypeId]);
  await pool.query("DELETE FROM component_types WHERE id = $1", [componentTypeId]);

  return NextResponse.json({ ok: true });
}
