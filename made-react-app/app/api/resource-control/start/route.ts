import { NextRequest, NextResponse } from "next/server";
import { startRunner } from "@/lib/process-registry";

export async function POST(req: NextRequest) {
  const body = (await req.json()) as { shellId?: string; serverUrl?: string };
  const { shellId, serverUrl } = body;

  if (!shellId || !serverUrl) {
    return NextResponse.json({ ok: false, error: "shellId and serverUrl are required" }, { status: 400 });
  }

  const result = await startRunner(shellId, serverUrl);

  if (!result.ok) {
    return NextResponse.json(result, { status: result.error === "Already running" ? 409 : 400 });
  }

  return NextResponse.json(result);
}
