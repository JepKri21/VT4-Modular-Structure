import { NextRequest, NextResponse } from "next/server";

interface SaveBody {
  serverUrl?: string;
  submodels: Record<string, unknown>[];
}

export async function POST(req: NextRequest) {
  const body = (await req.json()) as SaveBody;
  const base = (body.serverUrl ?? "http://localhost:8081").replace(/\/$/, "");
  const results: { id: string; status: number; ok: boolean }[] = [];

  for (const submodel of body.submodels) {
    const id = submodel.id as string;
    const encoded = Buffer.from(id).toString("base64url");
    const headers = { "Content-Type": "application/json" };
    const bodyStr = JSON.stringify(submodel);

    let res = await fetch(`${base}/submodels/${encoded}`, {
      method: "PUT",
      headers,
      body: bodyStr,
    });

    if (res.status === 404) {
      res = await fetch(`${base}/submodels`, {
        method: "POST",
        headers,
        body: bodyStr,
      });
    }

    results.push({ id, status: res.status, ok: res.ok });
  }

  const anyFailed = results.some((r) => !r.ok);
  return NextResponse.json({ results }, { status: anyFailed ? 207 : 200 });
}
