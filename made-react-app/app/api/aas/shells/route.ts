import { NextRequest, NextResponse } from "next/server";

function serverBase(req: NextRequest): string {
  const s = req.nextUrl.searchParams.get("server") ?? "http://localhost:8081";
  return s.replace(/\/$/, "");
}

/** GET /api/aas/shells?server=http://localhost:8081 — list all shells (paginated) */
export async function GET(req: NextRequest) {
  const base = serverBase(req);
  try {
    const allShells: unknown[] = [];
    let cursor: string | undefined;
    do {
      const url = cursor
        ? `${base}/shells?limit=1000&cursor=${encodeURIComponent(cursor)}`
        : `${base}/shells?limit=1000`;
      const res = await fetch(url);
      if (!res.ok) {
        return NextResponse.json({ error: `AAS server returned ${res.status}` }, { status: res.status });
      }
      const data = await res.json() as { result?: unknown[]; paging_metadata?: { cursor?: string } };
      allShells.push(...(data.result ?? []));
      cursor = data.paging_metadata?.cursor;
    } while (cursor);
    return NextResponse.json({ result: allShells });
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
    type RawShell = { id: string; submodels?: { keys: { value: string }[] }[] };
    const allShells: RawShell[] = [];
    let cursor: string | undefined;
    do {
      const url = cursor
        ? `${base}/shells?limit=1000&cursor=${encodeURIComponent(cursor)}`
        : `${base}/shells?limit=1000`;
      const listRes = await fetch(url);
      if (!listRes.ok) {
        return NextResponse.json({ error: "Failed to list shells" }, { status: 502 });
      }
      const listData = await listRes.json() as { result?: RawShell[]; paging_metadata?: { cursor?: string } };
      const page = listData.result ?? [];
      allShells.push(...page);
      cursor = listData.paging_metadata?.cursor;
    } while (cursor);
    let shells: RawShell[] = allShells;

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
        results.push({ id: smId, type: "submodel", status: del.status, ok: del.ok || del.status === 404 });
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
