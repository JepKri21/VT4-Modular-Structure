import { NextRequest, NextResponse } from "next/server";
import { Pool } from "pg";

const pool = new Pool({
  user: "postgres",
  host: "localhost",
  database: "thesis_mes",
  password: "password",
  port: 5432,
});

interface OEEItem {
  id: string;
  currentOEE: number;
  previousOEE: number;
  latestActivity: string;
}

async function calculateAvailability(
  client: any,
  filter: "station" | "line",
  id: string,
  interval: number,
) {
  let stationIds: string[] = [];

  if (filter === "station") {
    stationIds = [id];
  } else {
    const res = await client.query(
      `
      SELECT DISTINCT station_id
      FROM production_jobs
      WHERE production_line = $1
      `,
      [id],
    );

    stationIds = res.rows.map((r: any) => r.station_id);
  }

  let runningTime = 0;
  let totalTime = 0;

  for (const stationId of stationIds) {
    const res = await client.query(
      `
      SELECT
        state,
        timestamp,
        LEAD(timestamp) OVER (ORDER BY timestamp) AS next_timestamp
      FROM station_state_changes
      WHERE station_id = $1
      AND timestamp >= NOW() - INTERVAL '${interval} HOURS'
      ORDER BY timestamp
      `,
      [stationId],
    );

    for (const row of res.rows) {
      if (!row.next_timestamp) continue;

      const start = new Date(row.timestamp).getTime();
      const end = new Date(row.next_timestamp).getTime();
      const diff = end - start;

      totalTime += diff;

      if (row.state === "PackMLState.EXECUTE") {
        runningTime += diff;
      }
    }
  }

  if (totalTime === 0) return 1;

  return runningTime / totalTime;
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);

  const filter = (searchParams.get("filter") || "station") as
    | "station"
    | "line";

  const interval = Number(searchParams.get("hours") || 24);

  const client = await pool.connect();

  try {
    const column = filter === "line" ? "production_line" : "station_id";

    const entitiesRes = await client.query(
      `SELECT DISTINCT ${column} as id FROM production_jobs`,
    );

    const results: OEEItem[] = [];

    for (const row of entitiesRes.rows) {
      const id = row.id;

      // CURRENT INTERVAL
      const jobsRes = await client.query(
        `
        SELECT *
        FROM production_jobs
        WHERE ${column} = $1
        AND timestamp >= NOW() - INTERVAL '${interval} HOURS'
        `,
        [id],
      );

      const jobs = jobsRes.rows;

      if (jobs.length === 0) continue;

      // PREVIOUS INTERVAL
      const prevRes = await client.query(
        `
        SELECT *
        FROM production_jobs
        WHERE ${column} = $1
        AND timestamp >= NOW() - INTERVAL '${interval * 2} HOURS'
        AND timestamp < NOW() - INTERVAL '${interval} HOURS'
        `,
        [id],
      );

      const prevJobs = prevRes.rows;

      const calculateOEE = async (jobsArr: any[], id: string) => {
        const totalIdeal = jobsArr.reduce(
          (acc, j) => acc + j.ideal_cycle_time_ms,
          0,
        );

        const totalActual = jobsArr.reduce(
          (acc, j) => acc + j.cycle_time_ms,
          0,
        );

        const performance = totalActual ? totalIdeal / totalActual : 1;

        const goodJobs = jobsArr.filter((j) => j.quality === "OK").length;

        const quality = jobsArr.length ? goodJobs / jobsArr.length : 1;

        const availability = await calculateAvailability(
          client,
          filter,
          id,
          interval,
        );

        return Math.round(availability * performance * quality * 100);
      };

      const currentOEE = await calculateOEE(jobs, id);
      const previousOEE = await calculateOEE(prevJobs, id);

      const latestJob = jobs.reduce((prev, curr) =>
        new Date(prev.timestamp) > new Date(curr.timestamp) ? prev : curr,
      );

      const latestActivity = new Date(latestJob.timestamp).toLocaleString();

      results.push({
        id,
        currentOEE,
        previousOEE,
        latestActivity,
      });
    }

    return NextResponse.json(results);
  } finally {
    client.release();
  }
}
