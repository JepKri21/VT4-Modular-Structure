import { Pool } from "pg";

export const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 10,
  connectionTimeoutMillis: 5000,  // fail fast instead of hanging when DB is busy
  idleTimeoutMillis: 30_000,      // recycle stale connections before they go dead
  allowExitOnIdle: true,
});
