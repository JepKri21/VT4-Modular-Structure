import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    // Flatten nested config {Bottom_Cover: {material: x}} → {bottom_cover_material: x}
    // so the Flask API receives the flat format it expects.
    const flat: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(body)) {
      if (value !== null && typeof value === "object" && !Array.isArray(value)) {
        const prefix = key.toLowerCase();
        for (const [prop, v] of Object.entries(value as Record<string, unknown>)) {
          flat[`${prefix}_${prop}`] = v;
        }
      } else {
        flat[key] = value;
      }
    }

    const res = await fetch("http://localhost:2002/api/v4/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(flat),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Could not reach configurator API" }, { status: 503 });
  }
}
