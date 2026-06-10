import { NextRequest, NextResponse } from "next/server";

const MES_URL = "http://localhost:8000";

// Prioritize an order in the MES dispatch queue. The webshop order UUID maps to
// the MES batch id "ORD-<first 8 hex, uppercased>" (matching how the order route
// names it). Only PENDING (not-yet-dispatched) rows are affected. Lower priority
// number = dispatched sooner; default is 100, so 0 jumps to the front.
export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ orderId: string }> }
) {
  const { orderId } = await params;
  const batchId = `ORD-${orderId.slice(0, 8).toUpperCase()}`;

  try {
    const res = await fetch(`${MES_URL}/api/v1/orders/${batchId}/priority`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ priority: 0 }),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { error: "Could not reach the MES to prioritize this order." },
      { status: 502 }
    );
  }
}
