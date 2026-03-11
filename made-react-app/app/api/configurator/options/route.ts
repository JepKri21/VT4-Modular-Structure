import { NextResponse } from "next/server";

export async function GET() {
  // Proxy to Flask backend for dynamic options
  try {
    const res = await fetch("http://localhost:2002/api/v4/options");
    if (!res.ok) {
      return NextResponse.json({ error: "Failed to fetch options" }, { status: 500 });
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}