export interface Qualifier {
  type: string;
  value_type: string;
  value: unknown;
  kind: string;
}

export interface TemplateElement {
  type:
    | "property"
    | "collection"
    | "list"
    | "reference_element"
    | "multi_language_property"
    | "range";
  id_short: string;
  semantic_id?: string;
  description?: string;
  cardinality?: string;
  value_type?: string;
  element_type?: string;
  extensible?: boolean;
  entry_template?: string;
  elements?: TemplateElement[];
  qualifiers?: Qualifier[];
  options?: string[];
  /** Pattern like "{AssetName}-{Material}-{Color}" — resolved from context at render and generation time */
  derived?: string;
}

/** Flatten a nested FormData into a single-level { id_short: stringValue } map. */
export function flattenFormData(data: FormData, out: Record<string, string> = {}): Record<string, string> {
  for (const [k, v] of Object.entries(data)) {
    if (v === null || v === undefined) continue;
    if (typeof v === "object" && !Array.isArray(v)) {
      flattenFormData(v as FormData, out);
    } else if (!Array.isArray(v)) {
      out[k] = String(v);
    }
  }
  return out;
}

/** Replace {Token} placeholders in a derived pattern using the provided context map.
 *  Segments separated by - or _ that contain only empty tokens are dropped,
 *  so "{AssetName}-{Material}-{Color}" with no Material/Color gives "FuseBox"
 *  instead of "FuseBox--".
 */
export function resolveDerived(pattern: string, ctx: Record<string, string>): string {
  // Split on separators, resolve each segment, drop blanks, rejoin
  const segments = pattern.split(/(?=[-_])/); // split keeping the separator at the start of each chunk
  const resolved = segments
    .map((seg) => {
      const sep = seg.match(/^[-_]/)?.[0] ?? "";
      const body = sep ? seg.slice(1) : seg;
      // Replace all tokens in this segment body
      const filled = body.replace(/\{(\w+)\}/g, (_, key) => ctx[key] ?? "");
      // Drop the segment entirely if every token resolved to empty
      const hasToken = /\{/.test(body);
      if (hasToken && filled.trim() === "") return "";
      return sep + filled;
    })
    .filter((s) => s !== "");
  // Clean up any leading separators left after drops
  return resolved.join("").replace(/^[-_]+/, "").replace(/[-_]{2,}/g, "-");
}

/** Walk template elements and fill empty derived fields using context. Returns a new FormData. */
export function applyDerivedFields(
  elements: TemplateElement[],
  formData: FormData,
  ctx: Record<string, string>
): FormData {
  const result = { ...formData };
  for (const el of elements) {
    if (el.type === "property" && el.derived) {
      const cur = result[el.id_short];
      if (cur === null || cur === undefined || cur === "") {
        const computed = resolveDerived(el.derived, ctx);
        if (computed) result[el.id_short] = computed;
      }
    } else if (el.type === "collection" && el.elements) {
      const colData = (result[el.id_short] ?? {}) as FormData;
      result[el.id_short] = applyDerivedFields(el.elements, colData, ctx);
    }
  }
  return result;
}

export interface OperationCapability {
  id_short: string;
  template_file: string;
  template_id: string;
}

export interface SubmodelTemplate {
  id_short: string;
  id: string;
  description: string;
  elements: TemplateElement[];
  /** Populated for BOP templates: maps Operation value → required capability slot */
  operations?: Record<string, OperationCapability>;
}

export interface TemplateSummary {
  filename: string;
  name: string;
  id_short: string;
  id: string;
  description: string;
}

// FormData mirrors the template element hierarchy
export type FormValue =
  | string
  | number
  | boolean
  | null
  | LangEntry[]
  | string[]
  | FormData;

export type FormData = {
  [id_short: string]: FormValue | FormData[];
};

export interface LangEntry {
  language: string;
  text: string;
}

export interface ShellPresetSummary {
  filename: string;
  shell: string; // matches ShellType.name
  label: string;
  description: string;
  asset_name: string;
  asset_category: string;
}

export interface ShellPreset extends ShellPresetSummary {
  // submodels keyed by slot id_short → nested FormData-compatible object
  submodels: Record<string, unknown>;
}

/**
 * Deep-merge preset values into existing form data.
 * Preset values only fill fields that are currently null/undefined/empty —
 * user edits are never overwritten.
 */
export function mergePresetIntoForm(
  existing: FormData,
  presetData: Record<string, unknown>
): FormData {
  const result: FormData = { ...existing };
  for (const key of Object.keys(presetData)) {
    const presetVal = presetData[key];
    const existingVal = existing[key];

    if (presetVal === null || presetVal === undefined) continue;

    if (
      typeof presetVal === "object" &&
      !Array.isArray(presetVal) &&
      presetVal !== null
    ) {
      // collection: recurse
      result[key] = mergePresetIntoForm(
        (existingVal as FormData) ?? {},
        presetVal as Record<string, unknown>
      );
    } else if (existingVal === null || existingVal === undefined || existingVal === "") {
      // leaf value: only set if not already filled
      result[key] = presetVal as FormValue;
    }
  }
  return result;
}

export function isOptional(cardinality?: string): boolean {
  const c = (cardinality ?? "One").toLowerCase();
  return c === "zerotoone" || c === "zerotomany";
}

export interface ShellSubmodelSlot {
  template_id: string;
  id_short: string;
  description: string;
  required: boolean;
  template_file: string | null; // submodel template filename without extension
}

export interface ShellType {
  name: string; // filename without extension, e.g. "component_shell"
  label: string; // human-readable, e.g. "Component Shell"
  description: string;
  kind: string; // "Type" | "Instance"
  id_pattern: string;
  id_short_pattern: string;
  global_asset_id_pattern: string;
  submodels: ShellSubmodelSlot[];
}

export function isMany(cardinality?: string): boolean {
  const c = (cardinality ?? "One").toLowerCase();
  return c === "zerotomany" || c === "onetomany";
}
