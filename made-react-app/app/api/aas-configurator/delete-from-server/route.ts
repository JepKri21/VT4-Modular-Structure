import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const { serverUrl, shellId } = (await req.json()) as {
    serverUrl: string;
    shellId: string;
  };

  if (!serverUrl || !shellId) {
    return NextResponse.json({ error: "serverUrl and shellId are required" }, { status: 400 });
  }

  const base = serverUrl.replace(/\/$/, "");
  const encodedId = Buffer.from(shellId).toString("base64url");

  try {
    const res = await fetch(`${base}/shells/${encodedId}`, { method: "DELETE" });
    if (!res.ok && res.status !== 404) {
      const text = await res.text().catch(() => "");
      return NextResponse.json({ error: `Server returned ${res.status}: ${text}` }, { status: 502 });
    }
    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
