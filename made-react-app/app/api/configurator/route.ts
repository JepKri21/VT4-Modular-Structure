import { NextResponse } from "next/server";

export async function GET() {
  try {
    const res = await fetch("http://localhost:2001/api/inventory");
    if (!res.ok) {
      return NextResponse.json({ error: "Failed to fetch inventory" }, { status: 500 });
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}