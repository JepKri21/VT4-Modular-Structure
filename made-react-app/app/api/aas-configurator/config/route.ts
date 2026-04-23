import { NextRequest, NextResponse } from "next/server";
import { getGeneratorPath, saveGeneratorPath } from "@/lib/aas-config";

export async function GET() {
  return NextResponse.json({ generatorPath: getGeneratorPath() });
}

export async function POST(req: NextRequest) {
  const { generatorPath } = await req.json() as { generatorPath?: string };
  if (!generatorPath?.trim()) {
    return NextResponse.json({ error: "generatorPath is required" }, { status: 400 });
  }
  try {
    saveGeneratorPath(generatorPath.trim());
    return NextResponse.json({ generatorPath: generatorPath.trim() });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
