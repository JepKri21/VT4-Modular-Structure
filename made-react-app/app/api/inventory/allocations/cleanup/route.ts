import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";

type SlotChild = { idShort: string; modelType?: string; value?: unknown };
type SlotEntry = { idShort: string; modelType?: string; value?: SlotChild[] };

async function clearStaleSlots(
  base: string,
  resourceId: string,
  staleIris: Set<string>
): Promise<void> {
  // Find the resource shell's Inventory submodel
  const encodedShellId = Buffer.from(resourceId).toString("base64url");
  const shellRes = await fetch(`${base}/shells/${encodedShellId}`);
  if (!shellRes.ok) return;

  const shell = (await shellRes.json()) as {
    submodels?: Array<{ keys?: Array<{ value: string }> }>;
  };

  const inventorySmRef = shell.submodels?.find((sm) => {
    const key = sm.keys?.[0]?.value ?? "";
    return key.toLowerCase().includes("inventory");
  });
  if (!inventorySmRef) return;

  const inventorySmId = inventorySmRef.keys?.[0]?.value;
  if (!inventorySmId) return;
  const encodedSmId = Buffer.from(inventorySmId).toString("base64url");

  const storedPath = "Inventories.Inventory_1.StoredComponents";
  const storedRes = await fetch(
    `${base}/submodels/${encodedSmId}/submodel-elements/${storedPath}`
  );
  if (!storedRes.ok) return;

  const stored = (await storedRes.json()) as { idShort?: string; value?: SlotEntry[] };
  const entries: SlotEntry[] = stored.value ?? [];

  // Clear ComponentShellReference for any slot referencing a stale IRI
  const updated = entries.map((entry) => {
    const ref = (entry.value ?? []).find((c) => c.idShort === "ComponentShellReference");
    const refVal = ref?.value as Record<string, unknown> | undefined;
    const keys = refVal?.keys as Array<{ value?: string }> | undefined;
    const storedIri = keys?.[0]?.value ?? "";

    if (!storedIri || !staleIris.has(storedIri)) return entry;

    // Clear this slot's reference
    return {
      ...entry,
      value: (entry.value ?? []).map((child) => {
        if (child.idShort === "ComponentShellReference") {
          return { ...child, value: null };
        }
        return child;
      }),
    };
  });

  await fetch(
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
}

export async function POST(req: NextRequest) {
  const { serverUrl } = (await req.json()) as { serverUrl: string };

  if (!serverUrl) {
    return NextResponse.json({ error: "serverUrl is required" }, { status: 400 });
  }

  const base = serverUrl.replace(/\/$/, "");

  // Fetch all shells currently on the AAS server
  const shellsRes = await fetch(`${base}/shells?limit=1000`);
  if (!shellsRes.ok) {
    return NextResponse.json(
      { error: `AAS server returned ${shellsRes.status}` },
      { status: 502 }
    );
  }
  const shellsData = (await shellsRes.json()) as { result?: unknown[] };
  const liveIris = new Set(
    (
      (shellsData.result ?? (Array.isArray(shellsData) ? shellsData : [])) as Array<{
        id: string;
      }>
    ).map((s) => s.id)
  );

  // ── Case 1: resource shell deleted ──────────────────────────────────────
  // If the resource itself no longer exists on the AAS server, free every
  // allocation that was targeting it and remove it from resource_slots.
  const knownResources = await pool.query(`SELECT resource_id FROM resource_slots`);
  const deletedResources = (knownResources.rows as Array<{ resource_id: string }>).filter(
    (r) => !liveIris.has(r.resource_id)
  );

  let freedByDeletedResource = 0;
  for (const { resource_id } of deletedResources) {
    const countRes = await pool.query(
      `SELECT COUNT(*) AS n FROM allocated_instances ai
       JOIN resource_allocations ra ON ra.allocation_id = ai.allocation_id
       WHERE ra.resource_id = $1`,
      [resource_id]
    );
    freedByDeletedResource += parseInt(countRes.rows[0].n) || 0;

    // Cascade deletes allocated_instances via ON DELETE CASCADE on resource_allocations
    await pool.query(`DELETE FROM resource_allocations WHERE resource_id = $1`, [resource_id]);
    await pool.query(`DELETE FROM resource_slots WHERE resource_id = $1`, [resource_id]);
  }

  // ── Case 2: component instance shell deleted ─────────────────────────────
  // The resource still exists but a specific component instance was removed.
  const allocResult = await pool.query(`
    SELECT ai.instance_iri, ai.allocation_id, ra.resource_id
    FROM allocated_instances ai
    JOIN resource_allocations ra ON ra.allocation_id = ai.allocation_id
  `);

  const stale = allocResult.rows.filter((r) => !liveIris.has(r.instance_iri as string));

  // Group stale instances by resource to clear AAS slots in one PUT per resource
  const staleByResource = new Map<string, Set<string>>();
  for (const row of stale) {
    const rid = row.resource_id as string;
    if (!staleByResource.has(rid)) staleByResource.set(rid, new Set());
    staleByResource.get(rid)!.add(row.instance_iri as string);
  }

  for (const [resourceId, iris] of staleByResource) {
    try {
      await clearStaleSlots(base, resourceId, iris);
    } catch (err) {
      console.error(`AAS slot cleanup failed for resource ${resourceId}:`, err);
    }
  }

  if (stale.length > 0) {
    const staleIris = stale.map((r) => r.instance_iri as string);
    await pool.query(
      `DELETE FROM allocated_instances WHERE instance_iri = ANY($1::text[])`,
      [staleIris]
    );
    await pool.query(`
      DELETE FROM resource_allocations
      WHERE allocation_id NOT IN (SELECT DISTINCT allocation_id FROM allocated_instances)
    `);
  }

  const totalFreed = freedByDeletedResource + stale.length;

  if (totalFreed === 0) {
    return NextResponse.json({ freed: 0, message: "All allocations are up to date." });
  }

  const parts: string[] = [];
  if (deletedResources.length > 0)
    parts.push(`${deletedResources.length} deleted resource(s) freed ${freedByDeletedResource} slot(s)`);
  if (stale.length > 0)
    parts.push(`${stale.length} deleted component instance(s) freed`);

  return NextResponse.json({
    freed: totalFreed,
    message: parts.join("; ") + ".",
  });
}
