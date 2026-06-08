import { NextRequest, NextResponse } from "next/server";
import { getProcessLogs } from "@/lib/process-registry";

export async function GET(req: NextRequest) {
  const shellId = req.nextUrl.searchParams.get("shellId");
  if (!shellId) {
    return NextResponse.json({ error: "shellId required" }, { status: 400 });
  }
  return NextResponse.json({ lines: getProcessLogs(shellId) });
}
