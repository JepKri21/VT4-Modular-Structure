import { NextResponse } from "next/server";
import { startLineController } from "@/lib/process-registry";

export async function POST() {
  const result = await startLineController();

  if (!result.ok) {
    return NextResponse.json(result, { status: result.error === "Already running" ? 409 : 400 });
  }

  return NextResponse.json(result);
}
