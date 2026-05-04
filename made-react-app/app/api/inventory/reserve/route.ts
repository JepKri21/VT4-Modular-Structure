import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";

export async function POST(req: NextRequest) {
  const { id, session } = (await req.json()) as { id: string; session: string };
  if (!id || !session) {
    return NextResponse.json({ error: "id and session are required" }, { status: 400 });
  }

  const result = await pool.query(
    `UPDATE aas_inventory
     SET reserved_at = NOW(), reserved_session = $2
     WHERE id = $1 AND reserved_session IS NULL
     RETURNING id`,
    [id, session]
  );

  if ((result.rowCount ?? 0) === 0) {
    return NextResponse.json({ error: "Item already reserved or not found" }, { status: 409 });
  }

  return NextResponse.json({ ok: true });
}

export async function DELETE(req: NextRequest) {
  const url = new URL(req.url);
  const session = url.searchParams.get("session");
  const id = url.searchParams.get("id");

  if (!session) {
    return NextResponse.json({ error: "session is required" }, { status: 400 });
  }

  if (id) {
    await pool.query(
      `UPDATE aas_inventory SET reserved_at = NULL, reserved_session = NULL
       WHERE id = $1 AND reserved_session = $2`,
      [id, session]
    );
  } else {
    await pool.query(
      `UPDATE aas_inventory SET reserved_at = NULL, reserved_session = NULL
       WHERE reserved_session = $1`,
      [session]
    );
  }

  return NextResponse.json({ ok: true });
}
