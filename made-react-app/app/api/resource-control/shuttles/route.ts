import { NextRequest, NextResponse } from "next/server";
import { publish, lineTopic } from "@/lib/mqttPublisher";

// Add or retire a single transport shuttle (an actor in the Transport skill's
// Actors list). Shared by the resource-control card and the line-configurator
// card.
//
// - add:    write the new actor into the AAS Actors list, then ping
//           ReloadConfig so controller + station pick it up live.
// - retire: do NOT edit the AAS. Publish a RetireShuttle request and let the
//           Line Controller drain the shuttle cargo-safely; it deletes the
//           actor from the AAS only once the shuttle is idle + empty.

const b64url = (id: string) => Buffer.from(id).toString("base64url");
const headers = { "Content-Type": "application/json" };

interface SkillElement {
  idShort?: string;
  value?: unknown;
  modelType?: string;
  valueType?: string;
}

function defaultServer(url: string | null | undefined): string {
  return (url ?? "http://localhost:8081").replace(/\/$/, "");
}

async function readSkills(base: string, shellId: string): Promise<{ submodel: Record<string, unknown>; transport: SkillElement; actorsEl: SkillElement } | null> {
  const smId = `${shellId}/Skills`;
  const res = await fetch(`${base}/submodels/${b64url(smId)}`);
  if (!res.ok) return null;
  const submodel = (await res.json()) as Record<string, unknown>;
  const skills = (submodel.submodelElements as SkillElement[] | undefined) ?? [];
  const transport = skills.find((s) => s.idShort === "Transport") ?? skills[0];
  if (!transport) return null;
  const children = (transport.value as SkillElement[] | undefined) ?? [];
  const actorsEl = children.find((c) => c.idShort === "Actors");
  if (!actorsEl) return null;
  return { submodel, transport, actorsEl };
}

function actorNames(actorsEl: SkillElement): string[] {
  const items = (actorsEl.value as SkillElement[] | undefined) ?? [];
  return items.map((i) => String(i.value));
}

// "Shuttle3" -> 3; anything non-matching -> 0.
function shuttleIndex(name: string): number {
  const m = /Shuttle(\d+)/.exec(name);
  return m ? Number(m[1]) : 0;
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const shellId = searchParams.get("shellId");
  const base = defaultServer(searchParams.get("serverUrl"));
  if (!shellId) {
    return NextResponse.json({ error: "shellId required" }, { status: 400 });
  }
  const skills = await readSkills(base, shellId);
  if (!skills) {
    return NextResponse.json({ error: "Skills/Actors not found" }, { status: 404 });
  }
  const actors = actorNames(skills.actorsEl);
  return NextResponse.json({ actors, shuttleCount: actors.length });
}

export async function POST(req: NextRequest) {
  const body = (await req.json()) as {
    shellId?: string;
    action?: "add" | "retire";
    serverUrl?: string;
  };
  const base = defaultServer(body.serverUrl);
  const shellId = body.shellId;
  if (!shellId || (body.action !== "add" && body.action !== "retire")) {
    return NextResponse.json({ error: "shellId and action (add|retire) required" }, { status: 400 });
  }

  const skills = await readSkills(base, shellId);
  if (!skills) {
    return NextResponse.json({ error: "Skills/Actors not found" }, { status: 404 });
  }
  const { submodel, actorsEl } = skills;
  const names = actorNames(actorsEl);

  if (body.action === "add") {
    const next = (names.reduce((max, n) => Math.max(max, shuttleIndex(n)), 0) || names.length) + 1;
    const newName = `Shuttle${next}`;
    const items = (actorsEl.value as SkillElement[] | undefined) ?? [];
    // Clone an existing item to preserve modelType/valueType; fall back to a
    // plain string Property if the list was empty.
    const template = items[0];
    const newItem: SkillElement = template
      ? { ...template, value: newName }
      : { modelType: "Property", valueType: "xs:string", value: newName };
    if (newItem.idShort !== undefined) newItem.idShort = newName;
    actorsEl.value = [...items, newItem];

    const put = await fetch(`${base}/submodels/${b64url(`${shellId}/Skills`)}`, {
      method: "PUT",
      headers,
      body: JSON.stringify(submodel),
    });
    if (!put.ok) {
      const text = await put.text().catch(() => "");
      return NextResponse.json(
        { error: `AAS write failed (${put.status}): ${text}` },
        { status: 502 },
      );
    }
    // Live pickup: controller re-pulls actors + recomputes capacity, station
    // spawns the new shuttle's state machine.
    let reloadPinged = false;
    try {
      await publish(lineTopic("Controller/ReloadConfig"), { ts: Date.now() });
      reloadPinged = true;
    } catch (err) {
      console.error("[shuttles] reload ping failed:", err);
    }
    return NextResponse.json({ added: newName, shuttleCount: names.length + 1, reloadPinged });
  }

  // retire — pick the highest-numbered shuttle and let the controller drain it.
  if (names.length === 0) {
    return NextResponse.json({ error: "no shuttles to retire" }, { status: 409 });
  }
  const victim = [...names].sort((a, b) => shuttleIndex(b) - shuttleIndex(a))[0];
  let requested = false;
  try {
    await publish(lineTopic("Controller/RetireShuttle"), {
      timestamp: new Date().toISOString(),
      resource_iri: shellId,
      actor_name: victim,
    });
    requested = true;
  } catch (err) {
    console.error("[shuttles] retire publish failed:", err);
    return NextResponse.json({ error: "retire request publish failed" }, { status: 502 });
  }
  // The AAS Actors list is NOT changed here — the controller deletes the actor
  // once it is idle + empty. The card count updates on the next poll/refetch.
  return NextResponse.json({ retiring: victim, requested });
}
