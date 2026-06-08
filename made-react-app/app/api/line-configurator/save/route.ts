import { NextRequest, NextResponse } from "next/server";

interface SaveBody {
  serverUrl?: string;
  lineShellId?: string;
  communicationSubmodelId?: string;
  submodels: Record<string, unknown>[];
}

const b64url = (id: string) => Buffer.from(id).toString("base64url");

const headers = { "Content-Type": "application/json" };

async function resolveCommunicationSmId(
  base: string,
  body: SaveBody,
): Promise<string | null> {
  if (body.communicationSubmodelId) return body.communicationSubmodelId;
  if (!body.lineShellId) return null;
  const res = await fetch(`${base}/shells/${b64url(body.lineShellId)}`);
  if (!res.ok) return null;
  const shell = (await res.json()) as { submodels?: { keys?: { value: string }[] }[] };
  const iris = (shell.submodels ?? []).map((ref) => ref.keys?.[0]?.value ?? "");
  return iris.find((iri) => iri.includes("Communication")) ?? null;
}

async function readMqttProp(base: string, smId: string, prop: string): Promise<string | null> {
  const res = await fetch(`${base}/submodels/${b64url(smId)}/submodel-elements/MQTT.${prop}`);
  if (!res.ok) return null;
  const el = (await res.json()) as { value?: string };
  return el.value ?? null;
}

async function putMqttProp(
  base: string,
  smId: string,
  prop: string,
  value: string,
  valueType: string,
): Promise<boolean> {
  const res = await fetch(
    `${base}/submodels/${b64url(smId)}/submodel-elements/MQTT.${prop}`,
    {
      method: "PUT",
      headers,
      body: JSON.stringify({ idShort: prop, modelType: "Property", valueType, value }),
    },
  );
  return res.ok;
}

function extractResourceIris(submodels: Record<string, unknown>[]): string[] {
  const lineConfig = submodels.find((sm) => sm.idShort === "LineConfiguration");
  if (!lineConfig) return [];
  const elements = (lineConfig.submodelElements as Record<string, unknown>[] | undefined) ?? [];
  const locsSmc = elements.find((e) => e.idShort === "ResourceLocations") as
    | { value?: Record<string, unknown>[] }
    | undefined;
  if (!locsSmc?.value) return [];
  const iris = new Set<string>();
  for (const entry of locsSmc.value) {
    const children = (entry.value as Record<string, unknown>[] | undefined) ?? [];
    const refProp = children.find((c) => c.idShort === "ResourceReference") as
      | { value?: string | { keys?: { value: string }[] } }
      | undefined;
    const refVal = refProp?.value;
    const iri =
      typeof refVal === "string" ? refVal : refVal?.keys?.[0]?.value;
    if (iri) iris.add(iri);
  }
  return Array.from(iris);
}

async function findResourceCommunicationSmId(base: string, resourceIri: string): Promise<string | null> {
  const res = await fetch(`${base}/shells/${b64url(resourceIri)}`);
  if (!res.ok) return null;
  const shell = (await res.json()) as { submodels?: { keys?: { value: string }[] }[] };
  const iris = (shell.submodels ?? []).map((ref) => ref.keys?.[0]?.value ?? "");
  return iris.find((iri) => iri.includes("Communication")) ?? null;
}

async function syncResourceCommunication(
  base: string,
  body: SaveBody,
): Promise<{ updated: number; skipped: number }> {
  const lineSmId = await resolveCommunicationSmId(base, body);
  if (!lineSmId) return { updated: 0, skipped: 0 };

  const [prefix, brokerId, brokerPort] = await Promise.all([
    readMqttProp(base, lineSmId, "ProductionLinePrefix"),
    readMqttProp(base, lineSmId, "BrokerID"),
    readMqttProp(base, lineSmId, "BrokerPort"),
  ]);

  if (prefix === null && brokerId === null && brokerPort === null) {
    return { updated: 0, skipped: 0 };
  }

  const resourceIris = extractResourceIris(body.submodels);
  let updated = 0;
  let skipped = 0;

  await Promise.all(
    resourceIris.map(async (iri) => {
      const resourceSmId = await findResourceCommunicationSmId(base, iri);
      if (!resourceSmId) { skipped++; return; }

      const puts: Promise<boolean>[] = [];
      if (prefix !== null)
        puts.push(putMqttProp(base, resourceSmId, "ProductionLinePrefix", prefix, "xs:string"));
      if (brokerId !== null)
        puts.push(putMqttProp(base, resourceSmId, "BrokerID", brokerId, "xs:string"));
      if (brokerPort !== null)
        puts.push(putMqttProp(base, resourceSmId, "BrokerPort", brokerPort, "xs:integer"));

      const results = await Promise.all(puts);
      if (results.every(Boolean)) updated++;
      else skipped++;
    }),
  );

  return { updated, skipped };
}

export async function POST(req: NextRequest) {
  const body = (await req.json()) as SaveBody;
  const base = (body.serverUrl ?? "http://localhost:8081").replace(/\/$/, "");
  const results: { id: string; status: number; ok: boolean }[] = [];

  for (const submodel of body.submodels) {
    const id = submodel.id as string;
    const encoded = b64url(id);
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

  const communicationSync = await syncResourceCommunication(base, body);

  const anyFailed = results.some((r) => !r.ok);
  return NextResponse.json({ results, communicationSync }, { status: anyFailed ? 207 : 200 });
}
