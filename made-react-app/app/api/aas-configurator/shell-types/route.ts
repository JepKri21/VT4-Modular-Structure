import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import yaml from "js-yaml";

import { getGeneratorPath } from "@/lib/aas-config";


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

function buildSubmodelIndex(submodelDir: string): Record<string, string> {
  const index: Record<string, string> = {};
  const files = fs
    .readdirSync(submodelDir)
    .filter((f) => f.endsWith(".yaml") || f.endsWith(".yml"));

  for (const file of files) {
    try {
      const raw = fs.readFileSync(path.join(submodelDir, file), "utf-8");
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
  const generatorPath = getGeneratorPath();
  const SHELL_DIR = path.join(generatorPath, "shell_templates");
  const SUBMODEL_DIR = path.join(generatorPath, "submodel_templates");
  try {
    const submodelIndex = buildSubmodelIndex(SUBMODEL_DIR);

    const shellFiles = fs
      .readdirSync(SHELL_DIR)
      .filter((f) => f.endsWith(".yaml") || f.endsWith(".yml"));

    const shells = shellFiles.map((file) => {
      const raw = fs.readFileSync(path.join(SHELL_DIR, file), "utf-8");
      const doc = yaml.load(raw) as RawShell;
      const name = path.basename(file, path.extname(file));

      // Human-readable label from filename: "sub_assembly_shell" → "Sub Assembly Shell"
      const label = name
        .replace(/_shell$/, "")
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase());

      const submodels = (doc.submodels ?? []).map((sm) => ({
        template_id: sm.template_id,
        id_short: sm.id_short,
        description: sm.description,
        required: sm.required ?? true,
        // resolved filename so the frontend can fetch the template
        template_file: submodelIndex[sm.template_id] ?? null,
      }));

      return {
        name,
        label,
        description: doc.description ?? "",
        kind: doc.kind ?? "Type",
        id_pattern: doc.id_pattern ?? "",
        id_short_pattern: doc.id_short_pattern ?? "",
        global_asset_id_pattern: doc.global_asset_id_pattern ?? "",
        submodels,
      };
    });

    return NextResponse.json(shells);
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
