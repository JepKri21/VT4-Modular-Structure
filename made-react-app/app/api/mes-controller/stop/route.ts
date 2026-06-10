import { NextResponse } from "next/server";
import { stopRunner, MES_API_ID } from "@/lib/process-registry";

export async function POST() {
  const result = await stopRunner(MES_API_ID);

  if (!result.ok) {
    return NextResponse.json(result, { status: 404 });
  }

  return NextResponse.json(result);
}
