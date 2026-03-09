import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { calculateOEE } from "@/lib/oee";
import { Result } from "pg";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);

  const station = searchParams.get("station");
  const hours = Number(searchParams.get("hours") || 24);

  if (!station) {
    return NextResponse.json(
      { error: "Missing station parameter" },
      { status: 400 },
    );
  }

  try {
    const result = await pool.query(
      `
      SELECT *
      FROM production_jobs
      WHERE station_id = $1
        AND timestamp >= NOW() - INTERVAL '${hours} hours'
      ORDER BY timestamp ASC
      `,
      [station],
    );

    const rows = result.rows;

    if (!rows.length) {
      return NextResponse.json({
        station,
        totalParts: 0,
        A: 0,
        P: 0,
        Q: 0,
        OEE: 0,
      });
    }

    // Transformér til format som din calculateOEE forventer
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
      station,
      totalParts: rows.length,
      A,
      P,
      Q,
      OEE,
      lastActivity: rows[rows.length - 1].timestamp,
    });
  } catch (error) {
    console.error(error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
