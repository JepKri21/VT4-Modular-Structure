import { pool } from "@/lib/db";

export async function POST(req: Request) {
  const { id } = await req.json();

  await pool.query(
    `UPDATE alarms
     SET cleared_at = NOW()
     WHERE id = $1
       AND cleared_at IS NULL`,
    [id],
  );

  return Response.json({ success: true });
}
