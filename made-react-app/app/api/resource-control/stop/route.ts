import { NextRequest, NextResponse } from "next/server";
import { stopRunner } from "@/lib/process-registry";

export async function POST(req: NextRequest) {
  const body = (await req.json()) as { shellId?: string };
  const { shellId } = body;

  if (!shellId) {
    return NextResponse.json({ ok: false, error: "shellId is required" }, { status: 400 });
  }

  const result = await stopRunner(shellId);

  if (!result.ok) {
    return NextResponse.json(result, { status: 404 });
  }

  return NextResponse.json(result);
}
