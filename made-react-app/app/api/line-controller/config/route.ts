import { NextRequest, NextResponse } from "next/server";
import { getLineControllerConfig, saveLineControllerConfig } from "@/lib/aas-config";

export async function GET() {
  const cfg = getLineControllerConfig();
  return NextResponse.json(cfg);
}

export async function POST(req: NextRequest) {
  const body = (await req.json()) as { scriptPath?: string; pythonExe?: string };
  const { scriptPath = "", pythonExe = "python" } = body;
  saveLineControllerConfig(scriptPath.trim(), pythonExe.trim());
  return NextResponse.json({ ok: true });
}
