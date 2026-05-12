import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import yaml from "js-yaml";

import { getGeneratorPath } from "@/lib/aas-config";
import { resolvePresetType } from "@/lib/shell-type-utils";

const PRESETS_DIR = path.join(getGeneratorPath(), "shell_presets");

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ name: string }> }
) {
  const { name } = await params;
  for (const ext of [".yaml", ".yml"]) {
    const filePath = path.join(PRESETS_DIR, `${name}${ext}`);
    if (fs.existsSync(filePath)) {
      const raw = fs.readFileSync(filePath, "utf-8");
      const doc = yaml.load(raw) as Record<string, unknown>;
      return NextResponse.json(resolvePresetType(doc));
    }
  }
  return NextResponse.json({ error: "Preset not found" }, { status: 404 });
}
