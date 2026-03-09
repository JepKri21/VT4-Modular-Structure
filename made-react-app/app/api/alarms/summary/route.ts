import { NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { count } from "console";

export async function GET() {
  const active = await pool.query(
    `SELECT COUNT(*) from station_alarms
        WHERE cleared_at IS NULL
        `,
  );

  const warnings = await pool.query(
    `SELECT COUNT(*) FROM station_alarms
        WHERE severity = 'WARNING'
        AND cleared_at IS NULL`,
  );

  const cleared = await pool.query(
    `SELECT COUNT(*) FROM station_alarms
        WHERE cleared_at IS NOT NULL`,
  );
  const recent = await pool.query(
    `SELECT COUNT(*) FROM station_alarms
        WHERE triggered_at > NOW() - INTERVAL '1 hour'`,
  );

  return NextResponse.json({
    active: Number(active.rows[0].count),
    warnings: Number(warnings.rows[0].count),
    cleared: Number(cleared.rows[0].count),
    recent: Number(recent.rows[0].count),
  });
}
