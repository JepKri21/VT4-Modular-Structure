import { NextResponse } from "next/server";

export async function GET() {
  try {
    const res = await fetch("http://localhost:2002/api/v4/orders");
    const data = await res.json();
    if (!Array.isArray(data)) {
      return NextResponse.json({ error: "Unexpected response" }, { status: 502 });
    }
    const released = data.filter((o: any) => o.status === "released");
    return NextResponse.json(released);
  } catch {
    return NextResponse.json({ error: "Could not reach configurator API" }, { status: 503 });
  }
}
