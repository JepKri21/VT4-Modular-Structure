import { NextRequest, NextResponse } from "next/server";
import { getProcessLogs, LINE_CONTROLLER_ID } from "@/lib/process-registry";

export async function GET(req: NextRequest) {
  // ?limit=N caps to the last N lines; ?limit=0 returns the full history.
  const raw = req.nextUrl.searchParams.get("limit");
  const limit = raw === null ? undefined : Number(raw);
  const maxLines = limit === undefined || Number.isNaN(limit) ? undefined : limit;
  return NextResponse.json({ lines: getProcessLogs(LINE_CONTROLLER_ID, maxLines) });
}
