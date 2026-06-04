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
} from "@/lib/inventory";

async function ensureTables() {
  await pool.query(CREATE_COMPONENT_TYPES_TABLE_SQL);
  await pool.query(CREATE_INVENTORY_TABLE_SQL);
  await pool.query(CREATE_ORDERS_TABLE_SQL);
  await pool.query(CREATE_ORDER_ITEMS_TABLE_SQL);
  for (const sql of MIGRATE_COMPONENT_TYPES_SQL) await pool.query(sql);
  await pool.query(CREATE_RESOURCE_SLOTS_TABLE_SQL);
  await pool.query(CREATE_RESOURCE_ALLOCATIONS_TABLE_SQL);
  await pool.query(CREATE_ALLOCATED_INSTANCES_TABLE_SQL);
}

// Find unallocated instance shells of a given type from the AAS server.
// Instance IRI = typeIri + "-" + UUID  (e.g. .../BottomCoverABSBlack-<uuid>)
async function findAvailableInstances(
  base: string,
  aasTypeIri: string,
  quantity: number,
  excludeIris: Set<string>
): Promise<string[]> {
  const res = await fetch(`${base}/shells?limit=1000`);
  if (!res.ok) throw new Error(`AAS server returned ${res.status} when fetching instances`);

  const data = (await res.json()) as { result?: unknown[] };
  const shells = (data.result ?? (Array.isArray(data) ? data : [])) as Array<{
    id: string;
    assetInformation?: { assetKind?: string };
  }>;

  const typePrefix = aasTypeIri + "-";
  const available = shells.filter((s) => {
    if (!s.id?.startsWith(typePrefix)) return false;
    if (s.assetInformation?.assetKind === "Type") return false;
    if (excludeIris.has(s.id)) return false;
    return true;
  }).map((s) => s.id);

  const typeName = aasTypeIri.split("/").pop() ?? aasTypeIri;
  if (available.length < quantity) {
    throw new Error(
      `Only ${available.length} unallocated instance(s) of "${typeName}" on the AAS server, ${quantity} requested`
    );
  }

  return available.slice(0, quantity);
}

// Add actual instance shell IRIs to the resource's StoredComponents in BaSyx.
async function updateAasInventory(
  serverUrl: string,
  resourceShellId: string,
  instanceIris: string[]
): Promise<boolean> {
  const base = serverUrl.replace(/\/$/, "");

  try {
    const encodedShellId = Buffer.from(resourceShellId).toString("base64url");
    const shellRes = await fetch(`${base}/shells/${encodedShellId}`);
    if (!shellRes.ok) return false;

    const shell = (await shellRes.json()) as {
      submodels?: Array<{ keys?: Array<{ value: string }> }>;
    };

    const inventorySmRef = shell.submodels?.find((sm) => {
      const key = sm.keys?.[0]?.value ?? "";
      return key.toLowerCase().includes("inventory");
    });
    if (!inventorySmRef) return false;

    const inventorySmId = inventorySmRef.keys?.[0]?.value;
    if (!inventorySmId) return false;
    const encodedSmId = Buffer.from(inventorySmId).toString("base64url");

    // The shell is generated with pre-allocated empty slots (SlotEntry_1 … SlotEntry_N).
    // We must fill those empty slots rather than appending new ones — the collection
    // must never exceed InventorySize entries.
    const storedPath = "Inventories.Inventory_1.StoredComponents";
    const storedRes = await fetch(
      `${base}/submodels/${encodedSmId}/submodel-elements/${storedPath}`
    );

    if (!storedRes.ok) {
      console.error(`AAS: could not fetch StoredComponents (${storedRes.status})`);
      return false;
    }

    type SlotChild = { idShort: string; modelType?: string; value?: unknown; valueType?: string };
    type SlotEntry = { idShort: string; modelType?: string; value?: SlotChild[] };

    const stored = (await storedRes.json()) as { idShort?: string; value?: SlotEntry[] };
    const entries: SlotEntry[] = stored.value ?? [];

    // A slot is available when ComponentShellReference has no populated keys.
    // SlotReserved is managed separately during production and is not touched here.
    function isRefEmpty(value: unknown): boolean {
      if (value == null || value === "" || value === false) return true;
      if (typeof value === "object") {
        const keys = (value as Record<string, unknown>).keys;
        if (!Array.isArray(keys) || keys.length === 0) return true;
      }
      return false;
    }

    const emptySlots = entries.filter((entry) => {
      const children = entry.value ?? [];
      const ref = children.find((c) => c.idShort === "ComponentShellReference");
      return isRefEmpty(ref?.value);
    });

    if (emptySlots.length < instanceIris.length) {
      console.error(
        `AAS: only ${emptySlots.length} empty slot(s) available, need ${instanceIris.length}`
      );
      return false;
    }

    // Fill empty slots in-place with the instance IRIs
    const updated = entries.map((entry) => {
      const iriForThisSlot = instanceIris[emptySlots.indexOf(entry)];
      if (iriForThisSlot === undefined) return entry; // not a slot we're filling

      return {
        ...entry,
        value: (entry.value ?? []).map((child) => {
          if (child.idShort === "ComponentShellReference") {
            return {
              ...child,
              value: {
                type: "ModelReference",
                keys: [{ type: "AssetAdministrationShell", value: iriForThisSlot }],
              },
            };
          }
          return child;
        }),
      };
    });

    // PUT the modified collection back
    const putRes = await fetch(
      `${base}/submodels/${encodedSmId}/submodel-elements/${storedPath}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          idShort: "StoredComponents",
          modelType: "SubmodelElementCollection",
          value: updated,
        }),
      }
    );

    if (!putRes.ok) {
      const detail = await putRes.text().catch(() => "");
      console.error(`AAS: PUT StoredComponents failed (${putRes.status}): ${detail}`);
      return false;
    }

    return true;
  } catch (err) {
    console.error("updateAasInventory:", err);
    return false;
  }
}

export async function GET(req: NextRequest) {
  await ensureTables();

  const { searchParams } = new URL(req.url);
  const resourceId = searchParams.get("resourceId");

  const query = resourceId
    ? `SELECT ra.*, ct.name AS component_name, ct.category,
              COALESCE(
                json_agg(ai.instance_iri ORDER BY ai.instance_iri) FILTER (WHERE ai.instance_iri IS NOT NULL),
                '[]'
              ) AS instance_iris
       FROM resource_allocations ra
       JOIN component_types ct ON ct.id = ra.component_type_id
       LEFT JOIN allocated_instances ai ON ai.allocation_id = ra.allocation_id
       WHERE ra.resource_id = $1
       GROUP BY ra.allocation_id, ct.name, ct.category
       ORDER BY ra.allocated_at DESC`
    : `SELECT ra.*, ct.name AS component_name, ct.category,
              COALESCE(
                json_agg(ai.instance_iri ORDER BY ai.instance_iri) FILTER (WHERE ai.instance_iri IS NOT NULL),
                '[]'
              ) AS instance_iris
       FROM resource_allocations ra
       JOIN component_types ct ON ct.id = ra.component_type_id
       LEFT JOIN allocated_instances ai ON ai.allocation_id = ra.allocation_id
       GROUP BY ra.allocation_id, ct.name, ct.category
       ORDER BY ra.allocated_at DESC`;

  const result = resourceId
    ? await pool.query(query, [resourceId])
    : await pool.query(query);

  return NextResponse.json(
    result.rows.map((row) => ({
      allocationId: row.allocation_id,
      resourceId: row.resource_id,
      componentTypeId: row.component_type_id,
      componentName: row.component_name,
      category: row.category,
      quantity: row.quantity,
      instanceIris: Array.isArray(row.instance_iris) ? row.instance_iris : [],
      allocatedAt:
        row.allocated_at instanceof Date
          ? row.allocated_at.toISOString()
          : row.allocated_at,
      notes: row.notes ?? null,
    }))
  );
}

export async function POST(req: NextRequest) {
  await ensureTables();

  const body = (await req.json()) as {
    resourceId: string;
    items: Array<{ componentTypeId: string; quantity: number }>;
    serverUrl: string;
    notes?: string;
  };

  const { resourceId, items, serverUrl, notes } = body;

  if (!resourceId || !Array.isArray(items) || items.length === 0) {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }
  if (!serverUrl) {
    return NextResponse.json(
      { error: "serverUrl is required to look up actual component instances from the AAS server" },
      { status: 400 }
    );
  }

  const base = serverUrl.replace(/\/$/, "");

  // Validate resource
  const resourceResult = await pool.query(
    `SELECT * FROM resource_slots WHERE resource_id = $1`,
    [resourceId]
  );
  if (resourceResult.rows.length === 0) {
    return NextResponse.json({ error: "Resource not found" }, { status: 404 });
  }
  const resource = resourceResult.rows[0];

  // Check resource capacity
  const usedResult = await pool.query(
    `SELECT COALESCE(SUM(quantity), 0) AS used FROM resource_allocations WHERE resource_id = $1`,
    [resourceId]
  );
  const currentlyUsed = parseInt(usedResult.rows[0].used) || 0;
  const totalRequested = items.reduce((sum, item) => sum + item.quantity, 0);
  if (currentlyUsed + totalRequested > resource.inventory_size) {
    const available = resource.inventory_size - currentlyUsed;
    return NextResponse.json(
      { error: `Not enough capacity. ${available} slot(s) free, ${totalRequested} requested.` },
      { status: 400 }
    );
  }

  // Validate each type's stock level
  for (const item of items) {
    const invResult = await pool.query(
      `SELECT i.quantity_available, i.quantity_reserved,
              COALESCE(SUM(ra.quantity), 0) AS already_allocated
       FROM inventory i
       LEFT JOIN resource_allocations ra ON ra.component_type_id = i.component_type_id
       WHERE i.component_type_id = $1
       GROUP BY i.quantity_available, i.quantity_reserved`,
      [item.componentTypeId]
    );
    if (invResult.rows.length === 0) {
      return NextResponse.json({ error: `Component not found: ${item.componentTypeId}` }, { status: 404 });
    }
    const row = invResult.rows[0];
    const netAvailable =
      (row.quantity_available ?? 0) -
      (row.quantity_reserved ?? 0) -
      (parseInt(row.already_allocated) || 0);
    if (netAvailable < item.quantity) {
      return NextResponse.json(
        { error: `Insufficient stock for ${item.componentTypeId}. Available: ${netAvailable}, requested: ${item.quantity}.` },
        { status: 400 }
      );
    }
  }

  // Get all already-allocated instance IRIs so we don't double-allocate
  const allocatedResult = await pool.query(`SELECT instance_iri FROM allocated_instances`);
  const allocatedIris = new Set<string>(allocatedResult.rows.map((r) => r.instance_iri as string));

  // Resolve type IRIs and find available instances on AAS for each item
  const instanceMap = new Map<string, string[]>(); // componentTypeId → chosen instance IRIs
  for (const item of items) {
    const typeResult = await pool.query(
      `SELECT aas_type_iri FROM component_types WHERE id = $1`,
      [item.componentTypeId]
    );
    const aasTypeIri = typeResult.rows[0]?.aas_type_iri as string | undefined;
    if (!aasTypeIri) {
      return NextResponse.json(
        { error: `No AAS type IRI found for component ${item.componentTypeId}. Run a sync first.` },
        { status: 400 }
      );
    }

    let instances: string[];
    try {
      instances = await findAvailableInstances(base, aasTypeIri, item.quantity, allocatedIris);
    } catch (err) {
      return NextResponse.json({ error: String(err) }, { status: 400 });
    }

    // Mark these as taken so parallel items in the same request don't pick the same shells
    instances.forEach((iri) => allocatedIris.add(iri));
    instanceMap.set(item.componentTypeId, instances);
  }

  // Insert allocations and instance records in a transaction
  const allocationIds: string[] = [];
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    for (const item of items) {
      const allocationId = crypto.randomUUID();
      await client.query(
        `INSERT INTO resource_allocations (allocation_id, resource_id, component_type_id, quantity, notes)
         VALUES ($1, $2, $3, $4, $5)`,
        [allocationId, resourceId, item.componentTypeId, item.quantity, notes ?? null]
      );

      const instances = instanceMap.get(item.componentTypeId) ?? [];
      for (const iri of instances) {
        await client.query(
          `INSERT INTO allocated_instances (allocation_id, instance_iri) VALUES ($1, $2)`,
          [allocationId, iri]
        );
      }

      allocationIds.push(allocationId);
    }
    await client.query("COMMIT");
  } catch (err) {
    await client.query("ROLLBACK");
    client.release();
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
  client.release();

  // Update AAS resource inventory with actual instance IRIs
  const allInstanceIris = Array.from(instanceMap.values()).flat();
  let aasUpdated = false;
  try {
    aasUpdated = await updateAasInventory(serverUrl, resourceId, allInstanceIris);
  } catch (err) {
    console.error("AAS update failed:", err);
  }

  return NextResponse.json({ ok: true, allocationIds, aasUpdated, instanceCount: allInstanceIris.length });
}
