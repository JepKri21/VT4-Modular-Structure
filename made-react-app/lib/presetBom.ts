// Read all `shell_presets/*.yaml`, derive each preset's parent IRI from
// its shell type + asset_type, and surface its BillOfMaterials.BOMEntries
// as a tree the MRP run can explode through.
//
// Shared between /api/mrp/bom (UI) and /api/mrp/run (engine) so both
// always see the same source of truth.

import fs from "fs/promises";
import path from "path";
import yaml from "js-yaml";

const PRESETS_DIR = path.resolve(
  process.cwd(),
  "..",
  "Implementation2.0",
  "ClassesAndBuilderMethods",
  "BaSyx_AAS_Generator",
  "shell_presets",
);

// Map of `shell:` value → MRP material kind. The Configurator docs list
// three abstract shells; everything else falls through to RAW.
const SHELL_TO_KIND: Record<string, "FINISHED" | "INTERMEDIATE" | "RAW"> = {
  final_product_shell: "FINISHED",
  sub_assembly_shell: "INTERMEDIATE",
  component_shell: "RAW",
};

// Map kind → URL category segment (matches the AAS IRI scheme).
const KIND_TO_CATEGORY: Record<
  "FINISHED" | "INTERMEDIATE" | "RAW",
  string
> = {
  FINISHED: "Product",
  INTERMEDIATE: "Assembly",
  RAW: "Component",
};

export interface BomChild {
  iri: string;            // type-only IRI (no asset name, no UUID)
  description: string;    // human label
  quantity: number;
  is_sub_assembly: boolean;
}

export interface BomEntry {
  parent_iri: string;          // type-only IRI used for BOM lookup
  parent_full_iri: string;     // with asset name, for display / mrp_materials join
  parent_name: string;         // asset_name
  parent_kind: "FINISHED" | "INTERMEDIATE" | "RAW";
  preset_file: string;         // relative filename for debugging
  children: BomChild[];
}

// Inheritance for the `type:` field: when a preset uses `type:` (Configurator's
// shorthand) instead of `shell:`, we look at the type shell to recover the
// underlying abstract shell. To avoid a deep recursive YAML load here, we use
// a simple heuristic on the type-shell filename — "assembly" → INTERMEDIATE,
// "component" → RAW, falling back to RAW. The user can extend by adding the
// abstract `shell:` field directly on a preset, which takes precedence.
function kindFromTypeHint(typeRef: string | undefined): keyof typeof KIND_TO_CATEGORY {
  if (!typeRef) return "RAW";
  const lower = typeRef.toLowerCase();
  if (lower.includes("final_product") || lower.includes("product"))
    return "FINISHED";
  if (lower.includes("assembly") || lower.includes("sub_assembly"))
    return "INTERMEDIATE";
  return "RAW";
}

function presetKind(data: Record<string, unknown>): keyof typeof KIND_TO_CATEGORY {
  const shellField = data.shell as string | undefined;
  if (shellField && SHELL_TO_KIND[shellField]) return SHELL_TO_KIND[shellField];
  return kindFromTypeHint(data.type as string | undefined);
}

function parentIris(data: Record<string, unknown>): {
  type_only: string;
  full: string;
} {
  const assetType = String(data.asset_type ?? "");
  const assetName = String(data.asset_name ?? assetType);
  const category = KIND_TO_CATEGORY[presetKind(data)];
  const base = `https://aausmartlab.org/Shells/${category}/${assetType}`;
  return {
    type_only: base,
    full: `${base}/${assetName}`,
  };
}

function readBomEntries(data: Record<string, unknown>): BomChild[] {
  const submodels = (data.submodels ?? {}) as Record<string, unknown>;
  const bom = (submodels.BillOfMaterials ?? {}) as Record<string, unknown>;
  const entries = bom.BOMEntries as Array<Record<string, unknown>> | undefined;
  if (!Array.isArray(entries)) return [];
  return entries.map((e) => ({
    iri: String(e.ComponentTypeReference ?? ""),
    description: String(e.Description ?? ""),
    quantity: Number(e.Quantity ?? 1),
    is_sub_assembly: Boolean(e.IsSubAssembly),
  }));
}

export async function readPresetBom(): Promise<BomEntry[]> {
  let files: string[];
  try {
    files = await fs.readdir(PRESETS_DIR);
  } catch (err) {
    throw new Error(
      `cannot read presets dir at ${PRESETS_DIR}: ${String(err)}`,
    );
  }
  const out: BomEntry[] = [];
  for (const file of files) {
    if (!file.endsWith(".yaml") && !file.endsWith(".yml")) continue;
    const full = path.join(PRESETS_DIR, file);
    let raw: string;
    try {
      raw = await fs.readFile(full, "utf8");
    } catch {
      continue;
    }
    let data: Record<string, unknown>;
    try {
      data = (yaml.load(raw) ?? {}) as Record<string, unknown>;
    } catch {
      continue;
    }
    const children = readBomEntries(data);
    if (children.length === 0) continue;
    const iris = parentIris(data);
    out.push({
      parent_iri: iris.type_only,
      parent_full_iri: iris.full,
      parent_name: String(data.asset_name ?? data.asset_type ?? ""),
      parent_kind: presetKind(data),
      preset_file: file,
      children,
    });
  }
  return out;
}

// Helper for MRP run: build a lookup by type-only parent IRI so a child
// IRI in another BOM can be exploded recursively.
export function bomByParent(entries: BomEntry[]): Map<string, BomEntry> {
  const m = new Map<string, BomEntry>();
  for (const e of entries) m.set(e.parent_iri, e);
  return m;
}
