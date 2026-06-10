import { NextResponse } from "next/server";
import { getProcessLogs, LINE_CONTROLLER_ID } from "@/lib/process-registry";

export async function GET() {
  return NextResponse.json({ lines: getProcessLogs(LINE_CONTROLLER_ID) });
}
