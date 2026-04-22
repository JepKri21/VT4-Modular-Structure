import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  useMemo,
} from "react";
import {
  Move,
  RotateCw,
  Trash2,
  Undo2,
  Redo2,
  Download,
  Link2,
  AlertTriangle,
  Grid3x3,
  Eye,
  EyeOff,
  Pencil,
  X,
} from "lucide-react";

// ============================================================================
// === FILE: lib/types.ts =====================================================
// All shared types. In your project, move to a .ts file.
// ============================================================================
//
// ZoneType determines compatibility:
//   infeed  ↔ outfeed  ✓
//   inout   ↔ anything ✓
//   infeed  ↔ infeed   ✗
//   outfeed ↔ outfeed  ✗
//
// Colors:
//   infeed  = green   (#22c55e)
//   outfeed = blue    (#3b82f6)
//   inout   = purple  (#a855f7)
// ============================================================================

// ============================================================================
// === FILE: lib/resourceLibrary.ts ===========================================
// In your project, this eventually becomes: fetch('/api/resource-types')
// backed by your AAS registry (e.g. BaSyx). Each zone now has a `type`.
// ============================================================================
const RESOURCE_LIBRARY = [
  {
    typeId: "acopos6d-table",
    name: "ACOPOS 6D Table",
    vendor: "B&R",
    category: "transport",
    color: "#1D9E75",
    footprint: { width: 1200, height: 800 },
    connectionZones: [
      {
        id: "north",
        label: "North",
        type: "inout",
        polygon: [
          [-600, -700],
          [600, -700],
          [600, -400],
          [-600, -400],
        ],
      },
      {
        id: "south",
        label: "South",
        type: "inout",
        polygon: [
          [-600, 400],
          [600, 400],
          [600, 700],
          [-600, 700],
        ],
      },
      {
        id: "east",
        label: "East",
        type: "inout",
        polygon: [
          [600, -400],
          [900, -400],
          [900, 400],
          [600, 400],
        ],
      },
      {
        id: "west",
        label: "West",
        type: "inout",
        polygon: [
          [-900, -400],
          [-600, -400],
          [-600, 400],
          [-900, 400],
        ],
      },
    ],
  },
  {
    typeId: "drilling-station",
    name: "Drilling Station",
    vendor: "Generic",
    category: "process",
    color: "#378ADD",
    footprint: { width: 600, height: 600 },
    connectionZones: [
      {
        id: "infeed",
        label: "Infeed",
        type: "infeed",
        polygon: [
          [-600, -300],
          [-300, -300],
          [-300, 300],
          [-600, 300],
        ],
      },
      {
        id: "outfeed",
        label: "Outfeed",
        type: "outfeed",
        polygon: [
          [300, -300],
          [600, -300],
          [600, 300],
          [300, 300],
        ],
      },
    ],
  },
  {
    typeId: "robot-cell",
    name: "Robot Cell",
    vendor: "Generic",
    category: "handling",
    color: "#D85A30",
    footprint: { width: 1000, height: 1000 },
    connectionZones: [
      {
        id: "front",
        label: "Front",
        type: "inout",
        polygon: [
          [-500, 500],
          [500, 500],
          [500, 800],
          [-500, 800],
        ],
      },
      {
        id: "back",
        label: "Back",
        type: "inout",
        polygon: [
          [-500, -800],
          [500, -800],
          [500, -500],
          [-500, -500],
        ],
      },
      {
        id: "left",
        label: "Left",
        type: "inout",
        polygon: [
          [-800, -500],
          [-500, -500],
          [-500, 500],
          [-800, 500],
        ],
      },
      {
        id: "right",
        label: "Right",
        type: "inout",
        polygon: [
          [500, -500],
          [800, -500],
          [800, 500],
          [500, 500],
        ],
      },
    ],
  },
  {
    typeId: "buffer",
    name: "Buffer / Storage",
    vendor: "Generic",
    category: "storage",
    color: "#BA7517",
    footprint: { width: 800, height: 400 },
    connectionZones: [
      {
        id: "left",
        label: "Left",
        type: "infeed",
        polygon: [
          [-700, -200],
          [-400, -200],
          [-400, 200],
          [-700, 200],
        ],
      },
      {
        id: "right",
        label: "Right",
        type: "outfeed",
        polygon: [
          [400, -200],
          [700, -200],
          [700, 200],
          [400, 200],
        ],
      },
    ],
  },
];

const ZONE_COLORS = {
  infeed: {
    fill: "#22c55e22",
    stroke: "#22c55e",
    strokeActive: "#22c55e",
    label: "Infeed",
  },
  outfeed: {
    fill: "#3b82f622",
    stroke: "#3b82f6",
    strokeActive: "#3b82f6",
    label: "Outfeed",
  },
  inout: {
    fill: "#a855f722",
    stroke: "#a855f7",
    strokeActive: "#a855f7",
    label: "In/Out",
  },
};

const ZONES_COMPATIBLE = (a, b) => {
  if (a === "inout" || b === "inout") return true;
  return (
    (a === "infeed" && b === "outfeed") || (a === "outfeed" && b === "infeed")
  );
};

const MM_PER_GRID = 200;

// ============================================================================
// === FILE: lib/geometry.ts ==================================================
// Pure functions. Zero React. Easy to unit-test.
// ============================================================================
const uid = () => Math.random().toString(36).slice(2, 10);

const rotate = (x, y, deg) => {
  const r = (deg * Math.PI) / 180;
  const c = Math.cos(r),
    s = Math.sin(r);
  return { x: x * c - y * s, y: x * s + y * c };
};

const localToWorld = (resource, lx, ly) => {
  const r = rotate(lx, ly, resource.rotation);
  return { x: resource.position.x + r.x, y: resource.position.y + r.y };
};

const worldToLocal = (resource, wx, wy) => {
  const dx = wx - resource.position.x;
  const dy = wy - resource.position.y;
  return rotate(dx, dy, -resource.rotation);
};

const zoneToWorldPolygon = (resource, zonePolygon) =>
  zonePolygon.map(([x, y]) => {
    const w = localToWorld(resource, x, y);
    return [w.x, w.y];
  });

const pointInPolygon = (x, y, poly) => {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i],
      [xj, yj] = poly[j];
    const intersect =
      yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
};

const polygonSignedArea = (poly) => {
  let a = 0;
  for (let i = 0; i < poly.length; i++) {
    const [x1, y1] = poly[i];
    const [x2, y2] = poly[(i + 1) % poly.length];
    a += x1 * y2 - x2 * y1;
  }
  return a / 2;
};

// Ensure counter-clockwise winding (required by clipPolygon)
const ensureCCW = (poly) =>
  polygonSignedArea(poly) < 0 ? [...poly].reverse() : poly;

// --- Robust Sutherland-Hodgman polygon clipping ---
// Fixed: uses epsilon tolerance for edge cases and re-verifies winding on both inputs
const EPS = 1e-6;

const segmentIntersect = (p1, p2, p3, p4) => {
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

const clipPolygon = (subject, clip) => {
  // Defensive: both must be CCW. Caller should ensure, but we double-check.
  const subjectCCW = ensureCCW(subject);
  const clipCCW = ensureCCW(clip);

  let output = subjectCCW;
  for (let i = 0; i < clipCCW.length; i++) {
    const input = output;
    output = [];
    if (input.length === 0) return [];
    const A = clipCCW[i];
    const B = clipCCW[(i + 1) % clipCCW.length];
    // Inward-pointing normal for CCW polygons
    const edgeNormal = [B[1] - A[1], -(B[0] - A[0])];
    // Use strict "inside" test with epsilon so points exactly on the edge count as inside
    const inside = (p) =>
      (p[0] - A[0]) * edgeNormal[0] + (p[1] - A[1]) * edgeNormal[1] >= -EPS;

    for (let j = 0; j < input.length; j++) {
      const P = input[j];
      const Q = input[(j + 1) % input.length];
      const Pin = inside(P),
        Qin = inside(Q);
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
  // Strip collinear duplicates
  const deduped = output.filter((p, i) => {
    const prev = output[(i - 1 + output.length) % output.length];
    return Math.abs(p[0] - prev[0]) > EPS || Math.abs(p[1] - prev[1]) > EPS;
  });
  return deduped.length >= 3 ? deduped : [];
};

const resourceBBox = (res, typeById) => {
  const type = typeById[res.typeId];
  const { width: w, height: h } = type.footprint;
  const corners = [
    [-w / 2, -h / 2],
    [w / 2, -h / 2],
    [w / 2, h / 2],
    [-w / 2, h / 2],
  ];
  const worldCorners = corners.map(([x, y]) => localToWorld(res, x, y));
  const xs = worldCorners.map((p) => p.x);
  const ys = worldCorners.map((p) => p.y);
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
};

const bboxOverlap = (a, b) =>
  a.minX < b.maxX && a.maxX > b.minX && a.minY < b.maxY && a.maxY > b.minY;

// Get all effective zones for a resource instance: library zones + custom (instance) zones
const getEffectiveZones = (res, typeById) => {
  const type = typeById[res.typeId];
  const custom = res.customZones || [];
  return [...type.connectionZones, ...custom];
};

// ============================================================================
// === FILE: hooks/useHistory.ts ==============================================
// Generic undo/redo. In your project, move to its own file.
// ============================================================================
const useHistory = (initial) => {
  const [history, setHistory] = useState([initial]);
  const [idx, setIdx] = useState(0);
  const current = history[idx];

  const commit = useCallback(
    (updater) => {
      setHistory((h) => {
        const cur = h[idx];
        const next = typeof updater === "function" ? updater(cur) : updater;
        return [...h.slice(0, idx + 1), next];
      });
      setIdx((i) => i + 1);
    },
    [idx],
  );

  // For live drag: mutate current entry without creating new history step
  const mutate = useCallback(
    (updater) => {
      setHistory((h) => {
        const next = [...h];
        next[idx] =
          typeof updater === "function" ? updater(next[idx]) : updater;
        return next;
      });
    },
    [idx],
  );

  // Finalize: snapshot current into a new history entry (used after drag)
  const snapshot = useCallback(() => {
    setHistory((h) => [...h.slice(0, idx + 1), h[idx]]);
    setIdx((i) => i + 1);
  }, [idx]);

  return {
    state: current,
    commit,
    mutate,
    snapshot,
    undo: () => setIdx((i) => Math.max(0, i - 1)),
    redo: () => setIdx((i) => Math.min(history.length - 1, i + 1)),
    canUndo: idx > 0,
    canRedo: idx < history.length - 1,
  };
};

// ============================================================================
// === FILE: lib/aasExport.ts =================================================
// ============================================================================
const buildAASPayload = (scene, typeById) => ({
  schemaVersion: "1.2",
  generatedAt: new Date().toISOString(),
  globalReferenceFrame: { unit: "mm", origin: { x: 0, y: 0 } },
  resources: scene.resources.map((r) => {
    const type = typeById[r.typeId];
    return {
      instanceId: r.instanceId,
      aasIdShort: `${type.typeId}_${r.instanceId}`,
      typeId: r.typeId,
      submodels: {
        Nameplate: {
          manufacturerName: type.vendor,
          manufacturerProductDesignation: type.name,
        },
        LineConfiguration: {
          position: r.position,
          rotationDeg: r.rotation,
          footprint: type.footprint,
        },
        ...(r.customZones &&
          r.customZones.length > 0 && {
            CustomInterfaces: r.customZones.map((z) => ({
              id: z.id,
              label: z.label,
              type: z.type,
              polygon: z.polygon,
            })),
          }),
      },
    };
  }),
  connections: scene.connections.map((c) => {
    const resA = scene.resources.find((r) => r.instanceId === c.resourceAId);
    const resB = scene.resources.find((r) => r.instanceId === c.resourceBId);
    return {
      id: c.id,
      resourceA: {
        instanceId: c.resourceAId,
        zoneId: c.zoneAId,
        zoneType: c.zoneAType,
        local: c.localPositionA,
        aasIdShort: resA
          ? `${typeById[resA.typeId].typeId}_${resA.instanceId}`
          : null,
      },
      resourceB: {
        instanceId: c.resourceBId,
        zoneId: c.zoneBId,
        zoneType: c.zoneBType,
        local: c.localPositionB,
        aasIdShort: resB
          ? `${typeById[resB.typeId].typeId}_${resB.instanceId}`
          : null,
      },
      global: c.worldPosition,
    };
  }),
});

// ============================================================================
// === FILE: components/LineConfigurator.tsx ==================================
// Main component. The rest of the components below would be in their own files.
// ============================================================================
export default function LineConfigurator() {
  const typeById = useMemo(
    () => Object.fromEntries(RESOURCE_LIBRARY.map((t) => [t.typeId, t])),
    [],
  );

  const {
    state: scene,
    commit,
    mutate,
    snapshot,
    undo,
    redo,
    canUndo,
    canRedo,
  } = useHistory({ resources: [], connections: [] });

  const canvasRef = useRef(null);
  const [view, setView] = useState({ scale: 0.15, offsetX: 400, offsetY: 300 });
  const [selectedId, setSelectedId] = useState(null);
  const [hoverResourceId, setHoverResourceId] = useState(null);
  const [drag, setDrag] = useState(null);
  const [mode, setMode] = useState("select"); // 'select' | 'connect' | 'draw-zone'
  const [snapToGrid, setSnapToGrid] = useState(true);
  const [alwaysShowZones, setAlwaysShowZones] = useState(false);
  const [connectFirst, setConnectFirst] = useState(null);
  const [pendingOverlaps, setPendingOverlaps] = useState([]);
  // Zone drawing: { startLocal, currentLocal, resourceId, type }
  const [zoneDraw, setZoneDraw] = useState(null);
  const [newZoneType, setNewZoneType] = useState("inout");

  // --- Transform helpers ---
  const worldToScreen = useCallback(
    (wx, wy) => ({
      x: wx * view.scale + view.offsetX,
      y: wy * view.scale + view.offsetY,
    }),
    [view],
  );

  const screenToWorld = useCallback(
    (sx, sy) => ({
      x: (sx - view.offsetX) / view.scale,
      y: (sy - view.offsetY) / view.scale,
    }),
    [view],
  );

  // --- Station body overlaps (warning) ---
  const overlaps = useMemo(() => {
    const pairs = [];
    for (let i = 0; i < scene.resources.length; i++) {
      for (let j = i + 1; j < scene.resources.length; j++) {
        const a = resourceBBox(scene.resources[i], typeById);
        const b = resourceBBox(scene.resources[j], typeById);
        if (bboxOverlap(a, b))
          pairs.push([
            scene.resources[i].instanceId,
            scene.resources[j].instanceId,
          ]);
      }
    }
    return pairs;
  }, [scene.resources, typeById]);

  const overlapSet = useMemo(() => {
    const s = new Set();
    overlaps.forEach(([a, b]) => {
      s.add(a);
      s.add(b);
    });
    return s;
  }, [overlaps]);

  // --- Zone overlap computation (filtered by compatibility) ---
  const computeZoneOverlaps = useCallback(
    (resA, resB) => {
      const zonesA = getEffectiveZones(resA, typeById);
      const zonesB = getEffectiveZones(resB, typeById);
      const regions = [];
      zonesA.forEach((zoneA) => {
        const polyA = ensureCCW(zoneToWorldPolygon(resA, zoneA.polygon));
        zonesB.forEach((zoneB) => {
          if (!ZONES_COMPATIBLE(zoneA.type, zoneB.type)) return;
          const polyB = ensureCCW(zoneToWorldPolygon(resB, zoneB.polygon));
          const clipped = clipPolygon(polyA, polyB);
          if (clipped.length >= 3) {
            regions.push({
              polygon: clipped,
              zoneAId: zoneA.id,
              zoneBId: zoneB.id,
              zoneAType: zoneA.type,
              zoneBType: zoneB.type,
              zoneALabel: zoneA.label,
              zoneBLabel: zoneB.label,
            });
          }
        });
      });
      return regions;
    },
    [typeById],
  );

  useEffect(() => {
    if (mode !== "connect" || !connectFirst) {
      setPendingOverlaps([]);
      return;
    }
    const resA = scene.resources.find((r) => r.instanceId === connectFirst);
    if (!resA) return;
    const existingPairs = new Set(
      scene.connections.map((c) =>
        [c.resourceAId, c.resourceBId].sort().join("|"),
      ),
    );
    const all = [];
    scene.resources.forEach((resB) => {
      if (resB.instanceId === resA.instanceId) return;
      if (
        existingPairs.has([resA.instanceId, resB.instanceId].sort().join("|"))
      )
        return;
      computeZoneOverlaps(resA, resB).forEach((region) =>
        all.push({ ...region, otherInstanceId: resB.instanceId }),
      );
    });
    setPendingOverlaps(all);
  }, [
    mode,
    connectFirst,
    scene.resources,
    scene.connections,
    computeZoneOverlaps,
  ]);

  // ===========================================================================
  // === RENDERING ============================================================
  // ===========================================================================
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Background
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(0, 0, rect.width, rect.height);

    // Grid
    const gridStepPx = MM_PER_GRID * view.scale;
    if (gridStepPx > 6) {
      ctx.strokeStyle = "#1a1a1a";
      ctx.lineWidth = 1;
      const startX = view.offsetX % gridStepPx;
      const startY = view.offsetY % gridStepPx;
      ctx.beginPath();
      for (let x = startX; x < rect.width; x += gridStepPx) {
        ctx.moveTo(x, 0);
        ctx.lineTo(x, rect.height);
      }
      for (let y = startY; y < rect.height; y += gridStepPx) {
        ctx.moveTo(0, y);
        ctx.lineTo(rect.width, y);
      }
      ctx.stroke();
    }

    // GRF axes
    const origin = worldToScreen(0, 0);
    ctx.strokeStyle = "#dc2626";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(origin.x, origin.y);
    ctx.lineTo(origin.x + 80, origin.y);
    ctx.stroke();
    ctx.strokeStyle = "#16a34a";
    ctx.beginPath();
    ctx.moveTo(origin.x, origin.y);
    ctx.lineTo(origin.x, origin.y + 80);
    ctx.stroke();
    ctx.fillStyle = "#dc2626";
    ctx.font = "600 11px ui-monospace, monospace";
    ctx.fillText("X", origin.x + 84, origin.y + 4);
    ctx.fillStyle = "#16a34a";
    ctx.fillText("Y", origin.x - 4, origin.y + 94);
    ctx.fillStyle = "#737373";
    ctx.fillText("GRF", origin.x + 6, origin.y - 6);

    // Resources
    scene.resources.forEach((res) => {
      const type = typeById[res.typeId];
      const zones = getEffectiveZones(res, typeById);
      const p = worldToScreen(res.position.x, res.position.y);
      const isSelected = selectedId === res.instanceId;
      const isHover = hoverResourceId === res.instanceId;
      const isOverlapping = overlapSet.has(res.instanceId);
      const isConnectFirst = connectFirst === res.instanceId;
      const showZones =
        alwaysShowZones ||
        mode === "connect" ||
        mode === "draw-zone" ||
        isSelected;

      // Zones (colored by type)
      if (showZones) {
        zones.forEach((zone) => {
          const colors = ZONE_COLORS[zone.type] || ZONE_COLORS.inout;
          const worldPoly = zoneToWorldPolygon(res, zone.polygon);
          ctx.fillStyle = colors.fill;
          ctx.strokeStyle = isConnectFirst
            ? colors.strokeActive
            : colors.stroke;
          ctx.lineWidth = isConnectFirst ? 1.5 : 1;
          ctx.setLineDash([4, 3]);
          ctx.beginPath();
          worldPoly.forEach(([x, y], i) => {
            const s = worldToScreen(x, y);
            if (i === 0) ctx.moveTo(s.x, s.y);
            else ctx.lineTo(s.x, s.y);
          });
          ctx.closePath();
          ctx.fill();
          ctx.stroke();
          ctx.setLineDash([]);
        });
      }

      // Body
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate((res.rotation * Math.PI) / 180);
      const w = type.footprint.width * view.scale;
      const h = type.footprint.height * view.scale;

      ctx.fillStyle = type.color + "33";
      ctx.fillRect(-w / 2, -h / 2, w, h);
      ctx.strokeStyle = isOverlapping
        ? "#dc2626"
        : isConnectFirst
          ? "#fbbf24"
          : isSelected
            ? "#ffffff"
            : isHover
              ? type.color
              : type.color + "aa";
      ctx.lineWidth = isSelected || isConnectFirst ? 2 : 1.2;
      ctx.strokeRect(-w / 2, -h / 2, w, h);

      // Orientation marker (+X)
      ctx.fillStyle = type.color;
      ctx.beginPath();
      ctx.moveTo(w / 2 - 6, 0);
      ctx.lineTo(w / 2 - 14, -5);
      ctx.lineTo(w / 2 - 14, 5);
      ctx.closePath();
      ctx.fill();

      // Label (unrotated)
      ctx.rotate((-res.rotation * Math.PI) / 180);
      ctx.fillStyle = "#e5e5e5";
      ctx.font = "500 11px ui-monospace, monospace";
      ctx.textAlign = "center";
      ctx.fillText(type.name, 0, 0);
      ctx.fillStyle = "#737373";
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillText(
        `${Math.round(res.position.x)}, ${Math.round(res.position.y)} mm`,
        0,
        14,
      );
      ctx.textAlign = "start";
      ctx.restore();
    });

    // Pending overlaps (connect mode, after first pick)
    if (mode === "connect" && connectFirst) {
      pendingOverlaps.forEach((region) => {
        // Use a color that reflects the bound between the two zone types
        const mixed =
          region.zoneAType === "inout"
            ? region.zoneBType
            : region.zoneBType === "inout"
              ? region.zoneAType
              : "inout"; // infeed↔outfeed: neutral purple accent
        const col = ZONE_COLORS[mixed];
        ctx.fillStyle = col.stroke + "55";
        ctx.strokeStyle = "#fafafa";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        region.polygon.forEach(([x, y], i) => {
          const s = worldToScreen(x, y);
          if (i === 0) ctx.moveTo(s.x, s.y);
          else ctx.lineTo(s.x, s.y);
        });
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      });
    }

    // Active zone drawing (preview)
    if (zoneDraw && zoneDraw.currentLocal) {
      const res = scene.resources.find(
        (r) => r.instanceId === zoneDraw.resourceId,
      );
      if (res) {
        const { startLocal, currentLocal } = zoneDraw;
        const corners = [
          [startLocal.x, startLocal.y],
          [currentLocal.x, startLocal.y],
          [currentLocal.x, currentLocal.y],
          [startLocal.x, currentLocal.y],
        ];
        const worldPoly = corners.map(([x, y]) => {
          const w = localToWorld(res, x, y);
          return [w.x, w.y];
        });
        const col = ZONE_COLORS[zoneDraw.type];
        ctx.fillStyle = col.fill;
        ctx.strokeStyle = col.stroke;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([2, 2]);
        ctx.beginPath();
        worldPoly.forEach(([x, y], i) => {
          const s = worldToScreen(x, y);
          if (i === 0) ctx.moveTo(s.x, s.y);
          else ctx.lineTo(s.x, s.y);
        });
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    // Existing connections
    scene.connections.forEach((c) => {
      const resA = scene.resources.find((r) => r.instanceId === c.resourceAId);
      const resB = scene.resources.find((r) => r.instanceId === c.resourceBId);
      if (!resA || !resB) return;
      const pA = worldToScreen(resA.position.x, resA.position.y);
      const pB = worldToScreen(resB.position.x, resB.position.y);
      const pt = worldToScreen(c.worldPosition.x, c.worldPosition.y);

      ctx.strokeStyle = "#22d3ee88";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(pA.x, pA.y);
      ctx.lineTo(pt.x, pt.y);
      ctx.lineTo(pB.x, pB.y);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = "#fafafa";
      ctx.strokeStyle = "#22d3ee";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    });

    // Scale bar
    const barLengthMM = 1000;
    const barPx = barLengthMM * view.scale;
    const bx = 16,
      by = rect.height - 20;
    ctx.strokeStyle = "#a3a3a3";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(bx, by);
    ctx.lineTo(bx + barPx, by);
    ctx.moveTo(bx, by - 4);
    ctx.lineTo(bx, by + 4);
    ctx.moveTo(bx + barPx, by - 4);
    ctx.lineTo(bx + barPx, by + 4);
    ctx.stroke();
    ctx.fillStyle = "#a3a3a3";
    ctx.font = "10px ui-monospace, monospace";
    ctx.fillText(`${barLengthMM} mm`, bx, by - 8);
  }, [
    scene,
    view,
    selectedId,
    hoverResourceId,
    overlapSet,
    mode,
    connectFirst,
    pendingOverlaps,
    alwaysShowZones,
    zoneDraw,
    worldToScreen,
    typeById,
  ]);

  // ===========================================================================
  // === HIT TESTING & INTERACTION ============================================
  // ===========================================================================
  const pickResource = useCallback(
    (worldX, worldY) => {
      for (let i = scene.resources.length - 1; i >= 0; i--) {
        const res = scene.resources[i];
        const type = typeById[res.typeId];
        const local = worldToLocal(res, worldX, worldY);
        const { width: w, height: h } = type.footprint;
        if (Math.abs(local.x) <= w / 2 && Math.abs(local.y) <= h / 2) {
          return { res, local };
        }
      }
      return null;
    },
    [scene.resources, typeById],
  );

  const pickOverlapRegion = useCallback(
    (worldX, worldY) => {
      for (const region of pendingOverlaps) {
        if (pointInPolygon(worldX, worldY, region.polygon)) return region;
      }
      return null;
    },
    [pendingOverlaps],
  );

  // --- Palette drag/drop ---
  const onPaletteDragStart = (e, typeId) => {
    e.dataTransfer.setData("application/x-resource-type", typeId);
    e.dataTransfer.effectAllowed = "copy";
  };
  const onCanvasDragOver = (e) => {
    if (e.dataTransfer.types.includes("application/x-resource-type")) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    }
  };
  const onCanvasDrop = (e) => {
    e.preventDefault();
    const typeId = e.dataTransfer.getData("application/x-resource-type");
    if (!typeId) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const world = screenToWorld(e.clientX - rect.left, e.clientY - rect.top);
    const snapped = snapToGrid
      ? {
          x: Math.round(world.x / MM_PER_GRID) * MM_PER_GRID,
          y: Math.round(world.y / MM_PER_GRID) * MM_PER_GRID,
        }
      : world;
    const newRes = {
      instanceId: uid(),
      typeId,
      position: snapped,
      rotation: 0,
      customZones: [],
    };
    commit((s) => ({ ...s, resources: [...s.resources, newRes] }));
    setSelectedId(newRes.instanceId);
  };

  // --- Mouse down ---
  const onCanvasMouseDown = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const sx = e.clientX - rect.left,
      sy = e.clientY - rect.top;
    const world = screenToWorld(sx, sy);

    if (e.button === 1 || (e.button === 0 && e.altKey)) {
      setDrag({
        kind: "pan",
        startX: e.clientX,
        startY: e.clientY,
        origOffset: { ...view },
      });
      return;
    }

    // --- Draw zone mode ---
    if (mode === "draw-zone") {
      const hit = pickResource(world.x, world.y);
      if (!hit) return;
      setZoneDraw({
        resourceId: hit.res.instanceId,
        startLocal: { x: hit.local.x, y: hit.local.y },
        currentLocal: { x: hit.local.x, y: hit.local.y },
        type: newZoneType,
      });
      setDrag({ kind: "draw-zone" });
      return;
    }

    // --- Connect mode ---
    if (mode === "connect") {
      if (!connectFirst) {
        const hit = pickResource(world.x, world.y);
        if (hit) setConnectFirst(hit.res.instanceId);
        return;
      }
      const region = pickOverlapRegion(world.x, world.y);
      if (!region) {
        const hit = pickResource(world.x, world.y);
        if (hit && hit.res.instanceId !== connectFirst)
          setConnectFirst(hit.res.instanceId);
        return;
      }
      const resA = scene.resources.find((r) => r.instanceId === connectFirst);
      const resB = scene.resources.find(
        (r) => r.instanceId === region.otherInstanceId,
      );
      if (!resA || !resB) return;
      const localA = worldToLocal(resA, world.x, world.y);
      const localB = worldToLocal(resB, world.x, world.y);
      commit((s) => ({
        ...s,
        connections: [
          ...s.connections,
          {
            id: uid(),
            resourceAId: resA.instanceId,
            resourceBId: resB.instanceId,
            zoneAId: region.zoneAId,
            zoneBId: region.zoneBId,
            zoneAType: region.zoneAType,
            zoneBType: region.zoneBType,
            worldPosition: { x: world.x, y: world.y },
            localPositionA: { x: localA.x, y: localA.y },
            localPositionB: { x: localB.x, y: localB.y },
          },
        ],
      }));
      setConnectFirst(null);
      setMode("select");
      return;
    }

    // --- Select mode ---
    const hit = pickResource(world.x, world.y);
    if (hit) {
      setSelectedId(hit.res.instanceId);
      setDrag({
        kind: "resource",
        instanceId: hit.res.instanceId,
        grabOffset: {
          x: world.x - hit.res.position.x,
          y: world.y - hit.res.position.y,
        },
        moved: false,
      });
    } else {
      setSelectedId(null);
      setDrag({
        kind: "pan",
        startX: e.clientX,
        startY: e.clientY,
        origOffset: { ...view },
      });
    }
  };

  // --- Mouse move ---
  const onCanvasMouseMove = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const sx = e.clientX - rect.left,
      sy = e.clientY - rect.top;
    const world = screenToWorld(sx, sy);

    if (!drag) {
      const hit = pickResource(world.x, world.y);
      setHoverResourceId(hit ? hit.res.instanceId : null);
    }

    if (!drag) return;

    if (drag.kind === "pan") {
      setView((v) => ({
        ...v,
        offsetX: drag.origOffset.offsetX + (e.clientX - drag.startX),
        offsetY: drag.origOffset.offsetY + (e.clientY - drag.startY),
      }));
    } else if (drag.kind === "resource") {
      let nx = world.x - drag.grabOffset.x;
      let ny = world.y - drag.grabOffset.y;
      if (snapToGrid) {
        nx = Math.round(nx / MM_PER_GRID) * MM_PER_GRID;
        ny = Math.round(ny / MM_PER_GRID) * MM_PER_GRID;
      }
      mutate((s) => {
        const oldRes = s.resources.find(
          (r) => r.instanceId === drag.instanceId,
        );
        if (!oldRes) return s;
        const updatedRes = { ...oldRes, position: { x: nx, y: ny } };
        return {
          ...s,
          resources: s.resources.map((r) =>
            r.instanceId === drag.instanceId ? updatedRes : r,
          ),
          connections: s.connections.map((c) => {
            if (c.resourceAId === drag.instanceId)
              return {
                ...c,
                worldPosition: localToWorld(
                  updatedRes,
                  c.localPositionA.x,
                  c.localPositionA.y,
                ),
              };
            if (c.resourceBId === drag.instanceId)
              return {
                ...c,
                worldPosition: localToWorld(
                  updatedRes,
                  c.localPositionB.x,
                  c.localPositionB.y,
                ),
              };
            return c;
          }),
        };
      });
      setDrag((d) => ({ ...d, moved: true }));
    } else if (drag.kind === "draw-zone" && zoneDraw) {
      const res = scene.resources.find(
        (r) => r.instanceId === zoneDraw.resourceId,
      );
      if (!res) return;
      const local = worldToLocal(res, world.x, world.y);
      setZoneDraw((z) => ({ ...z, currentLocal: { x: local.x, y: local.y } }));
    }
  };

  // --- Mouse up ---
  const onCanvasMouseUp = () => {
    if (drag?.kind === "resource" && drag.moved) snapshot();

    if (drag?.kind === "draw-zone" && zoneDraw) {
      const { startLocal, currentLocal, resourceId, type } = zoneDraw;
      const minSize = 50; // mm — reject tiny accidental zones
      if (
        Math.abs(startLocal.x - currentLocal.x) > minSize &&
        Math.abs(startLocal.y - currentLocal.y) > minSize
      ) {
        const x1 = Math.min(startLocal.x, currentLocal.x);
        const x2 = Math.max(startLocal.x, currentLocal.x);
        const y1 = Math.min(startLocal.y, currentLocal.y);
        const y2 = Math.max(startLocal.y, currentLocal.y);
        const polygon = [
          [x1, y1],
          [x2, y1],
          [x2, y2],
          [x1, y2],
        ];
        commit((s) => ({
          ...s,
          resources: s.resources.map((r) =>
            r.instanceId === resourceId
              ? {
                  ...r,
                  customZones: [
                    ...(r.customZones || []),
                    {
                      id: `custom-${uid()}`,
                      label: `Custom ${ZONE_COLORS[type].label}`,
                      type,
                      polygon,
                    },
                  ],
                }
              : r,
          ),
        }));
      }
      setZoneDraw(null);
      setMode("select");
    }
    setDrag(null);
  };

  const onCanvasWheel = (e) => {
    e.preventDefault();
    const rect = canvasRef.current.getBoundingClientRect();
    const sx = e.clientX - rect.left,
      sy = e.clientY - rect.top;
    const worldBefore = screenToWorld(sx, sy);
    const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    const newScale = Math.max(0.02, Math.min(2, view.scale * factor));
    setView((v) => ({
      scale: newScale,
      offsetX: sx - worldBefore.x * newScale,
      offsetY: sy - worldBefore.y * newScale,
    }));
  };

  const rotateResource = (instanceId, deltaDeg) => {
    commit((s) => {
      const res = s.resources.find((r) => r.instanceId === instanceId);
      if (!res) return s;
      const newRes = {
        ...res,
        rotation: (res.rotation + deltaDeg + 360) % 360,
      };
      return {
        ...s,
        resources: s.resources.map((r) =>
          r.instanceId === instanceId ? newRes : r,
        ),
        connections: s.connections.map((c) => {
          if (c.resourceAId === instanceId)
            return {
              ...c,
              worldPosition: localToWorld(
                newRes,
                c.localPositionA.x,
                c.localPositionA.y,
              ),
            };
          if (c.resourceBId === instanceId)
            return {
              ...c,
              worldPosition: localToWorld(
                newRes,
                c.localPositionB.x,
                c.localPositionB.y,
              ),
            };
          return c;
        }),
      };
    });
  };

  useEffect(() => {
    const handler = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")
        return;
      if (
        (e.metaKey || e.ctrlKey) &&
        e.key.toLowerCase() === "z" &&
        !e.shiftKey
      ) {
        e.preventDefault();
        undo();
      } else if (
        (e.metaKey || e.ctrlKey) &&
        (e.key.toLowerCase() === "y" ||
          (e.key.toLowerCase() === "z" && e.shiftKey))
      ) {
        e.preventDefault();
        redo();
      } else if ((e.key === "Delete" || e.key === "Backspace") && selectedId) {
        e.preventDefault();
        commit((s) => ({
          ...s,
          resources: s.resources.filter((r) => r.instanceId !== selectedId),
          connections: s.connections.filter(
            (c) => c.resourceAId !== selectedId && c.resourceBId !== selectedId,
          ),
        }));
        setSelectedId(null);
      } else if (e.key.toLowerCase() === "r" && selectedId) {
        rotateResource(selectedId, 90);
      } else if (e.key === "Escape") {
        setConnectFirst(null);
        setZoneDraw(null);
        setMode("select");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedId, commit, undo, redo]);

  // --- Export ---
  const exportAAS = () => {
    const payload = buildAASPayload(scene, typeById);
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `line-configuration-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const selected = scene.resources.find((r) => r.instanceId === selectedId);
  const selectedType = selected ? typeById[selected.typeId] : null;
  const selectedConnections = selected
    ? scene.connections.filter(
        (c) =>
          c.resourceAId === selected.instanceId ||
          c.resourceBId === selected.instanceId,
      )
    : [];

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "240px 1fr 300px",
        height: "100vh",
        background: "#0a0a0a",
        color: "#e5e5e5",
        fontFamily: "ui-monospace, 'SF Mono', Menlo, monospace",
        fontSize: 12,
      }}
    >
      {/* ===== FILE: ResourcePalette.tsx ===== */}
      <aside
        style={{
          borderRight: "1px solid #1f1f1f",
          padding: 16,
          overflowY: "auto",
        }}
      >
        <div
          style={{
            fontSize: 10,
            letterSpacing: 1.5,
            color: "#737373",
            marginBottom: 8,
          }}
        >
          RESOURCE LIBRARY
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {RESOURCE_LIBRARY.map((t) => (
            <div
              key={t.typeId}
              draggable
              onDragStart={(e) => onPaletteDragStart(e, t.typeId)}
              style={{
                border: "1px solid #262626",
                borderLeft: `3px solid ${t.color}`,
                padding: "10px 12px",
                cursor: "grab",
                background: "#141414",
              }}
              onMouseEnter={(e) =>
                (e.currentTarget.style.background = "#1a1a1a")
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.background = "#141414")
              }
            >
              <div style={{ color: "#fafafa", fontWeight: 500 }}>{t.name}</div>
              <div style={{ color: "#737373", marginTop: 2, fontSize: 10 }}>
                {t.footprint.width}×{t.footprint.height} mm · {t.vendor}
              </div>
            </div>
          ))}
        </div>

        <div
          style={{
            marginTop: 24,
            fontSize: 10,
            letterSpacing: 1.5,
            color: "#737373",
            marginBottom: 8,
          }}
        >
          ZONE TYPES
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {Object.entries(ZONE_COLORS).map(([key, col]) => (
            <div
              key={key}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 10,
              }}
            >
              <div
                style={{
                  width: 12,
                  height: 12,
                  background: col.fill,
                  border: `1px solid ${col.stroke}`,
                }}
              />
              <span style={{ color: "#e5e5e5" }}>{col.label}</span>
            </div>
          ))}
        </div>

        <div
          style={{
            marginTop: 24,
            fontSize: 10,
            letterSpacing: 1.5,
            color: "#737373",
            marginBottom: 8,
          }}
        >
          SHORTCUTS
        </div>
        <div style={{ color: "#a3a3a3", lineHeight: 1.9, fontSize: 10 }}>
          <div>drag from palette → place</div>
          <div>R → rotate 90°</div>
          <div>⌫ → delete selected</div>
          <div>alt+drag / wheel → pan / zoom</div>
          <div>⌘Z / ⌘⇧Z → undo / redo</div>
          <div>esc → cancel mode</div>
        </div>
      </aside>

      {/* ===== FILE: CanvasView.tsx + Toolbar.tsx ===== */}
      <main style={{ position: "relative", overflow: "hidden" }}>
        <div
          style={{
            position: "absolute",
            top: 12,
            left: 12,
            right: 12,
            zIndex: 10,
            display: "flex",
            gap: 8,
            alignItems: "center",
          }}
        >
          <ToolbarGroup>
            <ToolbarBtn
              active={mode === "select"}
              onClick={() => {
                setMode("select");
                setConnectFirst(null);
                setZoneDraw(null);
              }}
              title="Select / move"
            >
              <Move size={13} />
            </ToolbarBtn>
            <ToolbarBtn
              active={mode === "connect"}
              onClick={() => {
                setMode("connect");
                setConnectFirst(null);
                setZoneDraw(null);
              }}
              title="Connect two resources"
            >
              <Link2 size={13} />
            </ToolbarBtn>
            <ToolbarBtn
              active={mode === "draw-zone"}
              onClick={() => {
                setMode("draw-zone");
                setConnectFirst(null);
              }}
              title="Draw a new zone on selected resource"
            >
              <Pencil size={13} />
            </ToolbarBtn>
          </ToolbarGroup>

          {mode === "draw-zone" && (
            <div
              style={{
                display: "flex",
                background: "#141414",
                border: "1px solid #262626",
              }}
            >
              {Object.entries(ZONE_COLORS).map(([key, col]) => (
                <button
                  key={key}
                  onClick={() => setNewZoneType(key)}
                  title={col.label}
                  style={{
                    background: newZoneType === key ? col.fill : "transparent",
                    border: "none",
                    borderRight: "1px solid #262626",
                    color: newZoneType === key ? "#fafafa" : "#a3a3a3",
                    padding: "8px 10px",
                    cursor: "pointer",
                    fontSize: 10,
                    fontFamily: "inherit",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      background: col.stroke,
                      display: "inline-block",
                    }}
                  />
                  {col.label}
                </button>
              ))}
            </div>
          )}

          <ToolbarGroup>
            <ToolbarBtn onClick={undo} disabled={!canUndo} title="Undo">
              <Undo2 size={13} />
            </ToolbarBtn>
            <ToolbarBtn onClick={redo} disabled={!canRedo} title="Redo">
              <Redo2 size={13} />
            </ToolbarBtn>
          </ToolbarGroup>
          <ToolbarGroup>
            <ToolbarBtn
              active={snapToGrid}
              onClick={() => setSnapToGrid((s) => !s)}
              title={`Snap to ${MM_PER_GRID}mm grid`}
            >
              <Grid3x3 size={13} />
            </ToolbarBtn>
            <ToolbarBtn
              active={alwaysShowZones}
              onClick={() => setAlwaysShowZones((s) => !s)}
              title="Always show zones"
            >
              {alwaysShowZones ? <Eye size={13} /> : <EyeOff size={13} />}
            </ToolbarBtn>
          </ToolbarGroup>
          <div style={{ flex: 1 }} />
          {overlaps.length > 0 && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                background: "#450a0a",
                color: "#fca5a5",
                padding: "6px 10px",
                border: "1px solid #7f1d1d",
                fontSize: 11,
              }}
            >
              <AlertTriangle size={13} /> {overlaps.length} station body overlap
              {overlaps.length > 1 ? "s" : ""}
            </div>
          )}
          <ToolbarBtn onClick={exportAAS} title="Export AAS JSON" accent>
            <Download size={13} /> <span style={{ marginLeft: 6 }}>Export</span>
          </ToolbarBtn>
        </div>

        {/* Mode hint */}
        {(mode === "connect" || mode === "draw-zone") && (
          <div
            style={{
              position: "absolute",
              top: 56,
              left: "50%",
              transform: "translateX(-50%)",
              zIndex: 10,
              background: "#1f1f1f",
              border: "1px solid #404040",
              padding: "6px 12px",
              fontSize: 11,
              color: "#fbbf24",
              whiteSpace: "nowrap",
            }}
          >
            {mode === "connect" &&
              !connectFirst &&
              "Step 1 — click the first resource"}
            {mode === "connect" &&
              connectFirst &&
              pendingOverlaps.length === 0 &&
              "No compatible overlapping zones — infeed needs outfeed (or in/out). Move resources closer or esc to cancel."}
            {mode === "connect" &&
              connectFirst &&
              pendingOverlaps.length > 0 &&
              "Step 2 — click inside a highlighted region to place the connection point"}
            {mode === "draw-zone" &&
              "Click and drag on a resource to draw a new zone"}
          </div>
        )}

        <canvas
          ref={canvasRef}
          onMouseDown={onCanvasMouseDown}
          onMouseMove={onCanvasMouseMove}
          onMouseUp={onCanvasMouseUp}
          onMouseLeave={onCanvasMouseUp}
          onWheel={onCanvasWheel}
          onDragOver={onCanvasDragOver}
          onDrop={onCanvasDrop}
          style={{
            width: "100%",
            height: "100%",
            display: "block",
            cursor:
              drag?.kind === "pan"
                ? "grabbing"
                : mode === "select"
                  ? "default"
                  : "crosshair",
          }}
        />

        <div
          style={{
            position: "absolute",
            right: 12,
            bottom: 12,
            zIndex: 10,
            background: "#141414",
            border: "1px solid #262626",
            padding: "6px 10px",
            fontSize: 10,
            color: "#a3a3a3",
          }}
        >
          scale: {view.scale.toFixed(3)} px/mm · grid: {MM_PER_GRID} mm
        </div>
      </main>

      {/* ===== FILE: Inspector.tsx ===== */}
      <aside
        style={{
          borderLeft: "1px solid #1f1f1f",
          padding: 16,
          overflowY: "auto",
        }}
      >
        <div
          style={{
            fontSize: 10,
            letterSpacing: 1.5,
            color: "#737373",
            marginBottom: 8,
          }}
        >
          INSPECTOR
        </div>
        {!selected ? (
          <div style={{ color: "#525252", fontSize: 11, marginTop: 8 }}>
            No resource selected. Click a resource on the canvas to inspect its
            properties.
          </div>
        ) : (
          <div>
            <div
              style={{
                borderLeft: `3px solid ${selectedType.color}`,
                paddingLeft: 10,
                marginBottom: 16,
              }}
            >
              <div style={{ color: "#fafafa", fontWeight: 500, fontSize: 13 }}>
                {selectedType.name}
              </div>
              <div style={{ color: "#737373", fontSize: 10, marginTop: 2 }}>
                {selected.instanceId}
              </div>
            </div>

            <InspectorRow label="Position X">
              <NumInput
                value={selected.position.x}
                onChange={(v) =>
                  commit((s) => {
                    const res = s.resources.find(
                      (r) => r.instanceId === selectedId,
                    );
                    if (!res) return s;
                    const updated = {
                      ...res,
                      position: { ...res.position, x: v },
                    };
                    return {
                      ...s,
                      resources: s.resources.map((r) =>
                        r.instanceId === selectedId ? updated : r,
                      ),
                      connections: s.connections.map((c) => {
                        if (c.resourceAId === selectedId)
                          return {
                            ...c,
                            worldPosition: localToWorld(
                              updated,
                              c.localPositionA.x,
                              c.localPositionA.y,
                            ),
                          };
                        if (c.resourceBId === selectedId)
                          return {
                            ...c,
                            worldPosition: localToWorld(
                              updated,
                              c.localPositionB.x,
                              c.localPositionB.y,
                            ),
                          };
                        return c;
                      }),
                    };
                  })
                }
                suffix="mm"
              />
            </InspectorRow>
            <InspectorRow label="Position Y">
              <NumInput
                value={selected.position.y}
                onChange={(v) =>
                  commit((s) => {
                    const res = s.resources.find(
                      (r) => r.instanceId === selectedId,
                    );
                    if (!res) return s;
                    const updated = {
                      ...res,
                      position: { ...res.position, y: v },
                    };
                    return {
                      ...s,
                      resources: s.resources.map((r) =>
                        r.instanceId === selectedId ? updated : r,
                      ),
                      connections: s.connections.map((c) => {
                        if (c.resourceAId === selectedId)
                          return {
                            ...c,
                            worldPosition: localToWorld(
                              updated,
                              c.localPositionA.x,
                              c.localPositionA.y,
                            ),
                          };
                        if (c.resourceBId === selectedId)
                          return {
                            ...c,
                            worldPosition: localToWorld(
                              updated,
                              c.localPositionB.x,
                              c.localPositionB.y,
                            ),
                          };
                        return c;
                      }),
                    };
                  })
                }
                suffix="mm"
              />
            </InspectorRow>
            <InspectorRow label="Rotation">
              <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                <NumInput
                  value={selected.rotation}
                  onChange={(v) => {
                    const delta = (((v - selected.rotation) % 360) + 360) % 360;
                    rotateResource(selectedId, delta);
                  }}
                  suffix="°"
                />
                <button
                  onClick={() => rotateResource(selectedId, 90)}
                  style={{
                    background: "#1f1f1f",
                    border: "1px solid #404040",
                    color: "#e5e5e5",
                    padding: "4px 6px",
                    cursor: "pointer",
                  }}
                  title="Rotate +90°"
                >
                  <RotateCw size={11} />
                </button>
              </div>
            </InspectorRow>
            <InspectorRow label="Footprint">
              <div style={{ color: "#a3a3a3" }}>
                {selectedType.footprint.width} × {selectedType.footprint.height}{" "}
                mm
              </div>
            </InspectorRow>

            {/* Custom zones */}
            {selected.customZones && selected.customZones.length > 0 && (
              <>
                <div
                  style={{
                    fontSize: 10,
                    letterSpacing: 1.5,
                    color: "#737373",
                    marginTop: 20,
                    marginBottom: 8,
                  }}
                >
                  CUSTOM ZONES ({selected.customZones.length})
                </div>
                {selected.customZones.map((z) => {
                  const col = ZONE_COLORS[z.type];
                  return (
                    <div
                      key={z.id}
                      style={{
                        border: "1px solid #262626",
                        borderLeft: `3px solid ${col.stroke}`,
                        padding: 8,
                        marginBottom: 6,
                        fontSize: 10,
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <div>
                        <div style={{ color: "#fafafa" }}>{z.label}</div>
                        <div style={{ color: "#737373", marginTop: 2 }}>
                          type: {col.label}
                        </div>
                      </div>
                      <button
                        onClick={() =>
                          commit((s) => ({
                            ...s,
                            resources: s.resources.map((r) =>
                              r.instanceId === selectedId
                                ? {
                                    ...r,
                                    customZones: r.customZones.filter(
                                      (cz) => cz.id !== z.id,
                                    ),
                                  }
                                : r,
                            ),
                          }))
                        }
                        style={{
                          background: "transparent",
                          border: "none",
                          color: "#737373",
                          cursor: "pointer",
                        }}
                      >
                        <X size={11} />
                      </button>
                    </div>
                  );
                })}
              </>
            )}

            <div
              style={{
                fontSize: 10,
                letterSpacing: 1.5,
                color: "#737373",
                marginTop: 20,
                marginBottom: 8,
              }}
            >
              CONNECTIONS ({selectedConnections.length})
            </div>
            {selectedConnections.length === 0 ? (
              <div style={{ color: "#525252", fontSize: 11 }}>
                None. Use the link tool, pick this resource, then click inside a
                highlighted overlap region.
              </div>
            ) : (
              selectedConnections.map((c) => {
                const other = scene.resources.find(
                  (r) =>
                    r.instanceId ===
                    (c.resourceAId === selected.instanceId
                      ? c.resourceBId
                      : c.resourceAId),
                );
                const otherType = other ? typeById[other.typeId] : null;
                const thisSide =
                  c.resourceAId === selected.instanceId ? "A" : "B";
                const thisZone = thisSide === "A" ? c.zoneAId : c.zoneBId;
                const otherZone = thisSide === "A" ? c.zoneBId : c.zoneAId;
                const thisLocal =
                  thisSide === "A" ? c.localPositionA : c.localPositionB;
                const thisZoneType =
                  thisSide === "A" ? c.zoneAType : c.zoneBType;
                const otherZoneType =
                  thisSide === "A" ? c.zoneBType : c.zoneAType;
                return (
                  <div
                    key={c.id}
                    style={{
                      border: "1px solid #262626",
                      padding: 8,
                      marginBottom: 6,
                      fontSize: 10,
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <span style={{ color: "#fafafa" }}>
                        ↔ {otherType?.name ?? "?"}
                      </span>
                      <button
                        onClick={() =>
                          commit((s) => ({
                            ...s,
                            connections: s.connections.filter(
                              (x) => x.id !== c.id,
                            ),
                          }))
                        }
                        style={{
                          background: "transparent",
                          border: "none",
                          color: "#737373",
                          cursor: "pointer",
                        }}
                      >
                        <Trash2 size={10} />
                      </button>
                    </div>
                    <div style={{ color: "#737373", marginTop: 4 }}>
                      {thisZone} ({ZONE_COLORS[thisZoneType].label}) ↔{" "}
                      {otherZone} ({ZONE_COLORS[otherZoneType].label})
                    </div>
                    <div style={{ color: "#737373" }}>
                      local (this): {Math.round(thisLocal.x)},{" "}
                      {Math.round(thisLocal.y)} mm
                    </div>
                    <div style={{ color: "#737373" }}>
                      global: {Math.round(c.worldPosition.x)},{" "}
                      {Math.round(c.worldPosition.y)} mm
                    </div>
                  </div>
                );
              })
            )}

            <button
              onClick={() =>
                commit((s) => ({
                  ...s,
                  resources: s.resources.filter(
                    (r) => r.instanceId !== selectedId,
                  ),
                  connections: s.connections.filter(
                    (c) =>
                      c.resourceAId !== selectedId &&
                      c.resourceBId !== selectedId,
                  ),
                }))
              }
              style={{
                marginTop: 16,
                width: "100%",
                background: "#450a0a",
                border: "1px solid #7f1d1d",
                color: "#fca5a5",
                padding: "8px",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
              }}
            >
              <Trash2 size={11} /> Remove resource
            </button>
          </div>
        )}
      </aside>
    </div>
  );
}

// ============================================================================
// === UI primitives (inline for artifact; split in project) ==================
// ============================================================================
function ToolbarGroup({ children }) {
  return (
    <div
      style={{
        display: "flex",
        background: "#141414",
        border: "1px solid #262626",
      }}
    >
      {children}
    </div>
  );
}

function ToolbarBtn({ children, active, disabled, onClick, title, accent }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{
        background: accent ? "#134e4a" : active ? "#1f2937" : "transparent",
        border: "none",
        borderRight: "1px solid #262626",
        color: disabled
          ? "#404040"
          : accent
            ? "#5eead4"
            : active
              ? "#fafafa"
              : "#a3a3a3",
        padding: "8px 12px",
        cursor: disabled ? "not-allowed" : "pointer",
        display: "flex",
        alignItems: "center",
        fontSize: 11,
        fontFamily: "inherit",
      }}
    >
      {children}
    </button>
  );
}

function InspectorRow({ label, children }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "80px 1fr",
        alignItems: "center",
        marginBottom: 8,
        fontSize: 11,
      }}
    >
      <div style={{ color: "#737373" }}>{label}</div>
      <div>{children}</div>
    </div>
  );
}

function NumInput({ value, onChange, suffix }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        border: "1px solid #262626",
        background: "#0060FF",
      }}
    >
      <input
        type="number"
        value={Math.round(value)}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{
          flex: 1,
          width: "100%",
          background: "transparent",
          border: "none",
          color: "#fafafa",
          padding: "5px 7px",
          fontFamily: "inherit",
          fontSize: 11,
          outline: "none",
        }}
      />
      {suffix && (
        <span style={{ color: "#525252", paddingRight: 8, fontSize: 10 }}>
          {suffix}
        </span>
      )}
    </div>
  );
}
