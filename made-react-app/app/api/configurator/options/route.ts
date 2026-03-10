import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    bottom_cover_materials: { Aluminum: true, Plastic: true },
    bottom_cover_colors: { Black: true, White: true, Blue: true },
    bottom_cover_finishes: { Matte: true, Glossy: true },
    top_cover_materials: { Aluminum: true, Plastic: true },
    top_cover_colors: { Black: true, White: true, Red: true },
    top_cover_finishes: { Matte: true, Glossy: true },
    fuse_counts: { 1: true, 2: true, 3: true }
  });
}