import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import yaml from "js-yaml";

import { getGeneratorPath } from "@/lib/aas-config";

const PRESETS_DIR = path.join(getGeneratorPath(), "shell_presets");

export async function POST(req: Request) {
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
  const { searchParams } = new URL(req.url);
  const shellFilter = searchParams.get("shell"); // e.g. "component_shell"

  try {
    const files = fs
      .readdirSync(PRESETS_DIR)
      .filter((f) => f.endsWith(".yaml") || f.endsWith(".yml"));

    const presets = files
      .map((file) => {
        const raw = fs.readFileSync(path.join(PRESETS_DIR, file), "utf-8");
        const doc = yaml.load(raw) as Record<string, unknown>;
        return {
          filename: path.basename(file, path.extname(file)),
          shell: String(doc.shell ?? ""),
          label: String(doc.label ?? file),
          description: String(doc.description ?? ""),
          asset_name: String(doc.asset_name ?? ""),
          asset_category: String(doc.asset_category ?? ""),
        };
      })
      .filter((p) => !shellFilter || p.shell === shellFilter);

    return NextResponse.json(presets);
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
