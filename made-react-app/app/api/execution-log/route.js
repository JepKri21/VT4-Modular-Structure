import { Pool } from "pg";

const pool = new Pool({
  user: "postgres",
  host: "localhost",
  database: "thesis_mes",
  password: "password",
  port: 5432,
});

export async function GET() {
  try {
    const result = await pool.query(
      "SELECT * FROM execution_log ORDER BY start_time DESC LIMIT 50",
    );
    return new Response(JSON.stringify(result.rows), { status: 200 });
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message }), {
      status: 500,
    });
  }
}
