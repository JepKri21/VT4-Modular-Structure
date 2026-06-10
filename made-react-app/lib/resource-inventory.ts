/**
 * Reads physical component stock straight from the AAS resource Inventory
 * submodels (`<resourceIri>/Inventory` → `Inventories[].StoredComponents[]`).
 *
 * This is the ground truth for what is available: a component leaves its slot
 * the instant it is picked for an order, so a filled slot = genuinely in stock,
 * and a consumed/aborted part is simply gone. The webshop derives availability
 * from here at read time rather than from a DB mirror that drifts.
 */

// IRI pattern: https://aausmartlab.org/Shells/Component/{Category}/{Type}-{UUID}
const UUID_SUFFIX_RE = /[-_][0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const UUID_SEGMENT_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Derive the component_types id for a component instance IRI, matching the id the
 * sync's shell-scan produces (`{category}_{type}` lowercased). Returns null for
 * anything that is not a `/Shells/Component/` instance (products, sub-assemblies).
 */
export function parseComponentTypeId(iri: string): string | null {
  if (!iri || !iri.includes("/Shells/Component/")) return null;
  const segments = iri.replace("https://aausmartlab.org/Shells/", "").split("/").filter(Boolean);
  const meaningful = segments.filter((s) => !UUID_SEGMENT_RE.test(s));
  const rawLast = meaningful[2] ?? meaningful[meaningful.length - 1] ?? "";
  const typeSegment = rawLast.replace(UUID_SUFFIX_RE, "");
  if (!typeSegment) return null;
  const category = meaningful[1] ?? "unknown";
  return `${category}_${typeSegment}`.toLowerCase().replace(/\s+/g, "_");
}

function findEl(elements: unknown, idShort: string): Record<string, unknown> | undefined {
  if (!Array.isArray(elements)) return undefined;
  return elements.find(
    (e) => (e as Record<string, unknown>)?.idShort === idShort
  ) as Record<string, unknown> | undefined;
}

export type ResourceInventory = {
  resourceId: string;
  resourceName: string;
  capacity: number;
  categories: string[];
  // Physically present component instances (filled slots only).
  filled: Array<{ componentTypeId: string; instanceIri: string; reserved: boolean }>;
};

/**
 * Read every resource's Inventory submodel and return its physical slot contents.
 * Resources without an Inventory submodel (404) are skipped; slots holding a
 * product/sub-assembly (not a `/Shells/Component/` instance) are ignored.
 */
export async function fetchResourceInventories(
  base: string,
  shells: Record<string, unknown>[]
): Promise<ResourceInventory[]> {
  const out: ResourceInventory[] = [];

  for (const shell of shells) {
    const iri = (shell.id as string) ?? "";
    if (!iri.includes("/Shells/Resources/")) continue;
    const assetKind = (shell.assetInformation as Record<string, unknown> | undefined)?.assetKind;
    if (assetKind === "Type") continue;

    const encoded = Buffer.from(`${iri}/Inventory`).toString("base64url");
    let submodel: { submodelElements?: unknown[] };
    try {
      const res = await fetch(`${base}/submodels/${encoded}`);
      if (!res.ok) continue; // 404 → resource has no inventory submodel
      submodel = (await res.json()) as { submodelElements?: unknown[] };
    } catch {
      continue;
    }

    const inventories = findEl(submodel.submodelElements, "Inventories");
    if (!inventories || !Array.isArray(inventories.value)) continue;

    const resourceName = ((shell.idShort as string) ?? iri.split("/").pop() ?? iri).replace(/_/g, " ");
    let capacity = 0;
    const categories = new Set<string>();
    const filled: ResourceInventory["filled"] = [];

    for (const inv of inventories.value as Record<string, unknown>[]) {
      const invChildren = inv.value;

      const specs = findEl(invChildren, "Specifications");
      const sizeEl = specs ? findEl(specs.value, "InventorySize") : undefined;
      const size = sizeEl ? parseInt(String(sizeEl.value), 10) : NaN;
      if (!isNaN(size)) capacity += size;

      const supported = findEl(invChildren, "SupportedComponents");
      if (supported && Array.isArray(supported.value)) {
        for (const item of supported.value as Record<string, unknown>[]) {
          const raw = (item?.value as string) ?? "";
          if (!raw) continue;
          const cat = raw.includes("/")
            ? raw.replace("https://aausmartlab.org/Shells/", "").split("/")[1] ?? ""
            : raw;
          if (cat) categories.add(cat.replace(/_/g, " ").trim());
        }
      }

      const stored = findEl(invChildren, "StoredComponents");
      if (!stored || !Array.isArray(stored.value)) continue;
      for (const slot of stored.value as Record<string, unknown>[]) {
        const ref = findEl(slot.value, "ComponentShellReference");
        const v = ref?.value as { keys?: { value?: string }[] } | undefined;
        const instanceIri = v?.keys?.[0]?.value?.trim();
        if (!instanceIri) continue;
        const componentTypeId = parseComponentTypeId(instanceIri);
        if (!componentTypeId) continue; // products / sub-assemblies → not component stock
        const reservedEl = findEl(slot.value, "SlotReserved");
        const reserved = reservedEl?.value === "true" || reservedEl?.value === true;
        filled.push({ componentTypeId, instanceIri, reserved });
      }
    }

    out.push({ resourceId: iri, resourceName, capacity, categories: Array.from(categories), filled });
  }

  return out;
}

/** Fetch every page of a BaSyx collection endpoint, following the paging cursor. */
export async function fetchAllPaged(base: string, path: string): Promise<Record<string, unknown>[]> {
  const out: Record<string, unknown>[] = [];
  let cursor: string | undefined;
  for (let i = 0; i < 100; i++) {
    const sep = path.includes("?") ? "&" : "?";
    const url = `${base}${path}${sep}limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`;
    const res = await fetch(url);
    if (!res.ok) {
      if (i === 0) throw new Error(`${res.status}: ${await res.text().catch(() => "")}`);
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

/** Resolve the AAS server base URL: explicit arg → env → localhost default. */
export function resolveAasBase(serverUrl?: string | null): string {
  const raw = serverUrl?.trim() || process.env.AAS_BASE || "http://localhost:8081";
  return raw.replace(/\/$/, "");
}

// ── Short-lived cache so rapid webshop reads don't hammer BaSyx ──
const ALLOCATED_TTL_MS = 8_000;
let _cache: { base: string; at: number; data: Map<string, number> } | null = null;

/**
 * Count physically present component instances per component_types id, across all
 * resource inventories. Returns null if the AAS server can't be read at all, so
 * callers can fall back to their DB value instead of zeroing everything out.
 * Result is cached per-base for a few seconds.
 */
export async function allocatedByTypeFromAas(base: string): Promise<Map<string, number> | null> {
  const now = Date.now();
  if (_cache && _cache.base === base && now - _cache.at < ALLOCATED_TTL_MS) {
    return _cache.data;
  }

  let shells: Record<string, unknown>[];
  try {
    shells = await fetchAllPaged(base, "/shells");
  } catch {
    return null; // AAS unreachable → caller keeps its DB value
  }

  const inventories = await fetchResourceInventories(base, shells);
  const counts = new Map<string, number>();
  for (const r of inventories) {
    for (const slot of r.filled) {
      counts.set(slot.componentTypeId, (counts.get(slot.componentTypeId) ?? 0) + 1);
    }
  }

  _cache = { base, at: now, data: counts };
  return counts;
}
