import type {
  CapabilityEntry,
  Connection,
  ConnectionZone,
  PolygonLocal,
  ProductionLineShell,
  Resource,
  ResourceType,
  Scene,
  ZoneType,
} from "./types";

export const AAS_SERVER_URL = "http://localhost:8081";

interface ModelRefValue {
  type?: string;
  keys?: { type?: string; value: string }[];
}

interface SME {
  idShort: string;
  modelType: string;
  value?: SME[] | string | ModelRefValue;
  submodelElements?: SME[];
  valueType?: string;
}

// Extract the target IRI from a ResourceReference, supporting both the legacy
// string Property form and the model ReferenceElement form.
const refIri = (sme: SME | undefined): string => {
  const v = sme?.value;
  if (typeof v === "string") return v;
  if (v && !Array.isArray(v)) return (v as ModelRefValue).keys?.[0]?.value ?? "";
  return "";
};

interface Shell {
  id: string;
  idShort: string;
  submodels?: { keys: { type: string; value: string }[]; type: string }[];
  assetInformation?: { assetKind?: string };
}

interface Submodel extends SME {
  id: string;
}

const PALETTE = [
  "#1D9E75",
  "#378ADD",
  "#D85A30",
  "#BA7517",
  "#7C3AED",
  "#DB2777",
  "#0EA5E9",
  "#F59E0B",
];

const hashString = (s: string): number => {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
};

const colorFor = (id: string): string => PALETTE[hashString(id) % PALETTE.length];

const children = (sme: SME | undefined): SME[] => {
  if (!sme) return [];
  if (Array.isArray(sme.value)) return sme.value as SME[];
  if (Array.isArray(sme.submodelElements)) return sme.submodelElements;
  return [];
};

const findChild = (sme: SME | undefined, idShort: string): SME | undefined =>
  children(sme).find((c) => c.idShort === idShort);

const propNumber = (parent: SME | undefined, idShort: string): number => {
  const p = findChild(parent, idShort);
  if (!p || typeof p.value !== "string") return 0;
  return parseFloat(p.value);
};

const parsePoint = (col: SME): [number, number] => [
  propNumber(col, "XPos"),
  propNumber(col, "YPos"),
];

const parsePolygon = (col: SME | undefined): PolygonLocal => {
  if (!col) return [];
  // Current AAS layout nests the points under a "Points" collection
  // (ResourceGeometry/Points/Point1.. and Zone/Points/Point1..). Fall back to
  // direct PointN children for the legacy flat layout.
  const container = findChild(col, "Points") ?? col;
  const points = children(container).filter(
    (c) => c.modelType === "SubmodelElementCollection" && /^Point\d+$/.test(c.idShort),
  );
  points.sort((a, b) => {
    const ai = parseInt(a.idShort.replace("Point", ""), 10);
    const bi = parseInt(b.idShort.replace("Point", ""), 10);
    return ai - bi;
  });
  return points.map(parsePoint);
};

const translatePolygon = (
  poly: PolygonLocal,
  cx: number,
  cy: number,
): PolygonLocal => poly.map(([x, y]) => [x - cx, y - cy]);

const parseZoneGroup = (
  group: SME | undefined,
  type: ZoneType,
  cx: number,
  cy: number,
): ConnectionZone[] => {
  if (!group) return [];
  return children(group)
    .filter((c) => c.modelType === "SubmodelElementCollection")
    .map((zone) => ({
      id: `${type}_${zone.idShort}`,
      label: zone.idShort,
      type,
      polygon: translatePolygon(parsePolygon(zone), cx, cy),
    }))
    .filter((z) => z.polygon.length >= 3);
};

const footprintFromPolygon = (poly: PolygonLocal): {
  width: number;
  height: number;
} => {
  if (poly.length === 0) return { width: 200, height: 200 };
  const xs = poly.map(([x]) => x);
  const ys = poly.map(([, y]) => y);
  const width = Math.max(...xs) - Math.min(...xs);
  const height = Math.max(...ys) - Math.min(...ys);
  return {
    width: width > 0 ? width : 200,
    height: height > 0 ? height : 200,
  };
};

const toResourceType = (shell: Shell, submodel: Submodel): ResourceType => {
  const center = findChild(submodel, "CenterPoint");
  const cx = propNumber(center, "XPos");
  const cy = propNumber(center, "YPos");

  const geometryRaw = parsePolygon(findChild(submodel, "ResourceGeometry"));
  const geometry = translatePolygon(geometryRaw, cx, cy);
  const footprint = footprintFromPolygon(geometry);

  const zones: ConnectionZone[] = [
    ...parseZoneGroup(findChild(submodel, "InputZones"), "infeed", cx, cy),
    ...parseZoneGroup(findChild(submodel, "OutputZones"), "outfeed", cx, cy),
    ...parseZoneGroup(findChild(submodel, "InOutputZones"), "inout", cx, cy),
  ];
  return {
    typeId: shell.id,
    name: shell.idShort,
    vendor: "AAS",
    category: "resource",
    color: colorFor(shell.id),
    footprint,
    geometry: geometry.length >= 3 ? geometry : undefined,
    connectionZones: zones,
  };
};

const pagedResults = async <T,>(url: string): Promise<T[]> => {
  const out: T[] = [];
  let cursor: string | undefined;
  const sep = url.includes("?") ? "&" : "?";
  for (;;) {
    const u = `${url}${sep}limit=1000${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`;
    const res = await fetch(u);
    if (!res.ok) throw new Error(`${res.status} ${url}`);
    const json = await res.json();
    if (Array.isArray(json.result)) out.push(...json.result);
    cursor = json.paging_metadata?.cursor;
    if (!cursor) break;
  }
  return out;
};

const b64url = (s: string): string => {
  const bytes = new TextEncoder().encode(s);
  let binary = "";
  bytes.forEach((b) => { binary += String.fromCharCode(b); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
};

export const fetchProductionLines = async (
  serverUrl: string = AAS_SERVER_URL,
): Promise<ProductionLineShell[]> => {
  const shells = await pagedResults<Shell>(`${serverUrl}/shells`);
  return shells
    .filter((s) => s.id.startsWith("https://aausmartlab.org/Shells/Resources/ProductionLine/"))
    .map((s) => {
      const smIris = (s.submodels ?? []).map((ref) => ref.keys?.[0]?.value ?? "");
      return {
        id: s.id,
        idShort: s.idShort,
        lineConfigSubmodelId: smIris.find((iri) => iri.includes("LineConfiguration")),
        serviceOfferedSubmodelId: smIris.find((iri) => iri.includes("ServiceOffered")),
        communicationSubmodelId: smIris.find((iri) => iri.includes("Communication")),
      };
    });
};

const importZoneType = (raw: string): ZoneType =>
  raw === "in_outfeed" ? "inout" : (raw as ZoneType);

export const fetchLineConfiguration = async (
  submodelId: string,
  serverUrl: string = AAS_SERVER_URL,
  resourceLibrary: ResourceType[] = [],
): Promise<Scene> => {
  const res = await fetch(`${serverUrl}/submodels/${b64url(submodelId)}`);
  if (!res.ok) throw new Error(`Failed to fetch LineConfiguration: ${res.status}`);
  const sm = (await res.json()) as SME;

  const typeByName = new Map<string, ResourceType>(
    resourceLibrary.map((t) => [t.name, t]),
  );
  const typeById = new Map<string, ResourceType>(
    resourceLibrary.map((t) => [t.typeId, t]),
  );

  const locsSmc = children(sm).find((c) => c.idShort === "ResourceLocations");
  const connsSmc = children(sm).find((c) => c.idShort === "ConnectionPoints");

  const resources: Resource[] = children(locsSmc)
    .filter((c) => c.modelType === "SubmodelElementCollection")
    .map((c) => {
      const rawTypeId = refIri(findChild(c, "ResourceReference"));
      const libraryEntry = typeById.get(rawTypeId) ?? typeByName.get(rawTypeId);
      const typeIdVal = libraryEntry?.typeId ?? rawTypeId;
      const globalLoc = findChild(c, "GlobalLocation");
      const x = propNumber(globalLoc, "XPos");
      const y = propNumber(globalLoc, "YPos");
      const theta = propNumber(globalLoc, "ThetaAngle");
      return {
        instanceId: crypto.randomUUID(),
        typeId: typeIdVal,
        position: { x, y },
        rotation: theta,
        customZones: [],
      } satisfies Resource;
    })
    .filter((r) => r.typeId !== "");

  const connections: Connection[] = children(connsSmc)
    .filter((c) => c.modelType === "SubmodelElementCollection")
    .map((c) => {
      const globalLoc = findChild(c, "GlobalLocation");
      const wx = propNumber(globalLoc, "XPos");
      const wy = propNumber(globalLoc, "YPos");
      const connRes = findChild(c, "ConnectedResources");
      const r1 = findChild(connRes, "Resource1");
      const r2 = findChild(connRes, "Resource2");
      const refA = refIri(findChild(r1, "ResourceReference"));
      const refB = refIri(findChild(r2, "ResourceReference"));
      const ztA = importZoneType((findChild(r1, "ZoneType")?.value as string) ?? "inout");
      const ztB = importZoneType((findChild(r2, "ZoneType")?.value as string) ?? "inout");
      const locA = findChild(r1, "LocalLocation");
      const locB = findChild(r2, "LocalLocation");
      const lax = propNumber(locA, "XPos");
      const lay = propNumber(locA, "YPos");
      const lbx = propNumber(locB, "XPos");
      const lby = propNumber(locB, "YPos");

      const resA = resources.find((r) => r.typeId === refA);
      const resB = resources.find((r) => r.typeId === refB);
      const rtA = typeById.get(refA) ?? typeByName.get(refA);
      const rtB = typeById.get(refB) ?? typeByName.get(refB);
      const zoneA = rtA?.connectionZones.find((z) => z.type === ztA);
      const zoneB = rtB?.connectionZones.find((z) => z.type === ztB);

      return {
        id: crypto.randomUUID(),
        resourceAId: resA?.instanceId ?? "",
        resourceBId: resB?.instanceId ?? "",
        zoneAId: zoneA?.id ?? `${ztA}_0`,
        zoneBId: zoneB?.id ?? `${ztB}_0`,
        zoneAType: ztA,
        zoneBType: ztB,
        worldPosition: { x: wx, y: wy },
        localPositionA: { x: lax, y: lay },
        localPositionB: { x: lbx, y: lby },
      } satisfies Connection;
    })
    .filter((c) => c.resourceAId !== "" && c.resourceBId !== "");

  return { resources, connections };
};

export const fetchResourceCapabilities = async (
  resourceTypeIds: string[],
  serverUrl: string = AAS_SERVER_URL,
): Promise<CapabilityEntry[]> => {
  const results: CapabilityEntry[] = [];

  for (const rid of resourceTypeIds) {
    const shellRes = await fetch(`${serverUrl}/shells/${b64url(rid)}`);
    if (!shellRes.ok) continue;
    const shell = (await shellRes.json()) as Shell;

    const capSmIris = (shell.submodels ?? [])
      .map((ref) => ref.keys?.[0]?.value ?? "")
      .filter((iri) => iri.endsWith("CapabilityOffered"));

    for (const capSmIri of capSmIris) {
      const capRes = await fetch(`${serverUrl}/submodels/${b64url(capSmIri)}`);
      if (!capRes.ok) continue;
      const data = (await capRes.json()) as SME;

      // CapabilityTypeReference holds the IRI identifying the capability type,
      // e.g. "https://aausmartlab.org/Submodels/Capability/Assemble"
      const capTypeRefEl = children(data).find((c) => c.idShort === "CapabilityTypeReference");
      const capTypeIri = (capTypeRefEl?.value as string) ?? "";
      const capabilityType = capTypeIri
        ? (capTypeIri.split("/").at(-1) ?? capTypeIri)
        : data.idShort.replace(/CapabilityOffered$/, "");

      if (!capabilityType) continue;
      results.push({ capabilityType, resourceRef: rid, capabilityRef: capSmIri });
    }
  }

  return results;
};

export const fetchResourceLibrary = async (
  serverUrl: string = AAS_SERVER_URL,
): Promise<ResourceType[]> => {
  // A shell is a resource type iff it references a ".../ResourceZones" submodel.
  // The shell already lists its submodel IRIs, so we never need to scan the whole
  // submodel collection — we read the ref off the shell and GET that one by ID.
  // This scales with the number of resources (~handful), not the total submodel
  // count (thousands), and skips the standalone ResourceZones template.
  const shells = await pagedResults<Shell>(`${serverUrl}/shells`);

  const targets = shells
    // Exclude Type/template shells (AssemblyModule, StorageModule, ...) —
    // only concrete instance resources belong in the configurator library.
    .filter((shell) => shell.assetInformation?.assetKind !== "Type")
    .map((shell) => {
      const zonesIri = (shell.submodels ?? [])
        .flatMap((ref) => ref.keys ?? [])
        .map((k) => k.value)
        .find((iri) => iri.endsWith("/ResourceZones"));
      return zonesIri ? { shell, zonesIri } : null;
    })
    .filter((t): t is { shell: Shell; zonesIri: string } => t !== null);

  const library = await Promise.all(
    targets.map(async ({ shell, zonesIri }) => {
      const res = await fetch(`${serverUrl}/submodels/${b64url(zonesIri)}`);
      if (!res.ok) return null;
      return toResourceType(shell, (await res.json()) as Submodel);
    }),
  );
  return library.filter((t): t is ResourceType => t !== null);
};
