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
import { collectConsumedIris, fetchResourceInventories, type ResourceInventory } from "@/lib/resource-inventory";

// IRI pattern: https://aausmartlab.org/Shells/Component/{Category}/{Type}-{UUID}
// The UUID is appended to the last segment with a hyphen/underscore prefix.
const UUID_SUFFIX_RE = /[-_][0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
// Plain UUIDs that appear as a full path segment (legacy/fallback).
const UUID_SEGMENT_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type ParsedProperties = {
  material?: string;
  color?: string;
  finish?: string;
  currentRating?: string;
  voltageRating?: string;
  version?: string;
  weight?: number;
};

function getCollectionValue(
  submodelElements: unknown,
  collectionIdShort: string,
  propertyIdShort: string
): string | undefined {
  if (!Array.isArray(submodelElements)) return undefined;

  const collection = submodelElements.find((element) => {
    const candidate = element as Record<string, unknown>;
    return candidate.idShort === collectionIdShort;
  }) as Record<string, unknown> | undefined;

  if (!collection || !Array.isArray(collection.value)) return undefined;

  const property = collection.value.find((element) => {
    const candidate = element as Record<string, unknown>;
    return candidate.idShort === propertyIdShort;
  }) as Record<string, unknown> | undefined;

  const val = property?.value;
  if (typeof val === "string") return val;
  if (typeof val === "number") return String(val);
  return undefined;
}

function formatAmpere(raw: string | undefined): string | undefined {
  if (!raw) return undefined;
  const n = parseFloat(raw);
  if (isNaN(n)) return raw;
  return `${n % 1 === 0 ? n : n}A`;
}

function formatVolt(raw: string | undefined): string | undefined {
  if (!raw) return undefined;
  const n = parseFloat(raw);
  if (isNaN(n)) return raw;
  return `${n % 1 === 0 ? n : n}V`;
}

async function fetchComponentProperties(base: string, shellId: string): Promise<ParsedProperties> {
  try {
    const submodelId = `${shellId}/Properties`;
    const encoded = Buffer.from(submodelId).toString("base64url");
    const response = await fetch(`${base}/submodels/${encoded}`);
    if (!response.ok) return {};

    const submodel = (await response.json()) as { submodelElements?: unknown[] };
    const elems = submodel.submodelElements;

    const material = getCollectionValue(elems, "MaterialProperties", "Material");
    const color = getCollectionValue(elems, "MaterialProperties", "Color");
    const finish = getCollectionValue(elems, "MaterialProperties", "Finish");
    const fuseType = getCollectionValue(elems, "ElectricalProperties", "Type");
    const currentRating = formatAmpere(getCollectionValue(elems, "ElectricalProperties", "CurrentRating"));
    const voltageRating = formatVolt(getCollectionValue(elems, "ElectricalProperties", "VoltageRating"));
    const rawWeight = getCollectionValue(elems, "PhysicalDimensions", "Weight");
    const weight = rawWeight != null ? parseFloat(rawWeight) : undefined;

    return {
      material,
      color,
      finish,
      currentRating,
      voltageRating,
      version: fuseType,
      weight: weight != null && !isNaN(weight) ? weight : undefined,
    };
  } catch {
    return {};
  }
}

/**
 * Fetch every page of a BaSyx collection endpoint (e.g. "/shells", "/submodels"),
 * following the cursor in paging_metadata. Replaces the old `?limit=100` cap that
 * silently dropped everything past the first 100 entries.
 */
async function fetchAllPaged(base: string, path: string): Promise<Record<string, unknown>[]> {
  const out: Record<string, unknown>[] = [];
  let cursor: string | undefined;
  for (let i = 0; i < 100; i++) {
    const sep = path.includes("?") ? "&" : "?";
    const url = `${base}${path}${sep}limit=1000${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`;
    const res = await fetch(url);
    if (!res.ok) {
      if (i === 0) {
        throw new Error(`${res.status}: ${await res.text().catch(() => "")}`);
      }
      break; // partial failure mid-pagination — return what we have
    }
    const data = (await res.json()) as { result?: unknown[]; paging_metadata?: { cursor?: string } };
    const batch = (data.result ?? (Array.isArray(data) ? data : [])) as Record<string, unknown>[];
    out.push(...batch);
    cursor = data.paging_metadata?.cursor;
    if (!cursor) break;
  }
  return out;
}

export async function POST(req: NextRequest) {
  const { serverUrl } = (await req.json()) as { serverUrl: string };

  if (!serverUrl) {
    return NextResponse.json({ error: "serverUrl is required" }, { status: 400 });
  }

  const base = serverUrl.replace(/\/$/, "");

  try {
    let rawShells: Record<string, unknown>[];
    try {
      rawShells = await fetchAllPaged(base, "/shells");
    } catch (err) {
      return NextResponse.json(
        { error: `AAS Server returned ${String(err)}` },
        { status: 502 }
      );
    }

    // Detect component instances already consumed into a product so they are not
    // counted as available stock. Best-effort: if the submodels can't be read,
    // fall back to counting every shell (nothing excluded).
    let consumedIris = new Set<string>();
    try {
      const rawSubmodels = await fetchAllPaged(base, "/submodels");
      consumedIris = collectConsumedIris(rawSubmodels);
    } catch {
      /* ignore — degrade to counting all shells */
    }

    // Resource StoredComponents are the physical ground truth for stock. Best-effort:
    // if they can't be read, the allocation rebuild below is skipped (allocations untouched).
    let resourceInventories: ResourceInventory[] = [];
    try {
      resourceInventories = await fetchResourceInventories(base, rawShells);
    } catch {
      /* ignore — leave resource allocations as-is */
    }

    await pool.query(CREATE_COMPONENT_TYPES_TABLE_SQL);
    await pool.query(CREATE_INVENTORY_TABLE_SQL);
    await pool.query(CREATE_ORDERS_TABLE_SQL);
    await pool.query(CREATE_ORDER_ITEMS_TABLE_SQL);
    await pool.query(CREATE_RESOURCE_SLOTS_TABLE_SQL);
    await pool.query(CREATE_RESOURCE_ALLOCATIONS_TABLE_SQL);
    await pool.query(CREATE_ALLOCATED_INSTANCES_TABLE_SQL);
    for (const sql of MIGRATE_COMPONENT_TYPES_SQL) {
      await pool.query(sql);
    }

    // Clean up stale UUID-tainted component type IDs from previous (broken) syncs.
    // Old IDs looked like "fuse_fuse_16a_sb_d6f8e1d3-6196-4c44-..." — strip those so
    // they don't appear alongside the new correctly-grouped types.
    await pool.query(
      `DELETE FROM resource_allocations WHERE component_type_id ~ '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'`
    );
    await pool.query(
      `DELETE FROM component_types WHERE id ~ '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'`
    );

    // Count shells per component type (UUID regexes are module-scope: UUID_SUFFIX_RE / UUID_SEGMENT_RE)
    const typeCounts: Record<string, { category: string; type: string; name: string; count: number; shellId: string }> = {};

    for (const shell of rawShells) {
      const id = (shell.id as string) ?? "";
      if (!id) continue;

      // Skip non-component shells (resources, production lines, etc.)
      if (!id.includes("/Shells/Component/")) continue;

      // Skip type-level template shells — only count physical instances
      const assetKind = (shell.assetInformation as Record<string, unknown> | undefined)?.assetKind;
      if (assetKind === "Type") continue;

      const segments = id.replace("https://aausmartlab.org/Shells/", "").split("/").filter(Boolean);
      // Filter out any full-UUID path segments (legacy format)
      const meaningful = segments.filter((s) => !UUID_SEGMENT_RE.test(s));

      // Strip UUID suffix from the last meaningful segment (e.g., "Fuse_16A_SB_d6f8e1d3-..." → "Fuse_16A_SB")
      const rawLastSegment = meaningful[2] ?? meaningful[meaningful.length - 1] ?? "Unknown";
      const typeSegment = rawLastSegment.replace(UUID_SUFFIX_RE, "");

      const category = (meaningful[1] ?? "Unknown").replace(/_/g, " ");
      const name = typeSegment.replace(/_/g, " ");
      const componentTypeId = `${meaningful[1] ?? "unknown"}_${typeSegment}`.toLowerCase().replace(/\s+/g, "_");

      if (!typeCounts[componentTypeId]) {
        // Store this instance's IRI for property fetching (any instance of the same type works)
        typeCounts[componentTypeId] = { category, type: typeSegment, name, count: 0, shellId: id };
      }

      // Consumed instances stay on the AAS but are no longer available stock.
      // The type is still registered above (so it shows with the correct count,
      // even 0, rather than vanishing), but its count is not incremented.
      if (consumedIris.has(id)) continue;

      // Prefer a non-consumed instance as the property representative.
      if (consumedIris.has(typeCounts[componentTypeId].shellId)) {
        typeCounts[componentTypeId].shellId = id;
      }
      typeCounts[componentTypeId].count++;
    }

    let created = 0;
    // For each component type found on the AAS server, ensure it exists and SET inventory to the count
    for (const [componentTypeId, info] of Object.entries(typeCounts)) {
      // Use instance IRI for property fetching; store the type IRI (no UUID) for WorkOrder references
      const properties = await fetchComponentProperties(base, info.shellId);
      const categorySegment = info.category.replace(/ /g, "_");
      const typeIri = `https://aausmartlab.org/Shells/Component/${categorySegment}/${info.type}`;

      // Ensure component type exists and keep the live properties in sync
      const typeRes = await pool.query(
        `INSERT INTO component_types (id, category, material, color, finish, current_rating, voltage_rating, version, weight, aas_type_iri, name, description, created_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
         ON CONFLICT (id) DO UPDATE SET
           category = EXCLUDED.category,
           material = EXCLUDED.material,
           color = EXCLUDED.color,
           finish = EXCLUDED.finish,
           current_rating = EXCLUDED.current_rating,
           voltage_rating = EXCLUDED.voltage_rating,
           version = EXCLUDED.version,
           weight = EXCLUDED.weight,
           aas_type_iri = EXCLUDED.aas_type_iri,
           name = EXCLUDED.name,
           description = EXCLUDED.description
         RETURNING id`,
        [
          componentTypeId, info.category,
          properties.material ?? null, properties.color ?? null,
          properties.finish ?? null, properties.currentRating ?? null, properties.voltageRating ?? null,
          properties.version ?? null, properties.weight ?? null,
          typeIri,
          info.name, `Synced from ${base}`,
        ]
      );
      if (typeRes.rows.length > 0) created++;

      // SET inventory to the actual count from AAS server (atomic upsert)
      await pool.query(
        `INSERT INTO inventory (component_type_id, quantity_available, quantity_reserved, last_updated)
         VALUES ($1, $2, 0, NOW())
         ON CONFLICT (component_type_id) DO UPDATE SET
           quantity_available = EXCLUDED.quantity_available,
           last_updated = EXCLUDED.last_updated`,
        [componentTypeId, info.count]
      );
    }

    // Remove stale synced entries that are no longer present on the AAS server
    // (covers type-level template shells and any other previously-synced leftovers).
    // Only touches rows whose description starts with "Synced from" to avoid
    // deleting manually-created entries.
    const activeIds = Object.keys(typeCounts);
    if (activeIds.length > 0) {
      const placeholders = activeIds.map((_, i) => `$${i + 1}`).join(", ");
      const staleFilter = `id NOT IN (${placeholders}) AND description LIKE 'Synced from %'`;
      await pool.query(
        `DELETE FROM inventory WHERE component_type_id NOT IN (${placeholders})
           AND component_type_id IN (SELECT id FROM component_types WHERE ${staleFilter})`,
        activeIds
      );
      await pool.query(
        `DELETE FROM order_items WHERE component_type_id NOT IN (${placeholders})
           AND component_type_id IN (SELECT id FROM component_types WHERE ${staleFilter})`,
        activeIds
      );
      await pool.query(
        `DELETE FROM resource_allocations WHERE component_type_id NOT IN (${placeholders})
           AND component_type_id IN (SELECT id FROM component_types WHERE ${staleFilter})`,
        activeIds
      );
      await pool.query(
        `DELETE FROM component_types WHERE ${staleFilter}`,
        activeIds
      );
    } else {
      // Nothing synced — wipe all previously-synced entries
      await pool.query(`DELETE FROM inventory WHERE component_type_id IN (SELECT id FROM component_types WHERE description LIKE 'Synced from %')`);
      await pool.query(`DELETE FROM order_items WHERE component_type_id IN (SELECT id FROM component_types WHERE description LIKE 'Synced from %')`);
      await pool.query(`DELETE FROM resource_allocations WHERE component_type_id IN (SELECT id FROM component_types WHERE description LIKE 'Synced from %')`);
      await pool.query(`DELETE FROM component_types WHERE description LIKE 'Synced from %'`);
    }

    // ── Rebuild resource allocations from the physical AAS inventories ──
    // The webshop sells from `quantityAllocated` (SUM of resource_allocations), and the
    // per-zone view shows the same. Those were written once at allocation time and never
    // decremented when production consumed a part, so consumed/assembled components kept
    // counting as sellable stock. Mirror each resource's actual StoredComponents into
    // resource_slots / resource_allocations / allocated_instances so the counts reflect
    // what is physically present right now.
    let resourcesReconciled = 0;
    let instancesReconciled = 0;
    if (resourceInventories.length > 0) {
      const client = await pool.connect();
      try {
        await client.query("BEGIN");
        const resourceIds = resourceInventories.map((r) => r.resourceId);
        const ph = resourceIds.map((_, i) => `$${i + 1}`).join(", ");

        // Upsert capacity + categories for every live resource.
        for (const r of resourceInventories) {
          await client.query(
            `INSERT INTO resource_slots (resource_id, resource_name, inventory_size, supported_categories, last_synced)
             VALUES ($1, $2, $3, $4, NOW())
             ON CONFLICT (resource_id) DO UPDATE SET
               resource_name = EXCLUDED.resource_name,
               inventory_size = EXCLUDED.inventory_size,
               supported_categories = EXCLUDED.supported_categories,
               last_synced = EXCLUDED.last_synced`,
            [r.resourceId, r.resourceName, r.capacity, JSON.stringify(r.categories)]
          );
        }

        // Drop resource_slots no longer on the AAS (CASCADE clears their allocations).
        await client.query(
          `DELETE FROM resource_slots
            WHERE resource_id LIKE '%/Shells/Resources/%' AND resource_id NOT IN (${ph})`,
          resourceIds
        );

        // Replace each live resource's allocations with its physical slot contents.
        await client.query(
          `DELETE FROM resource_allocations WHERE resource_id IN (${ph})`,
          resourceIds
        );

        for (const r of resourceInventories) {
          const byType = new Map<string, string[]>();
          for (const slot of r.filled) {
            const list = byType.get(slot.componentTypeId) ?? [];
            list.push(slot.instanceIri);
            byType.set(slot.componentTypeId, list);
          }
          for (const [componentTypeId, iris] of byType) {
            // FK guard: only allocate types known to component_types.
            const typeExists = await client.query(
              `SELECT 1 FROM component_types WHERE id = $1`,
              [componentTypeId]
            );
            if (typeExists.rowCount === 0) continue;

            const allocationId = crypto.randomUUID();
            await client.query(
              `INSERT INTO resource_allocations (allocation_id, resource_id, component_type_id, quantity, notes)
               VALUES ($1, $2, $3, $4, $5)`,
              [allocationId, r.resourceId, componentTypeId, iris.length, "Reconciled from AAS inventory"]
            );
            for (const iri of iris) {
              await client.query(
                `INSERT INTO allocated_instances (allocation_id, instance_iri)
                 VALUES ($1, $2) ON CONFLICT (instance_iri) DO NOTHING`,
                [allocationId, iri]
              );
            }
            resourcesReconciled++;
            instancesReconciled += iris.length;
          }
        }
        await client.query("COMMIT");
      } catch (e) {
        await client.query("ROLLBACK");
        console.error("resource allocation rebuild failed:", e);
      } finally {
        client.release();
      }
    }

    return NextResponse.json({
      synced: rawShells.length,
      created,
      updated: Object.keys(typeCounts).length - created,
      resourcesReconciled,
      instancesReconciled,
      message: `Found ${rawShells.length} shell(s) on server, synchronized ${Object.keys(typeCounts).length} component type(s); reconciled ${instancesReconciled} allocated instance(s) across ${resourceInventories.length} resource(s) from physical inventory.`,
    });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
