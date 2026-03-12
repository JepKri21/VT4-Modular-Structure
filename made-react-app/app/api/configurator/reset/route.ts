import { NextResponse } from "next/server";

export async function POST() {
  try {
    const res = await fetch("http://localhost:2002/api/v4/admin/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { error: "Could not reach the configurator API" },
      { status: 502 }
    );
  }
}
