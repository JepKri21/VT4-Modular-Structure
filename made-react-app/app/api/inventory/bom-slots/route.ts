import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import yaml from "js-yaml";
import { getGeneratorPath } from "@/lib/aas-config";

interface RawBomEntry {
  Description?: string;
  Quantity?: number;
  Required?: boolean;
  ProductFamilyRef?: string;
  // Per-unit template markers (fuse sub-assembly). When present, MinQuantity/
  // MaxQuantity are the authoritative slot bounds rather than the summed Quantity.
  PerFuseUnit?: boolean;
  MinQuantity?: number;
  MaxQuantity?: number;
}

export interface BomSlotDef {
  id: string;
  label: string;
  description: string;
  required: boolean;
  categoryFilter: string;
  minQuantity: number;
  maxQuantity: number;
}

// ── helpers ──────────────────────────────────────────────────────────────

function categoryFromIri(iri: string): string | null {
  const after = iri.replace(/^https?:\/\/[^/]+\/Shells\//, "");
  const parts = after.split("/").filter(Boolean);
  // parts[0] = shell class (e.g. "Component"), parts[1] = category
  if (parts.length < 2) return null;
  return parts[1].replace(/_/g, " ");
}

function slotsFromEntries(entries: RawBomEntry[]): BomSlotDef[] {
  const grouped = new Map<
    string,
    { label: string; description: string; required: boolean; minQuantity: number; maxQuantity: number; categoryFilter: string; explicitBounds: boolean }
  >();

  for (const entry of entries) {
    if (!entry.ProductFamilyRef) continue;
    const category = categoryFromIri(entry.ProductFamilyRef);
    if (!category) continue;

    const id = category.toLowerCase().replace(/\s+/g, "_");
    const qty = entry.Quantity ?? 1;
    // A per-unit template entry (e.g. fuse) carries the authoritative bounds in
    // Min/MaxQuantity — use them verbatim instead of summing Quantity.
    const hasExplicitBounds = entry.PerFuseUnit === true || entry.MaxQuantity != null;

    if (grouped.has(id)) {
      const existing = grouped.get(id)!;
      if (hasExplicitBounds) {
        existing.minQuantity = entry.MinQuantity ?? existing.minQuantity;
        existing.maxQuantity = entry.MaxQuantity ?? existing.maxQuantity;
        existing.explicitBounds = true;
      } else if (!existing.explicitBounds) {
        existing.maxQuantity += qty;
      }
      if (entry.Required) existing.required = true;
    } else {
      grouped.set(id, {
        label: category,
        description: entry.Description ?? category,
        required: entry.Required ?? false,
        minQuantity: hasExplicitBounds ? (entry.MinQuantity ?? 1) : 1,
        maxQuantity: hasExplicitBounds ? (entry.MaxQuantity ?? qty) : qty,
        categoryFilter: category,
        explicitBounds: hasExplicitBounds,
      });
    }
  }

  return Array.from(grouped.entries()).map(
    ([id, { explicitBounds: _ignore, ...slot }]) => ({ id, ...slot }),
  );
}

// ── AAS server helpers ────────────────────────────────────────────────────

type AasElement = Record<string, unknown>;
type AasQualifier = { type?: string; value?: string; kind?: string };

function getCollection(elements: unknown[], idShort: string): unknown[] | undefined {
  if (!Array.isArray(elements)) return undefined;
  const col = elements.find((e) => (e as AasElement).idShort === idShort) as AasElement | undefined;
  return Array.isArray(col?.value) ? (col!.value as unknown[]) : undefined;
}

function findChild(children: unknown[], idShort: string): AasElement | undefined {
  return children.find((c) => (c as AasElement).idShort === idShort) as AasElement | undefined;
}

function qualifierValue(el: AasElement, qualType: string): string | undefined {
  if (!Array.isArray(el.qualifiers)) return undefined;
  const q = (el.qualifiers as AasQualifier[]).find((q) => q.type === qualType);
  return q?.value;
}

// Handles plain string/number values AND BaSyx ReferenceElement objects:
// { type: "ExternalReference", keys: [{ type: "GlobalReference", value: "https://..." }] }
function resolveValue(el: AasElement): string | undefined {
  const val = el.value;
  if (typeof val === "string") return val;
  if (typeof val === "number") return String(val);
  if (val && typeof val === "object") {
    const keys = (val as Record<string, unknown>).keys;
    if (Array.isArray(keys) && keys.length > 0) {
      const first = (keys[0] as Record<string, unknown>).value;
      if (typeof first === "string") return first;
    }
  }
  return undefined;
}

function parseBomFromSubmodelElements(submodelElements: unknown[]): RawBomEntry[] {
  const bomEntries = getCollection(submodelElements, "BOMEntries");
  if (!bomEntries) return [];

  return bomEntries.map((entry) => {
    const el = entry as AasElement;
    const children = Array.isArray(el.value) ? (el.value as unknown[]) : [];

    // Required: derived from "cardinality" TEMPLATE_QUALIFIER on the entry collection.
    // "One" / "OneToMany" → required; "ZeroToOne" / "ZeroToMany" → optional.
    const cardinality = qualifierValue(el, "cardinality");
    const required =
      cardinality === "One" || cardinality === "OneToMany"
        ? true
        : cardinality === "ZeroToOne" || cardinality === "ZeroToMany"
        ? false
        : false;

    // Quantity: templates use a Range element (el.min / el.max) or qualifiers
    // (range_min / range_max) on the property, or fall back to a plain value.
    let quantity = 1;
    const qtyEl = findChild(children, "Quantity");
    if (qtyEl) {
      if (qtyEl.max !== undefined) {
        // Range element
        quantity = parseFloat(String(qtyEl.max)) || 1;
      } else if (Array.isArray(qtyEl.qualifiers)) {
        const rangeMax = qualifierValue(qtyEl, "range_max");
        const rangeMin = qualifierValue(qtyEl, "range_min");
        quantity = parseFloat(rangeMax ?? rangeMin ?? "1") || 1;
      } else {
        quantity = parseFloat(resolveValue(qtyEl) ?? "1") || 1;
      }
    }

    // ProductFamilyRef: may be a ReferenceElement (value is an object) or a plain property.
    const refEl = findChild(children, "ProductFamilyRef");
    const productFamilyRef = refEl ? resolveValue(refEl) : undefined;

    const descEl = findChild(children, "Description");
    const description = descEl ? resolveValue(descEl) : undefined;

    return {
      Description: description,
      Quantity: quantity,
      Required: required,
      ProductFamilyRef: productFamilyRef,
    };
  });
}

async function fetchBomFromServer(serverUrl: string): Promise<BomSlotDef[] | null> {
  const base = serverUrl.replace(/\/$/, "");

  const shells: AasElement[] = [];
  let cursor: string | undefined;
  do {
    const url = cursor
      ? `${base}/shells?limit=100&cursor=${encodeURIComponent(cursor)}`
      : `${base}/shells?limit=100`;
    const shellsRes = await fetch(url);
    if (!shellsRes.ok) return null;
    const data = (await shellsRes.json()) as { result?: AasElement[]; paging_metadata?: { cursor?: string } };
    const page = data.result ?? (Array.isArray(data) ? (data as unknown as AasElement[]) : []);
    shells.push(...page);
    cursor = data.paging_metadata?.cursor;
  } while (cursor);

  for (const shell of shells) {
    const shellId = shell.id as string | undefined;
    if (!shellId) continue;

    // Skip component shells — only final product shells have a BOM
    if (shellId.includes("/Shells/Component/")) continue;

    const slots = await tryFetchBomSubmodel(base, shellId);
    if (slots && slots.length > 0) return slots;
  }

  return null;
}

async function tryFetchBomSubmodel(base: string, shellId: string): Promise<BomSlotDef[] | null> {
  try {
    // BaSyx submodel ID convention used in this project
    const submodelId = `${shellId}/Submodel/BillOfMaterials/0`;
    const encoded = Buffer.from(submodelId).toString("base64url");
    const res = await fetch(`${base}/submodels/${encoded}`);
    if (!res.ok) return null;

    const submodel = (await res.json()) as { submodelElements?: unknown[] };
    if (!Array.isArray(submodel.submodelElements)) return null;

    const entries = parseBomFromSubmodelElements(submodel.submodelElements);
    if (!entries.length) return null;

    return slotsFromEntries(entries);
  } catch {
    return null;
  }
}

// ── local YAML fallback ───────────────────────────────────────────────────

type YamlDoc = Record<string, unknown>;

function loadAllPresets(presetsDir: string): YamlDoc[] {
  return fs
    .readdirSync(presetsDir)
    .filter((f) => f.endsWith(".yaml") || f.endsWith(".yml"))
    .map((f) => {
      try {
        return yaml.load(fs.readFileSync(path.join(presetsDir, f), "utf-8")) as YamlDoc;
      } catch {
        return null;
      }
    })
    .filter((d): d is YamlDoc => d !== null);
}

function findPresetByAssetName(presets: YamlDoc[], assetName: string): YamlDoc | null {
  return presets.find((d) => d.asset_name === assetName) ?? null;
}

/** Recursively collect raw-component BOM entries from a preset and all sub-assembly presets. */
function collectRawEntries(
  doc: YamlDoc,
  allPresets: YamlDoc[],
  visited = new Set<string>(),
): RawBomEntry[] {
  const assetName = doc.asset_name as string | undefined;
  if (assetName) {
    if (visited.has(assetName)) return [];
    visited.add(assetName);
  }

  const entries = (
    (doc as Record<string, Record<string, Record<string, unknown>>>)
      ?.submodels?.BillOfMaterials?.BOMEntries ?? []
  ) as Record<string, unknown>[];

  const result: RawBomEntry[] = [];

  for (const entry of entries) {
    // YAML uses ComponentTypeReference; fall back to ProductFamilyRef for old-style presets
    const iri = (entry.ComponentTypeReference ?? entry.ProductFamilyRef) as string | undefined;
    if (!iri) continue;

    const isSubAssembly = entry.IsSubAssembly === true || iri.includes("/Shells/Assembly/");

    if (isSubAssembly) {
      const subAssetName = iri.split("/").pop() ?? "";
      const subPreset = findPresetByAssetName(allPresets, subAssetName);
      if (subPreset) {
        result.push(...collectRawEntries(subPreset, allPresets, visited));
      }
    } else {
      result.push({
        Description: entry.Description as string | undefined,
        Quantity: entry.Quantity as number | undefined,
        Required: entry.Required as boolean | undefined,
        PerFuseUnit: entry.PerFuseUnit as boolean | undefined,
        MinQuantity: entry.MinQuantity as number | undefined,
        MaxQuantity: entry.MaxQuantity as number | undefined,
        ProductFamilyRef: iri,
      });
    }
  }

  return result;
}

function slotsFromLocalYaml(): BomSlotDef[] | null {
  try {
    const presetsDir = path.join(getGeneratorPath(), "shell_presets");
    const allPresets = loadAllPresets(presetsDir);

    // Find the final product preset
    const finalPreset = allPresets.find((d) => d.shell === "final_product_shell");
    if (!finalPreset) return null;

    // Recursively collect all raw component BOM entries from the full hierarchy
    const rawEntries = collectRawEntries(finalPreset, allPresets);
    return rawEntries.length ? slotsFromEntries(rawEntries) : null;
  } catch {
    return null;
  }
}

// ── route ─────────────────────────────────────────────────────────────────

export async function GET(req: NextRequest) {
  const serverUrl = new URL(req.url).searchParams.get("serverUrl");

  // Try AAS server first if a URL was provided
  if (serverUrl) {
    try {
      const slots = await fetchBomFromServer(serverUrl);
      if (slots && slots.length > 0) {
        return NextResponse.json(slots);
      }
    } catch {
      // fall through to local YAML
    }
  }

  // Fall back to local YAML preset
  const slots = slotsFromLocalYaml();
  if (slots && slots.length > 0) {
    return NextResponse.json(slots);
  }

  return NextResponse.json(
    { error: "No final product BOM found on AAS server or in local presets." },
    { status: 404 }
  );
}
