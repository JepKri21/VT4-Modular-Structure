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
  rowToResourceSlot,
  type ResourceWithAllocations,
} from "@/lib/inventory";

interface SubmodelElement {
  idShort: string;
  modelType?: string;
  value?: unknown;
  valueType?: string;
}

function findElement(elements: SubmodelElement[], idShort: string): SubmodelElement | undefined {
  return elements.find((e) => e.idShort === idShort);
}

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

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const serverUrl = searchParams.get("serverUrl") ?? "";

  await ensureTables();

  if (!serverUrl) {
    // Return cached resources from DB with current allocation summaries
    const result = await pool.query(`
      SELECT rs.*,
             COALESCE(SUM(ra.quantity), 0) AS slots_used,
             COALESCE(
               json_agg(
                 json_build_object(
                   'allocationId', ra.allocation_id,
                   'componentTypeId', ra.component_type_id,
                   'componentName', ct.name,
                   'category', ct.category,
                   'quantity', ra.quantity
                 ) ORDER BY ra.allocated_at
               ) FILTER (WHERE ra.allocation_id IS NOT NULL),
               '[]'
             ) AS allocations
      FROM resource_slots rs
      LEFT JOIN resource_allocations ra ON ra.resource_id = rs.resource_id
      LEFT JOIN component_types ct ON ct.id = ra.component_type_id
      GROUP BY rs.resource_id
    `);

    return NextResponse.json(
      result.rows.map((row) => ({
        ...rowToResourceSlot(row),
        slotsUsed: parseInt(row.slots_used) || 0,
        slotsAvailable:
          (row.inventory_size ?? 0) - (parseInt(row.slots_used) || 0),
        allocations: Array.isArray(row.allocations) ? row.allocations : [],
      }))
    );
  }

  const base = serverUrl.replace(/\/$/, "");

  try {
    const res = await fetch(`${base}/shells?limit=100`);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      return NextResponse.json(
        { error: `AAS server returned ${res.status}: ${text}` },
        { status: 502 }
      );
    }

    const data = (await res.json()) as { result?: unknown[] };
    const rawShells = (
      data.result ?? (Array.isArray(data) ? data : [])
    ) as Array<{
      id: string;
      idShort?: string;
      assetInformation?: { assetKind?: string };
      submodels?: Array<{ keys?: Array<{ value: string }> }>;
    }>;

    // Only instance shells — exclude Type/template shells (AssemblyModule, StorageModule, etc.)
    const resourceShells = rawShells.filter(
      (s) =>
        s.id?.includes("/Shells/Resources/") &&
        s.assetInformation?.assetKind !== "Type"
    );

    const found: ResourceWithAllocations[] = [];

    for (const shell of resourceShells) {
      // Find inventory submodel reference
      const inventorySmRef = shell.submodels?.find((sm) => {
        const key = sm.keys?.[0]?.value ?? "";
        return key.toLowerCase().includes("inventory");
      });
      if (!inventorySmRef) continue;

      const inventorySmId = inventorySmRef.keys?.[0]?.value;
      if (!inventorySmId) continue;

      const encodedSmId = Buffer.from(inventorySmId).toString("base64url");
      const smRes = await fetch(`${base}/submodels/${encodedSmId}`);
      if (!smRes.ok) continue;

      const submodel = (await smRes.json()) as {
        submodelElements?: SubmodelElement[];
      };
      const elements = submodel.submodelElements ?? [];

      const inventoriesCollection = findElement(elements, "Inventories");
      if (!Array.isArray(inventoriesCollection?.value)) continue;

      const inventorySlots =
        inventoriesCollection.value as SubmodelElement[];

      let totalCapacity = 0;
      const allCategories = new Set<string>();

      for (const slot of inventorySlots) {
        if (!slot.idShort?.startsWith("Inventory_")) continue;
        const slotElements = Array.isArray(slot.value)
          ? (slot.value as SubmodelElement[])
          : [];

        // Parse InventorySize
        const specsEl = findElement(slotElements, "Specifications");
        const sizeEl =
          specsEl && Array.isArray(specsEl.value)
            ? findElement(specsEl.value as SubmodelElement[], "InventorySize")
            : undefined;
        const capacity = sizeEl
          ? parseInt(String(sizeEl.value), 10) || 0
          : 0;
        totalCapacity += capacity;

        // Parse SupportedComponents → extract category name.
        // Values can be full IRIs (.../Shells/Component/BottomCover) or plain names ("BottomCover").
        const supportedEl = findElement(slotElements, "SupportedComponents");
        if (supportedEl && Array.isArray(supportedEl.value)) {
          for (const item of supportedEl.value as unknown[]) {
            const raw = typeof item === "object" && item !== null
              ? ((item as Record<string, unknown>).value as string | undefined) ?? ""
              : "";
            if (!raw) continue;
            let category: string;
            if (raw.includes("/")) {
              // Full IRI: https://aausmartlab.org/Shells/Component/BottomCover[/...]
              const parts = raw.replace("https://aausmartlab.org/Shells/", "").split("/");
              // parts[0] = "Component", parts[1] = category
              category = (parts[1] ?? parts[0] ?? "").replace(/_/g, " ").trim();
            } else {
              // Plain name: "BottomCover"
              category = raw.replace(/_/g, " ").trim();
            }
            if (category) allCategories.add(category);
          }
        }
      }

      const resourceName = (
        shell.idShort ?? shell.id.split("/").pop() ?? shell.id
      ).replace(/_/g, " ");

      // Upsert to DB
      await pool.query(
        `INSERT INTO resource_slots (resource_id, resource_name, inventory_size, supported_categories, last_synced)
         VALUES ($1, $2, $3, $4, NOW())
         ON CONFLICT (resource_id) DO UPDATE SET
           resource_name = EXCLUDED.resource_name,
           inventory_size = EXCLUDED.inventory_size,
           supported_categories = EXCLUDED.supported_categories,
           last_synced = EXCLUDED.last_synced`,
        [
          shell.id,
          resourceName,
          totalCapacity,
          JSON.stringify(Array.from(allCategories)),
        ]
      );

      found.push({
        resourceId: shell.id,
        resourceName,
        inventorySize: totalCapacity,
        supportedCategories: Array.from(allCategories),
        lastSynced: new Date().toISOString(),
        slotsUsed: 0,
        slotsAvailable: totalCapacity,
        allocations: [],
      });
    }

    // Remove resource slots that no longer exist on the AAS server.
    // ON DELETE CASCADE on resource_allocations cleans up allocations automatically.
    const foundIds = found.map((r) => r.resourceId);
    if (foundIds.length > 0) {
      const ph = foundIds.map((_, i) => `$${i + 1}`).join(", ");
      await pool.query(
        `DELETE FROM resource_slots
         WHERE resource_id NOT IN (${ph})
           AND resource_id LIKE '%/Shells/Resources/%'`,
        foundIds
      );
    } else {
      await pool.query(
        `DELETE FROM resource_slots WHERE resource_id LIKE '%/Shells/Resources/%'`
      );
    }

    // Overlay current allocation counts
    if (found.length > 0) {
      const usedRes = await pool.query(`
        SELECT ra.resource_id, COALESCE(SUM(ra.quantity), 0) AS slots_used,
               COALESCE(
                 json_agg(json_build_object(
                   'allocationId', ra.allocation_id,
                   'componentTypeId', ra.component_type_id,
                   'componentName', ct.name,
                   'category', ct.category,
                   'quantity', ra.quantity
                 ) ORDER BY ra.allocated_at) FILTER (WHERE ra.allocation_id IS NOT NULL),
                 '[]'
               ) AS allocations
        FROM resource_allocations ra
        JOIN component_types ct ON ct.id = ra.component_type_id
        GROUP BY ra.resource_id
      `);

      const usageMap = new Map(
        usedRes.rows.map((r) => [
          r.resource_id,
          {
            slotsUsed: parseInt(r.slots_used) || 0,
            allocations: Array.isArray(r.allocations) ? r.allocations : [],
          },
        ])
      );

      for (const r of found) {
        const usage = usageMap.get(r.resourceId);
        if (usage) {
          r.slotsUsed = usage.slotsUsed;
          r.slotsAvailable = r.inventorySize - usage.slotsUsed;
          r.allocations = usage.allocations;
        }
      }
    }

    return NextResponse.json(found);
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
