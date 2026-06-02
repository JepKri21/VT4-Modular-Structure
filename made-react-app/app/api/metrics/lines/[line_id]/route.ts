import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

// Detail view for a single line. Drives the line side-panel drill-down.
//
//   - orders: count completed / aborted, throughput (orders / hour)
//   - lead_time_ms: { avg, p50, p95 } over the window
//   - attempt_distribution: histogram of attempt_count values (resilience signal)
//   - recent_orders: last 20 orders

type Window = "1h" | "24h" | "7d";
const WINDOW_MS: Record<Window, number> = {
  "1h": 60 * 60 * 1000,
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
};

export async function GET(
  req: Request,
  context: { params: Promise<{ line_id: string }> },
) {
  const { line_id } = await context.params;
  const { searchParams } = new URL(req.url);
  const w = (searchParams.get("window") ?? "1h") as Window;
  const windowMs = WINDOW_MS[w] ?? WINDOW_MS["1h"];

  const now = Date.now();
  const start = new Date(now - windowMs);
  const end = new Date(now);

  // Single query that gathers everything line-scoped from order_completions.
  const ordersSql = `
    WITH win AS (
      SELECT
        order_id,
        product_ref,
        started_at,
        completed_at,
        status,
        attempt_count,
        EXTRACT(EPOCH FROM (completed_at - started_at)) * 1000 AS lead_ms
      FROM order_completions
      WHERE line_id = $1
        AND completed_at >= $2
        AND completed_at < $3
    )
    SELECT
      (SELECT COUNT(*) FROM win WHERE status = 'COMPLETED')           AS completed,
      (SELECT COUNT(*) FROM win WHERE status = 'ABORTED')             AS aborted,
      (SELECT AVG(lead_ms)::bigint FROM win WHERE status = 'COMPLETED') AS lead_avg_ms,
      (SELECT (percentile_cont(0.5) WITHIN GROUP (ORDER BY lead_ms))::bigint
         FROM win WHERE status = 'COMPLETED')                          AS lead_p50_ms,
      (SELECT (percentile_cont(0.95) WITHIN GROUP (ORDER BY lead_ms))::bigint
         FROM win WHERE status = 'COMPLETED')                          AS lead_p95_ms;
  `;

  const distSql = `
    SELECT attempt_count, COUNT(*) AS n
    FROM order_completions
    WHERE line_id = $1 AND completed_at >= $2 AND completed_at < $3
    GROUP BY attempt_count
    ORDER BY attempt_count
  `;

  const recentSql = `
    SELECT order_id, product_ref, started_at, completed_at, status, attempt_count
    FROM order_completions
    WHERE line_id = $1 AND completed_at >= $2 AND completed_at < $3
    ORDER BY completed_at DESC
    LIMIT 20
  `;

  const [aggRes, distRes, recentRes] = await Promise.all([
    pool.query(ordersSql, [line_id, start, end]),
    pool.query(distSql, [line_id, start, end]),
    pool.query(recentSql, [line_id, start, end]),
  ]);

  const agg = aggRes.rows[0] ?? {};
  const completed = Number(agg.completed) || 0;
  const aborted = Number(agg.aborted) || 0;
  const windowHours = (end.getTime() - start.getTime()) / 3_600_000;

  return NextResponse.json({
    line_id,
    window: w,
    start: start.toISOString(),
    end: end.toISOString(),
    orders: {
      completed,
      aborted,
      throughput_per_hour:
        windowHours > 0 ? +(completed / windowHours).toFixed(2) : 0,
    },
    lead_time_ms: {
      avg: agg.lead_avg_ms !== null ? Number(agg.lead_avg_ms) : null,
      p50: agg.lead_p50_ms !== null ? Number(agg.lead_p50_ms) : null,
      p95: agg.lead_p95_ms !== null ? Number(agg.lead_p95_ms) : null,
    },
    attempt_distribution: distRes.rows.map((r) => ({
      attempt_count: Number(r.attempt_count),
      n: Number(r.n),
    })),
    recent_orders: recentRes.rows.map((r) => ({
      order_id: r.order_id,
      product_ref: r.product_ref,
      started_at: new Date(r.started_at).toISOString(),
      completed_at: new Date(r.completed_at).toISOString(),
      status: r.status,
      attempt_count: Number(r.attempt_count),
    })),
  });
}
