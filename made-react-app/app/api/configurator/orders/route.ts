import { NextResponse } from "next/server";

export async function GET() {
  try {
    const res = await fetch("http://localhost:2002/api/v4/orders");
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "Could not reach configurator API" }, { status: 503 });
  }
}
