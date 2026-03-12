import { NextRequest, NextResponse } from "next/server";

export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ orderId: string }> }
) {
  const { orderId } = await params;
  try {
    const res = await fetch(
      `http://localhost:2002/api/v4/orders/${orderId}/release`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { error: "Could not reach the configurator API" },
      { status: 502 }
    );
  }
}
