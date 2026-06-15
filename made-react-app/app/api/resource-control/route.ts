import { NextRequest, NextResponse } from "next/server";
import { getLiveShellIds } from "@/lib/process-registry";
import { getResourceRunnerConfig } from "@/lib/aas-config";

export interface ResourceControlEntry {
  shellId: string;
  displayName: string;
  running: boolean;
  pid?: number;
  // Transport stations carry a shuttle count (the Transport skill's Actors
  // list). Only set for transport resources; undefined elsewhere so the UI
  // renders the stepper on transport cards only.
  isTransport?: boolean;
  shuttleCount?: number;
}

const b64url = (id: string) => Buffer.from(id).toString("base64url");

// A transport resource is identified by its shell IRI. Covers both the type
// shell (.../Resources/TransportStation) and a running instance
// (.../Resources/Transport_<uuid>). No other resource family (Storage,
// Drilling, *Assembler) contains "Transport".
function isTransportShell(shellId: string): boolean {
  return shellId.includes("/Shells/Resources/Transport");
}

// Count shuttles = length of the Transport skill's Actors list in the Skills
// submodel. Returns 0 if the submodel/skill/actors can't be read.
async function fetchShuttleCount(serverUrl: string, shellId: string): Promise<number> {
  try {
    const smId = `${shellId}/Skills`;
    const res = await fetch(`${serverUrl}/submodels/${b64url(smId)}`, {
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return 0;
    const sm = (await res.json()) as {
      submodelElements?: { idShort?: string; value?: unknown }[];
    };
    const skills = sm.submodelElements ?? [];
    const transport =
      skills.find((s) => s.idShort === "Transport") ?? skills[0];
    const children = (transport?.value as { idShort?: string; value?: unknown }[] | undefined) ?? [];
    const actors = children.find((c) => c.idShort === "Actors");
    const list = (actors?.value as unknown[] | undefined) ?? [];
    return list.length;
  } catch {
    return 0;
  }
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
        ? `${serverUrl}/shells?limit=1000&cursor=${encodeURIComponent(cursor)}`
        : `${serverUrl}/shells?limit=1000`;
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

    const resources: ResourceControlEntry[] = await Promise.all(
      resourceShells.map(async (s) => {
        const entry: ResourceControlEntry = {
          shellId: s.id,
          displayName: (s.idShort ?? s.id.split("/").pop() ?? s.id).replace(/_/g, " "),
          running: liveIds.has(s.id),
        };
        if (isTransportShell(s.id)) {
          entry.isTransport = true;
          entry.shuttleCount = await fetchShuttleCount(serverUrl, s.id);
        }
        return entry;
      }),
    );

    return NextResponse.json({ resources, configOk });
  } catch (err) {
    return NextResponse.json({
      resources: [],
      configOk,
      error: `Could not reach AAS server: ${String(err)}`,
    });
  }
}
