import { NextRequest, NextResponse } from "next/server";
import { getResourceRunnerConfig, saveResourceRunnerConfig } from "@/lib/aas-config";

export async function GET() {
  const cfg = getResourceRunnerConfig();
  return NextResponse.json(cfg);
}

export async function POST(req: NextRequest) {
  const body = (await req.json()) as { runnerPath?: string; pythonExe?: string };
  const { runnerPath = "", pythonExe = "python" } = body;
  saveResourceRunnerConfig(runnerPath.trim(), pythonExe.trim());
  return NextResponse.json({ ok: true });
}
