import { NextRequest, NextResponse } from "next/server";
import { getMesApiConfig, saveMesApiConfig } from "@/lib/aas-config";

export async function GET() {
  const cfg = getMesApiConfig();
  return NextResponse.json(cfg);
}

export async function POST(req: NextRequest) {
  const body = (await req.json()) as { scriptPath?: string; pythonExe?: string; port?: number };
  const { scriptPath = "", pythonExe = "python", port = 8000 } = body;
  saveMesApiConfig(scriptPath.trim(), pythonExe.trim(), port);
  return NextResponse.json({ ok: true });
}
