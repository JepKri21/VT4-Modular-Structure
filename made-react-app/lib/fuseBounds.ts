// Single source of truth for how many fuses a phone may have.
//
// The bounds live in the fuse sub-assembly preset YAML
// (shell_presets/*.yaml) on the BOM entry flagged `PerFuseUnit: true`, as
// `MinQuantity` / `MaxQuantity`. Both the webstore UI (slot stepper) and the
// order API read them through here so the allowed range is defined in exactly
// one place — the template — and the backend MES clamps to the same values.

import fs from "fs";
import path from "path";
import yaml from "js-yaml";
import { getGeneratorPath } from "@/lib/aas-config";

export interface FuseBounds {
  min: number;
  max: number;
}

// Used when no PerFuseUnit entry is found (e.g. presets dir unreadable). At
// least one fuse, no hard upper bound — the UI/stock checks still apply.
const DEFAULT_BOUNDS: FuseBounds = { min: 1, max: Number.POSITIVE_INFINITY };

export function getFuseBounds(): FuseBounds {
  try {
    const presetsDir = path.join(getGeneratorPath(), "shell_presets");
    for (const file of fs.readdirSync(presetsDir)) {
      if (!file.endsWith(".yaml") && !file.endsWith(".yml")) continue;
      let doc: Record<string, unknown>;
      try {
        doc = yaml.load(fs.readFileSync(path.join(presetsDir, file), "utf-8")) as Record<string, unknown>;
      } catch {
        continue;
      }
      const entries =
        ((doc as Record<string, Record<string, Record<string, unknown>>>)
          ?.submodels?.BillOfMaterials?.BOMEntries as Record<string, unknown>[] | undefined) ?? [];
      const fuseTemplate = entries.find((e) => e.PerFuseUnit === true);
      if (fuseTemplate) {
        const min = Number(fuseTemplate.MinQuantity ?? 1);
        const max = Number(fuseTemplate.MaxQuantity ?? DEFAULT_BOUNDS.max);
        return { min: Math.max(1, min), max: Math.max(min, max) };
      }
    }
  } catch {
    // fall through to defaults
  }
  return DEFAULT_BOUNDS;
}
