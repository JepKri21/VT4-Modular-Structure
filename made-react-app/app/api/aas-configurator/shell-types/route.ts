import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import yaml from "js-yaml";

import { getGeneratorPath } from "@/lib/aas-config";

const SHELL_DIR = path.join(getGeneratorPath(), "shell_templates");
const SUBMODEL_DIR = path.join(getGeneratorPath(), "submodel_templates");

interface RawShellSubmodel {
  template_id: string;
  id_short: string;
  description: string;
  required: boolean;
}

interface RawShell {
  kind: string;
  description: string;
  id_pattern: string;
  id_short_pattern: string;
  global_asset_id_pattern: string;
  submodels: RawShellSubmodel[];
}

// Build an index: template id URI → submodel filename (without extension)
function buildSubmodelIndex(): Record<string, string> {
  const index: Record<string, string> = {};
  const files = fs
    .readdirSync(SUBMODEL_DIR)
    .filter((f) => f.endsWith(".yaml") || f.endsWith(".yml"));

  for (const file of files) {
    try {
      const raw = fs.readFileSync(path.join(SUBMODEL_DIR, file), "utf-8");
      const doc = yaml.load(raw) as Record<string, unknown>;
      if (doc?.id) {
        index[String(doc.id)] = path.basename(file, path.extname(file));
      }
    } catch {
      // skip unreadable files
    }
  }
  return index;
}

export async function GET() {
  try {
    const submodelIndex = buildSubmodelIndex();

    const shellFiles = fs
      .readdirSync(SHELL_DIR)
      .filter((f) => f.endsWith(".yaml") || f.endsWith(".yml"));

    // Pass 1: separate abstract blueprints from category type shells
    interface BlueprintEntry { name: string; doc: Record<string, unknown>; }
    interface CategoryEntry  { name: string; label: string; description: string; blueprintRef: string; }

    const blueprints: BlueprintEntry[] = [];
    const typeShells: CategoryEntry[]  = [];

    for (const file of shellFiles) {
      const raw = fs.readFileSync(path.join(SHELL_DIR, file), "utf-8");
      const doc = yaml.load(raw) as Record<string, unknown>;
      const name = path.basename(file, path.extname(file));
      const label = name
        .replace(/_shell$/, "")
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase());

      if (Array.isArray(doc.submodels)) {
        blueprints.push({ name, doc });
      } else if (typeof doc.shell === "string") {
        typeShells.push({ name, label, description: String(doc.description ?? ""), blueprintRef: doc.shell });
      }
    }

    // Pass 2: build each blueprint entry with its matching categories attached
    const shells = blueprints.map(({ name, doc }) => {
      const label = name
        .replace(/_shell$/, "")
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase());

      const submodels = (doc.submodels as RawShellSubmodel[]).map((sm) => ({
        template_id: sm.template_id,
        id_short: sm.id_short,
        description: sm.description,
        required: sm.required ?? true,
        template_file: submodelIndex[sm.template_id] ?? null,
      }));

      const categories = typeShells
        .filter((ts) => ts.blueprintRef === name)
        .map(({ name: n, label: l, description: d }) => ({ name: n, label: l, description: d }));

      return {
        name,
        label,
        description: String(doc.description ?? ""),
        kind: String(doc.kind ?? "Type"),
        id_pattern: String(doc.id_pattern ?? ""),
        id_short_pattern: String(doc.id_short_pattern ?? ""),
        global_asset_id_pattern: String(doc.global_asset_id_pattern ?? ""),
        submodels,
        categories,
      };
    });

    return NextResponse.json(shells);
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
