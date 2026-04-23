import type {
  ConnectionZone,
  PolygonLocal,
  ResourceType,
  ZoneType,
} from "./types";

export const AAS_SERVER_URL = "http://localhost:8081";

interface SME {
  idShort: string;
  modelType: string;
  value?: SME[] | string;
  submodelElements?: SME[];
  valueType?: string;
}

interface Shell {
  id: string;
  idShort: string;
  submodels?: { keys: { type: string; value: string }[]; type: string }[];
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
  const points = children(col).filter(
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
  for (let i = 0; i < 10; i++) {
    const u = cursor ? `${url}?cursor=${encodeURIComponent(cursor)}` : url;
    const res = await fetch(u);
    if (!res.ok) throw new Error(`${res.status} ${url}`);
    const json = await res.json();
    if (Array.isArray(json.result)) out.push(...json.result);
    cursor = json.paging_metadata?.cursor;
    if (!cursor) break;
  }
  return out;
};

export const fetchResourceLibrary = async (
  serverUrl: string = AAS_SERVER_URL,
): Promise<ResourceType[]> => {
  const [shells, submodels] = await Promise.all([
    pagedResults<Shell>(`${serverUrl}/shells`),
    pagedResults<Submodel>(`${serverUrl}/submodels`),
  ]);
  const zonesById = new Map<string, Submodel>();
  submodels.forEach((s) => {
    if (s.idShort === "ResourceZones") zonesById.set(s.id, s);
  });
  const library: ResourceType[] = [];
  for (const shell of shells) {
    const sm = zonesById.get(`${shell.id}/ResourceZones`);
    if (!sm) continue;
    library.push(toResourceType(shell, sm));
  }
  return library;
};
