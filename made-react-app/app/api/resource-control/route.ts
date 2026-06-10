import { NextRequest, NextResponse } from "next/server";
import { getLiveShellIds } from "@/lib/process-registry";
import { getResourceRunnerConfig } from "@/lib/aas-config";

export interface ResourceControlEntry {
  shellId: string;
  displayName: string;
  running: boolean;
  pid?: number;
}

export interface ResourceControlResponse {
  resources: ResourceControlEntry[];
  configOk: boolean;
  error?: string;
}

export async function GET(req: NextRequest): Promise<NextResponse<ResourceControlResponse>> {
  const { searchParams } = new URL(req.url);
  const serverUrl = searchParams.get("serverUrl")?.replace(/\/$/, "") ?? "";

  const { runnerPath } = getResourceRunnerConfig();
  const configOk = runnerPath !== "";

  const liveIds = await getLiveShellIds();

  if (!serverUrl) {
    // Status-only mode: return only currently live entries without hitting AAS
    const resources: ResourceControlEntry[] = Array.from(liveIds).map((id) => ({
      shellId: id,
      displayName: id.split("/").pop()?.replace(/_/g, " ") ?? id,
      running: true,
    }));
    return NextResponse.json({ resources, configOk });
  }

  try {
    type RawShell = { id: string; idShort?: string; assetInformation?: { assetKind?: string } };
    const allShells: RawShell[] = [];
    let cursor: string | undefined;
    do {
      const url = cursor
        ? `${serverUrl}/shells?limit=100&cursor=${encodeURIComponent(cursor)}`
        : `${serverUrl}/shells?limit=100`;
      const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        return NextResponse.json(
          { resources: [], configOk, error: `AAS server returned ${res.status}: ${text}` }
        );
      }
      const data = (await res.json()) as { result?: RawShell[]; paging_metadata?: { cursor?: string } };
      const page = data.result ?? (Array.isArray(data) ? (data as unknown as RawShell[]) : []);
      allShells.push(...page);
      cursor = data.paging_metadata?.cursor;
    } while (cursor);

    const resourceShells = allShells.filter(
      (s) =>
        s.id?.includes("/Shells/Resources/") &&
        !s.id?.includes("/ProductionLine/") &&
        s.assetInformation?.assetKind !== "Type"
    );

    const resources: ResourceControlEntry[] = resourceShells.map((s) => ({
      shellId: s.id,
      displayName: (s.idShort ?? s.id.split("/").pop() ?? s.id).replace(/_/g, " "),
      running: liveIds.has(s.id),
    }));


    return NextResponse.json({ resources, configOk });
  } catch (err) {
    return NextResponse.json({
      resources: [],
      configOk,
      error: `Could not reach AAS server: ${String(err)}`,
    });
  }
}
