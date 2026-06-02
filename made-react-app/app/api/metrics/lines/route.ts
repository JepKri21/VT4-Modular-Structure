import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

// Per-line OEE roll-up.
//
// Same formulation as the per-resource endpoint:
//   Availability = (window − line_down_time) / window
//     where line_down_time is the time during which ALL of the line's
//     actors are simultaneously in a DOWN state. (Any actor up = line up.)
//   Performance  = sum(ideal)  / sum(actual)   (over all line jobs)
//   Quality      = good / total                (over all line jobs)
//
// Query params:
//   window: "1h" | "24h" | "7d"        (default "1h")

type Window = "1h" | "24h" | "7d";
const WINDOW_MS: Record<Window, number> = {
  "1h": 60 * 60 * 1000,
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
};

const DOWN_STATES = [
  "STOPPED",
  "STOPPING",
  "ABORTED",
  "ABORTING",
];

interface LineRow {
  line_id: string;
  availability: number;
  performance: number;
  quality: number;
  oee: number;
  prev_oee: number;
  jobs_total: number;
  jobs_good: number;
  resource_count: number;
  latest_activity: string | null;
}

async function computeLineOee(
  start: Date,
  end: Date,
): Promise<Omit<LineRow, "prev_oee">[]> {
  // Strategy: compute per-actor down_s exactly like the resource endpoint,
  // then approximate "line down" as the MINIMUM down fraction across the
  // line's actors. Rationale: if the line has 5 actors and only one is
  // STOPPED for an hour, the line itself wasn't down — work could still
  // flow through the other 4. Treating the minimum is closer than the
  // average for a redundant line, while staying simple.
  //
  // Performance and Quality come from straightforward sums.
  const sql = `
    WITH seed AS (
      SELECT DISTINCT ON (line_id, resource_id, actor_name)
        line_id, resource_id, actor_name, state, $1::timestamptz AS ts
      FROM state_transitions
      WHERE ts < $1 AND line_id IS NOT NULL
      ORDER BY line_id, resource_id, actor_name, ts DESC
    ),
    inwindow AS (
      SELECT line_id, resource_id, actor_name, state, ts
      FROM state_transitions
      WHERE ts >= $1 AND ts < $2 AND line_id IS NOT NULL
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
    actor_down AS (
      SELECT
        line_id, resource_id, actor_name,
        SUM(CASE WHEN state = ANY($3::text[]) THEN GREATEST(dur_s, 0) ELSE 0 END)
            AS down_s
      FROM durations
      GROUP BY line_id, resource_id, actor_name
    ),
    line_down AS (
      -- "Line is down" only when every actor is concurrently down — taken
      -- here as MIN(down_s) across actors of the line, which equals the
      -- duration during which the least-down actor was still down.
      SELECT line_id, MIN(down_s) AS line_down_s, COUNT(*) AS actor_count
      FROM actor_down
      GROUP BY line_id
    ),
    line_jobs AS (
      SELECT
        line_id,
        SUM(COALESCE(actual_cycle_time_ms, 0)) AS busy_ms,
        SUM(COALESCE(ideal_cycle_time_ms, 0))  AS ideal_ms,
        COUNT(*)                                AS jobs_total,
        SUM(CASE WHEN quality = 'GOOD' THEN 1 ELSE 0 END) AS jobs_good,
        MAX(completed_at)                       AS latest_activity
      FROM job_results
      WHERE completed_at >= $1 AND completed_at < $2 AND line_id IS NOT NULL
      GROUP BY line_id
    ),
    lines AS (
      SELECT line_id FROM line_down
      UNION
      SELECT line_id FROM line_jobs
    )
    SELECT
      l.line_id,
      ld.line_down_s,
      ld.actor_count,
      lj.busy_ms,
      lj.ideal_ms,
      lj.jobs_total,
      lj.jobs_good,
      lj.latest_activity
    FROM lines l
    LEFT JOIN line_down ld USING (line_id)
    LEFT JOIN line_jobs lj USING (line_id)
    ORDER BY l.line_id;
  `;
  const result = await pool.query(sql, [start, end, DOWN_STATES]);

  const windowSeconds = (end.getTime() - start.getTime()) / 1000;
  return result.rows.map((r) => {
    const busy = Number(r.busy_ms) || 0;
    const ideal = Number(r.ideal_ms) || 0;
    const total = Number(r.jobs_total) || 0;
    const good = Number(r.jobs_good) || 0;
    const downS = Number(r.line_down_s) || 0;
    const actorCount = Number(r.actor_count) || 0;

    const availability =
      windowSeconds > 0
        ? Math.min(1, Math.max(0, (windowSeconds - downS) / windowSeconds))
        : 0;
    const performance = busy > 0 ? Math.min(1, ideal / busy) : 0;
    const quality = total > 0 ? good / total : 0;
    const oee = availability * performance * quality;

    return {
      line_id: r.line_id,
      availability: Math.round(availability * 100),
      performance: Math.round(performance * 100),
      quality: Math.round(quality * 100),
      oee: Math.round(oee * 100),
      jobs_total: total,
      jobs_good: good,
      resource_count: actorCount,
      latest_activity: r.latest_activity
        ? new Date(r.latest_activity).toISOString()
        : null,
    };
  });
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

  const [current, previous] = await Promise.all([
    computeLineOee(start, end),
    computeLineOee(prevStart, prevEnd),
  ]);

  const prevByLine = new Map<string, number>();
  for (const row of previous) prevByLine.set(row.line_id, row.oee);

  const lines: LineRow[] = current.map((row) => ({
    ...row,
    prev_oee: prevByLine.get(row.line_id) ?? 0,
  }));

  return NextResponse.json({
    window: w,
    start: start.toISOString(),
    end: end.toISOString(),
    lines,
  });
}
