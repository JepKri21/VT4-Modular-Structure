import { NextRequest, NextResponse } from "next/server";
import { Pool } from "pg";

const pool = new Pool({
  user: "postgres",
  host: "localhost",
  database: "thesis_mes",
  password: "password",
  port: 5432,
});

interface StationOEE {
  stationId: string;
  currentOEE: number;
  previousOEE: number;
  latestActivity: string;
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const filter = (searchParams.get("filter") || "station") as
    | "line"
    | "station";
  const interval = Number(searchParams.get("hours") || 24);

  const client = await pool.connect();
  try {
    let stationsRes = await client.query(
      `SELECT DISTINCT station_id FROM production_jobs`,
    );
    let stations: StationOEE[] = [];

    // Hvis "line", grupper alle stationer under én line
    if (filter === "line") {
      // Her kan du lave et simpelt eksempel: alle stationer = én line
      stationsRes = { rows: [{ station_id: "LINE_1" }] } as any;
    }

    for (const row of stationsRes.rows) {
      const stationId = row.station_id;

      // CURRENT interval
      const jobsRes = await client.query(
        `SELECT * FROM production_jobs
         WHERE station_id = ANY($1)
         AND timestamp >= NOW() - INTERVAL '${interval} HOURS'`,
        filter === "line"
          ? [[...stationsRes.rows.map((r) => r.station_id)]]
          : [[stationId]],
      );
      const jobs = jobsRes.rows;
      if (jobs.length === 0) continue;

      // PREVIOUS interval
      const prevRes = await client.query(
        `SELECT * FROM production_jobs
         WHERE station_id = ANY($1)
         AND timestamp >= NOW() - INTERVAL '${interval * 2} HOURS'
         AND timestamp < NOW() - INTERVAL '${interval} HOURS'`,
        filter === "line"
          ? [[...stationsRes.rows.map((r) => r.station_id)]]
          : [[stationId]],
      );
      const prevJobs = prevRes.rows;

      const calculateOEE = (jobsArr: any[]) => {
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
        const availability = 1; // Kan beregnes senere fra station_state_changes
        return Math.round(availability * performance * quality * 100);
      };

      const currentOEE = calculateOEE(jobs);
      const previousOEE = calculateOEE(prevJobs);

      // Latest activity
      const latestJob = jobs.reduce((prev, curr) =>
        new Date(prev.timestamp) > new Date(curr.timestamp) ? prev : curr,
      );
      const latestActivity = new Date(latestJob.timestamp).toLocaleString();

      stations.push({ stationId, currentOEE, previousOEE, latestActivity });
    }

    return NextResponse.json(stations);
  } finally {
    client.release();
  }
}
