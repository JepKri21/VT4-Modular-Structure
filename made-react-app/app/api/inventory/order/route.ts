import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import {
  CREATE_COMPONENT_TYPES_TABLE_SQL,
  CREATE_INVENTORY_TABLE_SQL,
  CREATE_ORDERS_TABLE_SQL,
  CREATE_ORDER_ITEMS_TABLE_SQL,
  MIGRATE_COMPONENT_TYPES_SQL,
  MIGRATE_ORDERS_SQL,
  RESERVED_FOR_TYPE_SQL,
  rowToComponentType,
  type OrderStatus,
  type PlacedOrder,
} from "@/lib/inventory";
import { randomUUID } from "crypto";
import { getFuseBounds } from "@/lib/fuseBounds";

async function ensureTables() {
  await pool.query(CREATE_COMPONENT_TYPES_TABLE_SQL);
  await pool.query(CREATE_INVENTORY_TABLE_SQL);
  await pool.query(CREATE_ORDERS_TABLE_SQL);
  await pool.query(CREATE_ORDER_ITEMS_TABLE_SQL);
  for (const sql of MIGRATE_COMPONENT_TYPES_SQL) {
    await pool.query(sql);
  }
  for (const sql of MIGRATE_ORDERS_SQL) {
    await pool.query(sql);
  }
}

// List all placed orders with their line items and component details
export async function GET() {
  await ensureTables();

  // Auto-heal: if the dispatcher missed notifying us (e.g. mes_api was down),
  // mark fulfilled any webshop order whose entire MES batch is COMPLETED.
  await pool.query(`
    UPDATE aas_orders ao
    SET status = 'fulfilled',
        fulfilled_at = COALESCE(
          (SELECT MAX(completed_at)
           FROM mes_orders
           WHERE batch_id = 'ORD-' || UPPER(LEFT(ao.order_id::text, 8))),
          NOW()
        )
    WHERE ao.cancelled_at IS NULL
      AND ao.status NOT IN ('fulfilled', 'cancelled')
      AND EXISTS (
        SELECT 1 FROM mes_orders
        WHERE batch_id = 'ORD-' || UPPER(LEFT(ao.order_id::text, 8))
      )
      AND NOT EXISTS (
        SELECT 1 FROM mes_orders
        WHERE batch_id = 'ORD-' || UPPER(LEFT(ao.order_id::text, 8))
          AND status != 'COMPLETED'
      )
  `).catch(() => {
    // mes_orders table may not exist yet; heal is best-effort
  });

  const res = await pool.query(`
    SELECT
      o.order_id, o.placed_at, o.cancelled_at, o.cancellation_reason, o.reserved_session,
      o.status, o.started_at, o.fulfilled_at,
      oi.order_item_id, oi.component_type_id, oi.quantity, oi.added_at,
      ct.id, ct.category, ct.material, ct.color, ct.version, ct.name, ct.description, ct.created_at
    FROM aas_orders o
    LEFT JOIN order_items oi ON o.order_id = oi.order_id
    LEFT JOIN component_types ct ON oi.component_type_id = ct.id
    WHERE o.cancelled_at IS NULL
    ORDER BY o.placed_at DESC, oi.added_at
  `);

  // Group by order
  const grouped: Record<string, PlacedOrder> = {};

  for (const row of res.rows) {
    const orderId = row.order_id;

    if (!grouped[orderId]) {
      grouped[orderId] = {
        orderId,
        placedAt: row.placed_at instanceof Date ? row.placed_at.toISOString() : row.placed_at,
        cancelledAt: row.cancelled_at instanceof Date ? row.cancelled_at.toISOString() : (row.cancelled_at ?? null),
        cancellationReason: row.cancellation_reason ?? null,
        reserved_session: row.reserved_session ?? null,
        status: (row.status ?? "pending") as OrderStatus,
        startedAt: row.started_at instanceof Date ? row.started_at.toISOString() : (row.started_at ?? null),
        fulfilledAt: row.fulfilled_at instanceof Date ? row.fulfilled_at.toISOString() : (row.fulfilled_at ?? null),
        items: [],
      };
    }

    // Only add item if it exists (not null from outer join)
    if (row.order_item_id) {
      grouped[orderId].items.push({
        orderItemId: row.order_item_id,
        orderId,
        componentTypeId: row.component_type_id,
        quantity: row.quantity,
        addedAt: row.added_at instanceof Date ? row.added_at.toISOString() : row.added_at,
        component: rowToComponentType(row),
      });
    }
  }

  return NextResponse.json(Object.values(grouped));
}

const VALID_STATUS_TRANSITIONS: Record<string, OrderStatus[]> = {
  pending: ["in_production"],
  in_production: ["fulfilled"],
};

// Update order status (pending → in_production → fulfilled)
export async function PATCH(req: NextRequest) {
  const { orderId, status } = (await req.json()) as { orderId?: string; status?: OrderStatus };

  if (!orderId || !status) {
    return NextResponse.json({ error: "orderId and status are required" }, { status: 400 });
  }

  await ensureTables();

  const orderRes = await pool.query(
    `SELECT status FROM aas_orders WHERE order_id = $1 AND cancelled_at IS NULL`,
    [orderId]
  );

  if (orderRes.rows.length === 0) {
    return NextResponse.json({ error: "Order not found or already cancelled" }, { status: 404 });
  }

  const current = orderRes.rows[0].status as OrderStatus;
  const allowed = VALID_STATUS_TRANSITIONS[current] ?? [];

  if (!allowed.includes(status)) {
    return NextResponse.json(
      { error: `Cannot transition from '${current}' to '${status}'` },
      { status: 400 }
    );
  }

  const timestampField =
    status === "in_production" ? ", started_at = NOW()" :
    status === "fulfilled"     ? ", fulfilled_at = NOW()" : "";

  // No inventory write needed: reserved is derived from open orders (B2), so
  // moving the order to 'fulfilled' (out of the open set) releases its
  // reservation automatically. The consumed instances drop out of
  // quantity_available via sync once their shells are referenced by a product BOM.
  await pool.query(
    `UPDATE aas_orders SET status = $1${timestampField} WHERE order_id = $2`,
    [status, orderId]
  );

  return NextResponse.json({ ok: true, orderId, status });
}

// Place an order: create order with line items and reserve inventory
export async function POST(req: NextRequest) {
  const { items, session, totalProducts, productConfigs, serverUrl } = (await req.json()) as {
    items: Array<{ componentTypeId: string; quantity: number }>;
    session: string;
    totalProducts?: number;
    productConfigs?: Array<{
      items: Array<{ slotLabel: string; componentTypeId: string; quantity: number }>;
    }>;
    serverUrl?: string;
  };

  if (!items?.length || !session) {
    return NextResponse.json({ error: "items array and session are required" }, { status: 400 });
  }

  // Enforce the fuse bounds defined in the preset template (single source of
  // truth). Reject out-of-range orders before reserving any inventory so a
  // hand-crafted or buggy request can never push an unbuildable fuse count
  // into production.
  if (productConfigs && productConfigs.length > 0) {
    const { min, max } = getFuseBounds();
    for (let i = 0; i < productConfigs.length; i++) {
      const fuseQty = productConfigs[i].items
        .filter((it) => it.slotLabel?.toLowerCase().includes("fuse"))
        .reduce((sum, it) => sum + (it.quantity ?? 0), 0);
      if (fuseQty < min || fuseQty > max) {
        const range = Number.isFinite(max) ? `${min}–${max}` : `at least ${min}`;
        return NextResponse.json(
          { error: `Product ${i + 1}: fuse count ${fuseQty} is outside the allowed range (${range}).` },
          { status: 400 },
        );
      }
    }
  }

  await ensureTables();

  // Sync from AAS before checking availability so inventory counts are always fresh.
  if (serverUrl) {
    try {
      await fetch(new URL("/api/inventory/sync", req.url).toString(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ serverUrl }),
      });
    } catch {
      // Sync failure is non-fatal — fall back to last-cached inventory counts.
    }
  }

  // Merge duplicate component types (e.g. two fuse slots picking the same type)
  const merged = new Map<string, number>();
  for (const item of items) {
    merged.set(item.componentTypeId, (merged.get(item.componentTypeId) ?? 0) + item.quantity);
  }
  const dedupedItems = Array.from(merged.entries()).map(([componentTypeId, quantity]) => ({
    componentTypeId,
    quantity,
  }));

  const orderId = randomUUID();
  const placedAt = new Date();
  const client = await pool.connect();

  try {
    await client.query("BEGIN");

    // Lock every involved type's inventory row up front, in a deterministic order,
    // so concurrent orders for the same type serialize here (preventing oversell)
    // without risking a deadlock between multi-type orders. We don't write these
    // rows — reserved is derived from open orders — we only need the lock + the
    // available count. A missing row means the type has no inventory entry.
    const typeIds = dedupedItems.map((i) => i.componentTypeId);
    const locked = await client.query(
      `SELECT component_type_id, quantity_available
       FROM inventory
       WHERE component_type_id = ANY($1)
       ORDER BY component_type_id
       FOR UPDATE`,
      [typeIds]
    );
    const availableByType = new Map<string, number>(
      locked.rows.map((r) => [r.component_type_id, r.quantity_available as number])
    );

    await client.query(
      `INSERT INTO aas_orders (order_id, placed_at, reserved_session, cancelled_at)
       VALUES ($1, $2, $3, NULL)`,
      [orderId, placedAt.toISOString(), session]
    );

    for (const item of dedupedItems) {
      if (!availableByType.has(item.componentTypeId)) {
        throw new Error(`Component type not found: ${item.componentTypeId}`);
      }

      // Reserved = demand from other open orders (this order isn't inserted into
      // order_items yet, so it is not double-counted). Effective free stock is
      // available minus that reserved demand.
      const reservedRes = await client.query(RESERVED_FOR_TYPE_SQL, [item.componentTypeId]);
      const reserved = parseInt(reservedRes.rows[0]?.reserved ?? "0", 10) || 0;
      const available = Math.max(0, (availableByType.get(item.componentTypeId) ?? 0) - reserved);
      if (available < item.quantity) {
        throw new Error(
          `Insufficient inventory for ${item.componentTypeId}: need ${item.quantity}, have ${available}`
        );
      }

      await client.query(
        `INSERT INTO order_items (order_item_id, order_id, component_type_id, quantity, added_at)
         VALUES ($1, $2, $3, $4, NOW())`,
        [randomUUID(), orderId, item.componentTypeId, item.quantity]
      );
    }

    await client.query("COMMIT");
  } catch (error) {
    await client.query("ROLLBACK");
    client.release();
    const message = error instanceof Error ? error.message : "Failed to place order";
    console.error("[order POST]", message);
    return NextResponse.json({ error: message }, { status: 400 });
  }
  client.release();

  // Build MES payload — fetch component properties once, then map per-product
  const expectedDelivery = new Date(placedAt.getTime() + 24 * 60 * 60 * 1000);

  const typeCache = new Map<string, Record<string, string | null>>();
  const allTypeIds = new Set(dedupedItems.map((i) => i.componentTypeId));
  await Promise.all(
    Array.from(allTypeIds).map(async (id) => {
      const row = (
        await pool.query(
          `SELECT category, material, color, finish, current_rating, voltage_rating, version, weight, aas_type_iri
           FROM component_types WHERE id = $1`,
          [id]
        )
      ).rows[0] as Record<string, string | null> | undefined;
      if (row) typeCache.set(id, row);
    })
  );

  const buildConfig = (items: Array<{ slotLabel: string; componentTypeId: string; quantity: number }>) =>
    items.map((item) => {
      const row = typeCache.get(item.componentTypeId);
      return {
        slot: item.slotLabel,
        componentTypeId: item.componentTypeId,
        category: row?.category ?? item.componentTypeId,
        aasTypeIri: row?.aas_type_iri ?? null,
        quantity: item.quantity,
        properties: {
          material: row?.material ?? null,
          color: row?.color ?? null,
          finish: row?.finish ?? null,
          currentRating: row?.current_rating ?? null,
          voltageRating: row?.voltage_rating ?? null,
          type: row?.version ?? null,
          weight: row?.weight != null ? Number(row.weight) : null,
        },
      };
    });

  const products =
    productConfigs && productConfigs.length > 0
      ? productConfigs.map((p, idx) => ({
          productIndex: idx + 1,
          name: "AAU Mobile Phone",
          configuration: buildConfig(p.items),
        }))
      : [
          {
            productIndex: 1,
            name: "AAU Mobile Phone",
            configuration: buildConfig(
              dedupedItems.map((i) => ({ slotLabel: i.componentTypeId, componentTypeId: i.componentTypeId, quantity: i.quantity }))
            ),
          },
        ];

  const mesPayload = {
    orderNumber: `ORD-${orderId.slice(0, 8).toUpperCase()}`,
    orderId,
    placedAt: placedAt.toISOString(),
    expectedDelivery: expectedDelivery.toISOString(),
    totalProducts: totalProducts ?? products.length,
    products,
  };

  // Fire-and-forget: notify MES (do not await — webshop does not block on this)
  fetch("http://localhost:8000/api/v1/orders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(mesPayload),
  }).catch((err) => console.warn("[order POST] MES notification failed:", err));

  return NextResponse.json({ ok: true, orderId, mesPayload });
}

// Cancel an order: marking it cancelled removes it from the open set, which
// releases its reservation automatically (reserved is derived from open orders).
export async function DELETE(req: NextRequest) {
  const url = new URL(req.url);
  const orderId = url.searchParams.get("orderId");
  const reason = url.searchParams.get("reason") ?? null;
  if (!orderId) {
    return NextResponse.json({ error: "orderId query param is required" }, { status: 400 });
  }

  await ensureTables();

  const batchId = `ORD-${orderId.slice(0, 8).toUpperCase()}`;

  try {
    await pool.query(
      `UPDATE aas_orders SET cancelled_at = NOW(), status = 'cancelled', cancellation_reason = $2 WHERE order_id = $1`,
      [orderId, reason]
    );
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to cancel order" },
      { status: 400 }
    );
  }

  // Cancel any PENDING MES queue entries for this webshop order so the
  // user doesn't need to cancel separately on the scheduling page.
  // batch_id in mes_orders = "ORD-<first 8 hex chars of webshop UUID uppercase>" (batchId above).
  await pool.query(
    `UPDATE mes_orders
     SET status = 'CANCELLED', completed_at = NOW()
     WHERE batch_id = $1
       AND status = 'PENDING'`,
    [batchId],
  );

  // Fire-and-forget: ask MES to delete BaSyx shells for this order
  fetch(`http://localhost:8000/api/v1/orders/${orderId}/shells`, {
    method: "DELETE",
  }).catch((err) => console.warn("[order DELETE] MES shell cleanup failed:", err));

  return NextResponse.json({ ok: true });
}
