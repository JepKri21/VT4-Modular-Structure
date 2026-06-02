import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

export async function GET() {
  const result = await pool.query(
    `SELECT * FROM alarms
        ORDER BY triggered_at DESC
    LIMIT 100`,
  );
  return NextResponse.json(result.rows);
}
