import { NextResponse } from "next/server";
import { readPresetBom } from "@/lib/presetBom";

// GET — preset-derived BOM tree. Single source of truth: the YAML
// presets edited via the AAS Configurator. Read-only here; mutations
// happen in the Configurator.

export async function GET() {
  try {
    const entries = await readPresetBom();
    return NextResponse.json({ entries });
  } catch (err) {
    return NextResponse.json(
      { error: String(err) },
      { status: 500 },
    );
  }
}
