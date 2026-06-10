import { NextResponse } from "next/server";
import { stopRunner, LINE_CONTROLLER_ID } from "@/lib/process-registry";

export async function POST() {
  const result = await stopRunner(LINE_CONTROLLER_ID);

  if (!result.ok) {
    return NextResponse.json(result, { status: 404 });
  }

  return NextResponse.json(result);
}
