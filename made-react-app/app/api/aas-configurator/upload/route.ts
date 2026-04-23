import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const { serverUrl, shell, submodels } = await req.json() as {
    serverUrl: string;
    shell: Record<string, unknown>;
    submodels: Record<string, unknown>[];
  };

  if (!serverUrl) {
    return NextResponse.json({ error: "serverUrl is required" }, { status: 400 });
  }

  const base = serverUrl.replace(/\/$/, "");
  const results: { type: string; id: string; status: number; ok: boolean; error?: string }[] = [];

  const post = async (endpoint: string, body: Record<string, unknown>, label: string) => {
    try {
      const res = await fetch(`${base}/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const text = res.ok ? undefined : await res.text().catch(() => undefined);
      results.push({ type: label, id: (body.id as string) ?? label, status: res.status, ok: res.ok, error: text });
    } catch (err) {
      results.push({ type: label, id: (body.id as string) ?? label, status: 0, ok: false, error: String(err) });
    }
  };

  await post("shells", shell, "shell");
  for (const sm of submodels) {
    await post("submodels", sm, "submodel");
  }

  const allOk = results.every((r) => r.ok);
  return NextResponse.json({ results }, { status: allOk ? 200 : 207 });
}
