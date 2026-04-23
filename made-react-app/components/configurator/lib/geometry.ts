import type {
  ConnectionZone,
  CustomZone,
  PolygonLocal,
  Resource,
  TypeById,
} from "./types";

export const EPS = 1e-6;

export const uid = (): string => Math.random().toString(36).slice(2, 10);

export const rotate = (
  x: number,
  y: number,
  deg: number,
): { x: number; y: number } => {
  const r = (deg * Math.PI) / 180;
  const c = Math.cos(r);
  const s = Math.sin(r);
  return { x: x * c - y * s, y: x * s + y * c };
};

export const localToWorld = (
  resource: Resource,
  lx: number,
  ly: number,
): { x: number; y: number } => {
  const r = rotate(lx, ly, resource.rotation);
  return { x: resource.position.x + r.x, y: resource.position.y + r.y };
};

export const worldToLocal = (
  resource: Resource,
  wx: number,
  wy: number,
): { x: number; y: number } => {
  const dx = wx - resource.position.x;
  const dy = wy - resource.position.y;
  return rotate(dx, dy, -resource.rotation);
};

export const zoneToWorldPolygon = (
  resource: Resource,
  zonePolygon: PolygonLocal,
): [number, number][] =>
  zonePolygon.map(([x, y]) => {
    const w = localToWorld(resource, x, y);
    return [w.x, w.y] as [number, number];
  });

export const pointInPolygon = (
  x: number,
  y: number,
  poly: [number, number][],
): boolean => {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    const intersect =
      yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
};

export const polygonSignedArea = (poly: [number, number][]): number => {
  let a = 0;
  for (let i = 0; i < poly.length; i++) {
    const [x1, y1] = poly[i];
    const [x2, y2] = poly[(i + 1) % poly.length];
    a += x1 * y2 - x2 * y1;
  }
  return a / 2;
};

export const ensureCCW = (poly: [number, number][]): [number, number][] =>
  polygonSignedArea(poly) < 0 ? [...poly].reverse() : poly;

export const segmentIntersect = (
  p1: [number, number],
  p2: [number, number],
  p3: [number, number],
  p4: [number, number],
): [number, number] | null => {
  const x1 = p1[0],
    y1 = p1[1],
    x2 = p2[0],
    y2 = p2[1];
  const x3 = p3[0],
    y3 = p3[1],
    x4 = p4[0],
    y4 = p4[1];
  const denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);
  if (Math.abs(denom) < EPS) return null;
  const t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom;
  return [x1 + t * (x2 - x1), y1 + t * (y2 - y1)];
};

export const clipPolygon = (
  subject: [number, number][],
  clip: [number, number][],
): [number, number][] => {
  const subjectCCW = ensureCCW(subject);
  const clipCCW = ensureCCW(clip);

  let output: [number, number][] = subjectCCW;
  for (let i = 0; i < clipCCW.length; i++) {
    const input = output;
    output = [];
    if (input.length === 0) return [];
    const A = clipCCW[i];
    const B = clipCCW[(i + 1) % clipCCW.length];
    const edge: [number, number] = [B[0] - A[0], B[1] - A[1]];
    const inside = (p: [number, number]): boolean =>
      edge[0] * (p[1] - A[1]) - edge[1] * (p[0] - A[0]) >= -EPS;

    for (let j = 0; j < input.length; j++) {
      const P = input[j];
      const Q = input[(j + 1) % input.length];
      const Pin = inside(P);
      const Qin = inside(Q);
      if (Pin && Qin) {
        output.push(Q);
      } else if (Pin && !Qin) {
        const inter = segmentIntersect(P, Q, A, B);
        if (inter) output.push(inter);
      } else if (!Pin && Qin) {
        const inter = segmentIntersect(P, Q, A, B);
        if (inter) output.push(inter);
        output.push(Q);
      }
    }
  }
  const deduped = output.filter((p, i) => {
    const prev = output[(i - 1 + output.length) % output.length];
    return Math.abs(p[0] - prev[0]) > EPS || Math.abs(p[1] - prev[1]) > EPS;
  });
  return deduped.length >= 3 ? deduped : [];
};

export interface BBox {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

export const resourceBBox = (res: Resource, typeById: TypeById): BBox => {
  const type = typeById[res.typeId];
  const localCorners: [number, number][] =
    type.geometry && type.geometry.length >= 3
      ? type.geometry
      : (() => {
          const { width: w, height: h } = type.footprint;
          return [
            [-w / 2, -h / 2],
            [w / 2, -h / 2],
            [w / 2, h / 2],
            [-w / 2, h / 2],
          ];
        })();
  const worldCorners = localCorners.map(([x, y]) => localToWorld(res, x, y));
  const xs = worldCorners.map((p) => p.x);
  const ys = worldCorners.map((p) => p.y);
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
};

export const bboxOverlap = (a: BBox, b: BBox): boolean =>
  a.minX < b.maxX && a.maxX > b.minX && a.minY < b.maxY && a.maxY > b.minY;

export const getEffectiveZones = (
  res: Resource,
  typeById: TypeById,
): (ConnectionZone | CustomZone)[] => {
  const type = typeById[res.typeId];
  const overrides = res.zoneOverrides || {};
  const builtin = type.connectionZones.map((z) =>
    overrides[z.id] ? { ...z, type: overrides[z.id] } : z,
  );
  const custom = res.customZones || [];
  return [...builtin, ...custom];
};
