import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import yaml from "js-yaml";

import { getGeneratorPath } from "@/lib/aas-config";
import { resolvePresetType } from "@/lib/shell-type-utils";

export async function POST(req: Request) {
  const PRESETS_DIR = path.join(getGeneratorPath(), "shell_presets");
  try {
    const body = await req.json() as Record<string, unknown>;
    const { shell, label, description, asset_name, asset_category, submodels, filename } = body as {
      shell: string;
      label: string;
      description?: string;
      asset_name?: string;
      asset_category?: string;
      submodels: Record<string, unknown>;
      filename: string;
    };

    const safeFilename = filename
      .toLowerCase()
      .replace(/[^a-z0-9_-]/g, "_")
      .replace(/_+/g, "_")
      .replace(/^_|_$/g, "");

    const doc = { shell, label, description, asset_name, asset_category, submodels };
    const yamlStr = yaml.dump(doc, { lineWidth: 120, quotingType: '"', noRefs: true });

    fs.writeFileSync(path.join(PRESETS_DIR, `${safeFilename}.yaml`), yamlStr, "utf-8");

    return NextResponse.json({ filename: safeFilename });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

export async function GET(req: Request) {
  const PRESETS_DIR = path.join(getGeneratorPath(), "shell_presets");
  const { searchParams } = new URL(req.url);
  const shellFilter = searchParams.get("shell"); // e.g. "component_shell"

  try {
    const files = fs
      .readdirSync(PRESETS_DIR)
      .filter((f) => f.endsWith(".yaml") || f.endsWith(".yml"));

    const presets = files
      .map((file) => {
        try {
          const raw = fs.readFileSync(path.join(PRESETS_DIR, file), "utf-8");
          const doc = yaml.load(raw) as Record<string, unknown>;
          const originalType = String(doc.type ?? "");
          const resolved = resolvePresetType(doc);
          return {
            filename: path.basename(file, path.extname(file)),
            shell: String(resolved.shell ?? ""),
            type: originalType,
            label: String(resolved.label ?? file),
            description: String(resolved.description ?? ""),
            asset_name: String(resolved.asset_name ?? ""),
            asset_category: String(resolved.asset_category ?? ""),
          };
        } catch (e) {
          console.error(`[presets] Failed to process ${file}:`, e);
          return null;
        }
      })
      .filter((p): p is NonNullable<typeof p> =>
        p !== null && (!shellFilter || p.shell === shellFilter || p.type === shellFilter)
      );

    return NextResponse.json(presets);
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
