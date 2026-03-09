import { pool } from "@/lib/db";

export async function POST(req: Request) {
  const { id } = await req.json();

  await pool.query(
    `
    UPDATE station_alarms
    SET acknowledged = true
    WHERE id = $1
  `,
    [id],
  );

  return Response.json({ success: true });
}
