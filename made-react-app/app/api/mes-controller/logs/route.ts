import { NextResponse } from "next/server";
import { getProcessLogs, MES_API_ID } from "@/lib/process-registry";

export async function GET() {
  return NextResponse.json({ lines: getProcessLogs(MES_API_ID) });
}
