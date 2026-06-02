import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

// Detail view for a single resource. Drives the side-panel drill-down.
//
//   - jobs: last 50 JobResults in the window (for cycle-time chart and
//           recent-jobs table)
//   - current_states: latest PackML state per actor + when it took effect
//
// Query params:
//   window: "1h" | "24h" | "7d"        (default "1h")

type Window = "1h" | "24h" | "7d";
const WINDOW_MS: Record<Window, number> = {
  "1h": 60 * 60 * 1000,
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
};

export async function GET(
  req: Request,
  context: { params: Promise<{ resource_id: string }> },
) {
  const { resource_id } = await context.params;
  const { searchParams } = new URL(req.url);
  const w = (searchParams.get("window") ?? "1h") as Window;
  const windowMs = WINDOW_MS[w] ?? WINDOW_MS["1h"];

  const now = Date.now();
  const start = new Date(now - windowMs);
  const end = new Date(now);

  const jobsSql = `
    SELECT
      actor_name,
      order_id,
      job_id,
      ideal_cycle_time_ms,
      actual_cycle_time_ms,
      result,
      quality,
      completed_at
    FROM job_results
    WHERE resource_id = $1
      AND completed_at >= $2
      AND completed_at < $3
    ORDER BY completed_at DESC
    LIMIT 50
  `;

  // Latest state per actor — could be inside or before the window.
  const statesSql = `
    SELECT DISTINCT ON (actor_name)
      actor_name, state, ts
    FROM state_transitions
    WHERE resource_id = $1
    ORDER BY actor_name, ts DESC
  `;

  const [jobsRes, statesRes] = await Promise.all([
    pool.query(jobsSql, [resource_id, start, end]),
    pool.query(statesSql, [resource_id]),
  ]);

  const jobs = jobsRes.rows.map((r) => ({
    actor_name: r.actor_name,
    order_id: r.order_id,
    job_id: r.job_id,
    ideal_cycle_time_ms: r.ideal_cycle_time_ms,
    actual_cycle_time_ms: r.actual_cycle_time_ms,
    result: r.result,
    quality: r.quality,
    completed_at: new Date(r.completed_at).toISOString(),
  }));

  const current_states = statesRes.rows.map((r) => ({
    actor_name: r.actor_name,
    state: r.state,
    since: new Date(r.ts).toISOString(),
  }));

  return NextResponse.json({
    resource_id,
    window: w,
    start: start.toISOString(),
    end: end.toISOString(),
    jobs,
    current_states,
  });
}
