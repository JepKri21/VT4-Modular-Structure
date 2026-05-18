import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import {
  CREATE_COMPONENT_TYPES_TABLE_SQL,
  CREATE_INVENTORY_TABLE_SQL,
  CREATE_ORDERS_TABLE_SQL,
  CREATE_ORDER_ITEMS_TABLE_SQL,
  MIGRATE_COMPONENT_TYPES_SQL,
  rowToComponentType,
  rowToInventoryItem,
  type ComponentType,
  type InventoryItem,
} from "@/lib/inventory";

async function ensureTables() {
  await pool.query(CREATE_COMPONENT_TYPES_TABLE_SQL);
  await pool.query(CREATE_INVENTORY_TABLE_SQL);
  await pool.query(CREATE_ORDERS_TABLE_SQL);
  await pool.query(CREATE_ORDER_ITEMS_TABLE_SQL);
  for (const sql of MIGRATE_COMPONENT_TYPES_SQL) {
    await pool.query(sql);
  }
}

interface ComponentWithInventory extends ComponentType {
  quantityAvailable: number;
  quantityReserved: number;
}

export async function GET() {
  await ensureTables();
  const res = await pool.query(`
    SELECT
      ct.id, ct.category, ct.material, ct.color, ct.finish, ct.current_rating, ct.voltage_rating,
      ct.version, ct.weight, ct.aas_type_iri, ct.name, ct.description, ct.created_at,
      COALESCE(inv.quantity_available, 0) as quantity_available,
      COALESCE(inv.quantity_reserved, 0) as quantity_reserved
    FROM component_types ct
    LEFT JOIN inventory inv ON ct.id = inv.component_type_id
    ORDER BY ct.category, ct.created_at DESC
  `);

  return NextResponse.json(
    res.rows.map((row) => ({
      ...rowToComponentType(row),
      quantityAvailable: row.quantity_available,
      quantityReserved: row.quantity_reserved,
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

  await ensureTables();

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

  await ensureTables();
  await pool.query("DELETE FROM order_items WHERE component_type_id = $1", [componentTypeId]);
  await pool.query("DELETE FROM inventory WHERE component_type_id = $1", [componentTypeId]);
  await pool.query("DELETE FROM component_types WHERE id = $1", [componentTypeId]);

  return NextResponse.json({ ok: true });
}
