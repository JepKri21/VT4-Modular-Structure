import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { calculateOEE } from "@/lib/oee";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const hours = Number(searchParams.get("hours") || 24);

  const result = await pool.query(
    `
    SELECT *
    FROM production_jobs
    WHERE timestamp >= NOW() - ($1 * INTERVAL '1 hour')
    `,
    [hours],
  );

  const rows = result.rows;

  if (!rows.length) {
    return NextResponse.json({
      station: "Production Line 1",
      A: 0,
      P: 0,
      Q: 0,
      OEE: 0,
      totalParts: 0,
    });
  }

  const logs = rows.map((r) => ({
    start_time: r.timestamp,
    end_time: new Date(new Date(r.timestamp).getTime() + r.cycle_time_ms),
    status: r.result,
    good_count: r.quality === "OK" ? 1 : 0,
    reject_count: r.quality === "OK" ? 0 : 1,
  }));

  const idealCycleSec = rows[0].ideal_cycle_time_ms / 1000;

  const { A, P, Q, OEE } = calculateOEE(logs, idealCycleSec);

  return NextResponse.json({
    station: "Production Line 1",
    A,
    P,
    Q,
    OEE,
    totalParts: rows.length,
  });
}
