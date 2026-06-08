import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

// Summary stats the scheduling page uses to project delivery times.
// The estimate is intentionally crude: average COMPLETED lead time from
// the last 24 h, multiplied by the order's queue position divided by
// MES_MAX_CONCURRENT (defaults to 2 here — keep in sync with dispatcher).
// Returns avg_lead_ms = null until at least one completed order exists.

const MES_MAX_CONCURRENT = Number(
  process.env.MES_MAX_CONCURRENT_HINT ?? "2",
);

export async function GET() {
  const sql = `
    SELECT
      AVG(EXTRACT(EPOCH FROM (completed_at - started_at)) * 1000)::bigint
        AS avg_lead_ms,
      COUNT(*)::int AS sample_size
    FROM order_completions
    WHERE status = 'COMPLETED'
      AND completed_at >= NOW() - INTERVAL '24 hours'
  `;
  const res = await pool.query(sql);
  const row = res.rows[0] ?? {};
  return NextResponse.json({
    avg_lead_ms: row.avg_lead_ms !== null ? Number(row.avg_lead_ms) : null,
    sample_size: Number(row.sample_size) || 0,
    max_concurrent: MES_MAX_CONCURRENT,
  });
}
