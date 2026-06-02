import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

// Per-resource OEE for a time window. One row per resource_id with a
// nested `actors[]` array for per-actor breakdown (so the card drill-down
// already has the data it needs without a second round trip).
//
//   Availability = (window − time_in_DOWN) / window     (per actor, then
//                  averaged across actors of the resource)
//   Performance  = sum(ideal) / sum(actual)             (summed over actors)
//   Quality      = good / total                         (summed over actors)
//
// Query params:
//   window: "1h" | "24h" | "7d"        (default "1h")

type Window = "1h" | "24h" | "7d";
const WINDOW_MS: Record<Window, number> = {
  "1h": 60 * 60 * 1000,
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
};

const DOWN_STATES = ["STOPPED", "STOPPING", "ABORTED", "ABORTING"];

interface ActorRow {
  line_id: string | null;
  resource_id: string;
  actor_name: string;
  availability: number;
  performance: number;
  quality: number;
  oee: number;
  jobs_total: number;
  jobs_good: number;
  latest_activity: string | null;
}

interface ResourceRow {
  line_id: string | null;
  resource_id: string;
  availability: number;
  performance: number;
  quality: number;
  oee: number;
  prev_oee: number;
  jobs_total: number;
  jobs_good: number;
  actor_count: number;
  latest_activity: string | null;
  actors: ActorRow[];
}

// Run the per-actor SQL; the resource-level rollup happens in JS so the
// SQL stays readable.
async function computeActorOee(
  start: Date,
  end: Date,
): Promise<ActorRow[]> {
  const sql = `
    WITH seed AS (
      SELECT DISTINCT ON (line_id, resource_id, actor_name)
        line_id, resource_id, actor_name, state, $1::timestamptz AS ts
      FROM state_transitions
      WHERE ts < $1
      ORDER BY line_id, resource_id, actor_name, ts DESC
    ),
    inwindow AS (
      SELECT line_id, resource_id, actor_name, state, ts
      FROM state_transitions
      WHERE ts >= $1 AND ts < $2
    ),
    combined AS (
      SELECT * FROM seed UNION ALL SELECT * FROM inwindow
    ),
    ordered AS (
      SELECT
        line_id, resource_id, actor_name, state, ts,
        LEAD(ts) OVER (
          PARTITION BY line_id, resource_id, actor_name
          ORDER BY ts
        ) AS next_ts
      FROM combined
    ),
    durations AS (
      SELECT
        line_id, resource_id, actor_name, state,
        EXTRACT(EPOCH FROM (
          LEAST(COALESCE(next_ts, $2::timestamptz), $2::timestamptz)
          - GREATEST(ts, $1::timestamptz)
        )) AS dur_s
      FROM ordered
      WHERE COALESCE(next_ts, $2::timestamptz) > $1::timestamptz
        AND ts < $2::timestamptz
    ),
    avail_per_actor AS (
      SELECT
        line_id, resource_id, actor_name,
        SUM(GREATEST(dur_s, 0)) AS observed_s,
        SUM(CASE WHEN state = ANY($3::text[]) THEN GREATEST(dur_s, 0) ELSE 0 END)
                                AS down_s
      FROM durations
      GROUP BY line_id, resource_id, actor_name
    ),
    job_agg AS (
      SELECT
        line_id, resource_id, actor_name,
        SUM(COALESCE(actual_cycle_time_ms, 0)) AS busy_ms,
        SUM(COALESCE(ideal_cycle_time_ms, 0))  AS ideal_ms,
        COUNT(*)                                AS jobs_total,
        SUM(CASE WHEN quality = 'GOOD' THEN 1 ELSE 0 END) AS jobs_good,
        MAX(completed_at)                       AS latest_activity
      FROM job_results
      WHERE completed_at >= $1 AND completed_at < $2
      GROUP BY line_id, resource_id, actor_name
    ),
    actors AS (
      SELECT line_id, resource_id, actor_name FROM avail_per_actor
      UNION
      SELECT line_id, resource_id, actor_name FROM job_agg
    )
    SELECT
      a.line_id, a.resource_id, a.actor_name,
      av.down_s, j.busy_ms, j.ideal_ms,
      j.jobs_total, j.jobs_good, j.latest_activity
    FROM actors a
    LEFT JOIN avail_per_actor av USING (line_id, resource_id, actor_name)
    LEFT JOIN job_agg          j  USING (line_id, resource_id, actor_name)
    ORDER BY a.line_id, a.resource_id, a.actor_name;
  `;
  const result = await pool.query(sql, [start, end, DOWN_STATES]);
  const windowSeconds = (end.getTime() - start.getTime()) / 1000;

  return result.rows.map((r) => {
    const busy = Number(r.busy_ms) || 0;
    const ideal = Number(r.ideal_ms) || 0;
    const total = Number(r.jobs_total) || 0;
    const good = Number(r.jobs_good) || 0;
    const downS = Number(r.down_s) || 0;

    const availability =
      windowSeconds > 0
        ? Math.min(1, Math.max(0, (windowSeconds - downS) / windowSeconds))
        : 0;
    const performance = busy > 0 ? Math.min(1, ideal / busy) : 0;
    const quality = total > 0 ? good / total : 0;
    const oee = availability * performance * quality;

    return {
      line_id: r.line_id ?? null,
      resource_id: r.resource_id,
      actor_name: r.actor_name,
      availability: Math.round(availability * 100),
      performance: Math.round(performance * 100),
      quality: Math.round(quality * 100),
      oee: Math.round(oee * 100),
      jobs_total: total,
      jobs_good: good,
      latest_activity: r.latest_activity
        ? new Date(r.latest_activity).toISOString()
        : null,
    };
  });
}

// Group actors into resources. Per-resource A/P/Q are derived from the
// actor-level numbers so the rollup math is self-consistent with the
// nested actors[] array each card carries.
function aggregateByResource(
  actorRows: ActorRow[],
): Omit<ResourceRow, "prev_oee">[] {
  const byKey = new Map<string, ActorRow[]>();
  for (const a of actorRows) {
    const key = `${a.line_id ?? ""}|${a.resource_id}`;
    if (!byKey.has(key)) byKey.set(key, []);
    byKey.get(key)!.push(a);
  }

  const out: Omit<ResourceRow, "prev_oee">[] = [];
  for (const actors of byKey.values()) {
    const first = actors[0];

    // Availability across actors = mean. With one actor it equals the
    // actor's availability; with multiple, it represents the "average
    // experience" across the resource's actors.
    const availability =
      actors.reduce((s, a) => s + a.availability, 0) / actors.length;

    // Performance and Quality from raw sums — denominator-friendly so a
    // big-job actor doesn't get drowned out by an idle one.
    const jobsTotal = actors.reduce((s, a) => s + a.jobs_total, 0);
    const jobsGood = actors.reduce((s, a) => s + a.jobs_good, 0);

    // To recompute Performance from already-rounded actor percentages
    // would compound error, so weight by jobs_total instead — close
    // enough for a card-level number. Same for Quality.
    const performance =
      jobsTotal > 0
        ? actors.reduce((s, a) => s + a.performance * a.jobs_total, 0) /
          jobsTotal
        : 0;
    const quality = jobsTotal > 0 ? (jobsGood / jobsTotal) * 100 : 0;

    const oee = (availability * performance * quality) / 10_000;

    const latestActivity = actors
      .map((a) => a.latest_activity)
      .filter((t): t is string => !!t)
      .sort()
      .pop() ?? null;

    out.push({
      line_id: first.line_id,
      resource_id: first.resource_id,
      availability: Math.round(availability),
      performance: Math.round(performance),
      quality: Math.round(quality),
      // `oee` above is already on the 0..100 scale (A*P*Q / 10_000 with
      // each of A/P/Q in 0..100). Just round — don't multiply again.
      oee: Math.round(oee),
      jobs_total: jobsTotal,
      jobs_good: jobsGood,
      actor_count: actors.length,
      latest_activity: latestActivity,
      actors,
    });
  }
  out.sort((a, b) =>
    `${a.line_id}|${a.resource_id}`.localeCompare(`${b.line_id}|${b.resource_id}`),
  );
  return out;
}

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const w = (searchParams.get("window") ?? "1h") as Window;
  const windowMs = WINDOW_MS[w] ?? WINDOW_MS["1h"];

  const now = Date.now();
  const start = new Date(now - windowMs);
  const end = new Date(now);
  const prevStart = new Date(now - 2 * windowMs);
  const prevEnd = start;

  const [currentActors, previousActors] = await Promise.all([
    computeActorOee(start, end),
    computeActorOee(prevStart, prevEnd),
  ]);

  const current = aggregateByResource(currentActors);
  const previous = aggregateByResource(previousActors);

  const prevByKey = new Map<string, number>();
  for (const row of previous) {
    prevByKey.set(`${row.line_id ?? ""}|${row.resource_id}`, row.oee);
  }

  const resources: ResourceRow[] = current.map((r) => ({
    ...r,
    prev_oee: prevByKey.get(`${r.line_id ?? ""}|${r.resource_id}`) ?? 0,
  }));

  return NextResponse.json({
    window: w,
    start: start.toISOString(),
    end: end.toISOString(),
    resources,
  });
}
