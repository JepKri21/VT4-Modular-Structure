import { NextRequest, NextResponse } from "next/server";

function serverBase(req: NextRequest): string {
  const s = req.nextUrl.searchParams.get("server") ?? "http://localhost:8081";
  return s.replace(/\/$/, "");
}

/** GET /api/aas/shells?server=http://localhost:8081 — list all shells */
export async function GET(req: NextRequest) {
  const base = serverBase(req);
  try {
    const res = await fetch(`${base}/shells`);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Could not reach AAS server" }, { status: 502 });
  }
}

/** DELETE /api/aas/shells — delete selected or all shells + their submodels.
 *  Body: { server: string; ids?: string[] }
 *  If ids is omitted or empty, deletes all shells on the server.
 */
export async function DELETE(req: NextRequest) {
  const body = await req.json() as { server?: string; ids?: string[] };
  const base = (body.server ?? "http://localhost:8081").replace(/\/$/, "");

  try {
    // Fetch full shell list to resolve submodel references
    const listRes = await fetch(`${base}/shells`);
    if (!listRes.ok) {
      return NextResponse.json({ error: "Failed to list shells" }, { status: 502 });
    }
    const listData = await listRes.json();
    type RawShell = { id: string; submodels?: { keys: { value: string }[] }[] };
    let shells: RawShell[] = listData.result ?? [];

    // Filter to requested IDs if provided
    if (body.ids && body.ids.length > 0) {
      const idSet = new Set(body.ids);
      shells = shells.filter((s) => idSet.has(s.id));
    }

    const results: { id: string; type: string; status: number; ok: boolean }[] = [];

    for (const shell of shells) {
      for (const ref of shell.submodels ?? []) {
        const smId = ref.keys?.[0]?.value;
        if (!smId) continue;
        const encoded = Buffer.from(smId).toString("base64url");
        const del = await fetch(`${base}/submodels/${encoded}`, { method: "DELETE" });
        results.push({ id: smId, type: "submodel", status: del.status, ok: del.ok });
      }
      const encoded = Buffer.from(shell.id).toString("base64url");
      const del = await fetch(`${base}/shells/${encoded}`, { method: "DELETE" });
      results.push({ id: shell.id, type: "shell", status: del.status, ok: del.ok });
    }

    return NextResponse.json({
      deleted: results.filter((r) => r.ok).length,
      failed: results.filter((r) => !r.ok).length,
      results,
    });
  } catch {
    return NextResponse.json({ error: "Could not reach AAS server" }, { status: 502 });
  }
}
