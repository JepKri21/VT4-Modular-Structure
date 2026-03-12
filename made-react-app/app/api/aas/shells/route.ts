import { NextResponse } from "next/server";

const AAS_SERVER = "http://localhost:8081";

/** GET /api/aas/shells — list all shells on the AAS server */
export async function GET() {
  try {
    const res = await fetch(`${AAS_SERVER}/shells`);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Could not reach AAS server" }, { status: 502 });
  }
}

/** DELETE /api/aas/shells — delete every shell and its submodels from the AAS server */
export async function DELETE() {
  try {
    const res = await fetch(`${AAS_SERVER}/shells`);
    if (!res.ok) {
      return NextResponse.json({ error: "Failed to list shells" }, { status: 502 });
    }
    const data = await res.json();
    const shells: { id: string; submodels?: { keys: { value: string }[] }[] }[] =
      data.result ?? [];

    const results: { id: string; type: string; status: number; ok: boolean }[] = [];

    for (const shell of shells) {
      // Delete all referenced submodels first
      for (const ref of shell.submodels ?? []) {
        const smId = ref.keys?.[0]?.value;
        if (!smId) continue;
        const encoded = Buffer.from(smId).toString("base64url");
        const del = await fetch(`${AAS_SERVER}/submodels/${encoded}`, { method: "DELETE" });
        results.push({ id: smId, type: "submodel", status: del.status, ok: del.ok });
      }

      // Then delete the shell itself
      const encoded = Buffer.from(shell.id).toString("base64url");
      const del = await fetch(`${AAS_SERVER}/shells/${encoded}`, { method: "DELETE" });
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
