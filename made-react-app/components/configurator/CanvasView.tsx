"use client";

import React, { useEffect, useCallback } from "react";
import type {
  Scene,
  ViewTransform,
  EditorMode,
  DragState,
  ZoneDraw,
  PendingOverlap,
  TypeById,
  Point,
  ZoneType,
} from "./lib/types";
import { MM_PER_GRID, ZONE_COLORS } from "./lib/resourceLibrary";
import {
  uid,
  getEffectiveZones,
  zoneToWorldPolygon,
  ensureCCW,
  clipPolygon,
  pointInPolygon,
  localToWorld,
  worldToLocal,
} from "./lib/geometry";

interface CanvasViewProps {
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  scene: Scene;
  view: ViewTransform;
  setView: React.Dispatch<React.SetStateAction<ViewTransform>>;
  mode: EditorMode;
  selectedId: string | null;
  setSelectedId: React.Dispatch<React.SetStateAction<string | null>>;
  hoverResourceId: string | null;
  setHoverResourceId: React.Dispatch<React.SetStateAction<string | null>>;
  overlapSet: Set<string>;
  connectFirst: string | null;
  setConnectFirst: React.Dispatch<React.SetStateAction<string | null>>;
  pendingOverlaps: PendingOverlap[];
  alwaysShowZones: boolean;
  zoneDraw: ZoneDraw | null;
  setZoneDraw: React.Dispatch<React.SetStateAction<ZoneDraw | null>>;
  typeById: TypeById;
  drag: DragState | null;
  setDrag: React.Dispatch<React.SetStateAction<DragState | null>>;
  commit: (updater: Scene | ((prev: Scene) => Scene)) => void;
  mutate: (updater: Scene | ((prev: Scene) => Scene)) => void;
  snapshot: () => void;
  worldToScreen: (wx: number, wy: number) => Point;
  screenToWorld: (sx: number, sy: number) => Point;
  snapToGrid: boolean;
  newZoneType: ZoneType;
  setMode: React.Dispatch<React.SetStateAction<EditorMode>>;
  selectedConnectionId: string | null;
  setSelectedConnectionId: React.Dispatch<React.SetStateAction<string | null>>;
  invalidConnectionIds: Set<string>;
  selectedZoneKey: string | null;
  setSelectedZoneKey: React.Dispatch<React.SetStateAction<string | null>>;
}

function cssVar(name: string, alpha?: number) {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();

  if (!value) return "#000";

  // Handle OKLCH and HEX automatically
  if (value.startsWith("oklch") || value.startsWith("#")) {
    return value;
  }

  // fallback for rgb values
  return alpha !== undefined ? `rgb(${value} / ${alpha})` : `rgb(${value})`;
}

export function CanvasView({
  canvasRef,
  scene,
  view,
  setView,
  mode,
  selectedId,
  setSelectedId,
  hoverResourceId,
  setHoverResourceId,
  overlapSet,
  connectFirst,
  setConnectFirst,
  pendingOverlaps,
  alwaysShowZones,
  zoneDraw,
  setZoneDraw,
  typeById,
  drag,
  setDrag,
  commit,
  mutate,
  snapshot,
  worldToScreen,
  screenToWorld,
  snapToGrid,
  newZoneType,
  setMode,
  selectedConnectionId,
  setSelectedConnectionId,
  invalidConnectionIds,
  selectedZoneKey,
  setSelectedZoneKey,
}: CanvasViewProps) {
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // ctx.fillStyle = cssVar("--background");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, rect.width, rect.height);

    const gridStepPx = MM_PER_GRID * view.scale;
    if (gridStepPx > 6) {
      // ctx.strokeStyle = cssVar("--muted", 0.4);
      ctx.strokeStyle = "#D9D9D9";
      ctx.lineWidth = 0.5;
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

    scene.resources.forEach((res) => {
      const type = typeById[res.typeId];
      if (!type) return;
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

      if (showZones) {
        zones.forEach((zone) => {
          const worldPoly = zoneToWorldPolygon(res, zone.polygon);
          const zc = ZONE_COLORS[zone.type];
          const isZoneSelected =
            selectedZoneKey === `${res.instanceId}:${zone.id}`;
          ctx.fillStyle = zc.fill;
          ctx.strokeStyle = zc.stroke;
          ctx.lineWidth = isZoneSelected ? 2.5 : 1.2;
          ctx.setLineDash(isZoneSelected ? [6, 3] : [4, 3]);
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

      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate((res.rotation * Math.PI) / 180);
      const w = type.footprint.width * view.scale;
      const h = type.footprint.height * view.scale;
      const bodyStroke = isOverlapping
        ? "#dc2626"
        : isConnectFirst
          ? "#fbbf24"
          : isSelected
            ? "#ffffff"
            : isHover
              ? type.color
              : type.color + "aa";
      const bodyLineWidth = isSelected || isConnectFirst ? 2 : 1.2;

      if (type.geometry && type.geometry.length >= 3) {
        ctx.beginPath();
        type.geometry.forEach(([gx, gy], i) => {
          const sx = gx * view.scale;
          const sy = gy * view.scale;
          if (i === 0) ctx.moveTo(sx, sy);
          else ctx.lineTo(sx, sy);
        });
        ctx.closePath();
        ctx.fillStyle = type.color + "33";
        ctx.fill();
        ctx.strokeStyle = bodyStroke;
        ctx.lineWidth = bodyLineWidth;
        ctx.stroke();
      } else {
        ctx.fillStyle = type.color + "33";
        ctx.fillRect(-w / 2, -h / 2, w, h);
        ctx.strokeStyle = bodyStroke;
        ctx.lineWidth = bodyLineWidth;
        ctx.strokeRect(-w / 2, -h / 2, w, h);
      }

      ctx.fillStyle = type.color;
      ctx.beginPath();
      ctx.arc(0, 0, Math.max(2, 3 * Math.min(view.scale * 20, 1)), 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = type.color;
      ctx.beginPath();
      ctx.moveTo(w / 2 - 6, 0);
      ctx.lineTo(w / 2 - 14, -5);
      ctx.lineTo(w / 2 - 14, 5);
      ctx.closePath();
      ctx.fill();

      ctx.rotate((-res.rotation * Math.PI) / 180);
      ctx.fillStyle = "#000000";
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

    scene.connections.forEach((c) => {
      const resA = scene.resources.find((r) => r.instanceId === c.resourceAId);
      const resB = scene.resources.find((r) => r.instanceId === c.resourceBId);
      if (!resA || !resB) return;
      const isSelectedConnection = selectedConnectionId === c.id;
      const isInvalidConnection = invalidConnectionIds.has(c.id);
      const pA = worldToScreen(resA.position.x, resA.position.y);
      const pB = worldToScreen(resB.position.x, resB.position.y);
      const pt = worldToScreen(c.worldPosition.x, c.worldPosition.y);

      ctx.strokeStyle = isInvalidConnection ? "#dc262688" : "#22d3ee88";
      ctx.lineWidth = isSelectedConnection ? 2.5 : 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(pA.x, pA.y);
      ctx.lineTo(pt.x, pt.y);
      ctx.lineTo(pB.x, pB.y);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = isInvalidConnection ? "#dc2626" : "#fafafa";
      ctx.strokeStyle = isInvalidConnection ? "#dc2626" : "#22d3ee";
      ctx.lineWidth = isSelectedConnection ? 3 : 2;
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      if (isSelectedConnection) {
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 10, 0, Math.PI * 2);
        ctx.strokeStyle = "#fbbf24";
        ctx.lineWidth = 1.5;
        ctx.setLineDash([6, 4]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    });

    if (selectedConnectionId) {
      const selected = scene.connections.find(
        (c) => c.id === selectedConnectionId,
      );
      if (selected) {
        const resA = scene.resources.find(
          (r) => r.instanceId === selected.resourceAId,
        );
        const resB = scene.resources.find(
          (r) => r.instanceId === selected.resourceBId,
        );
        if (resA && resB) {
          const zoneA = getEffectiveZones(resA, typeById).find(
            (z) => z.id === selected.zoneAId,
          );
          const zoneB = getEffectiveZones(resB, typeById).find(
            (z) => z.id === selected.zoneBId,
          );
          if (zoneA && zoneB) {
            const polyA = ensureCCW(zoneToWorldPolygon(resA, zoneA.polygon));
            const polyB = ensureCCW(zoneToWorldPolygon(resB, zoneB.polygon));
            const overlap = clipPolygon(polyA, polyB);
            if (overlap.length >= 3) {
              ctx.fillStyle = invalidConnectionIds.has(selectedConnectionId)
                ? "#dc262622"
                : "#fbbf2422";
              ctx.strokeStyle = invalidConnectionIds.has(selectedConnectionId)
                ? "#dc2626"
                : "#fbbf24";
              ctx.lineWidth = 2;
              ctx.beginPath();
              overlap.forEach(([x, y], i) => {
                const s = worldToScreen(x, y);
                if (i === 0) ctx.moveTo(s.x, s.y);
                else ctx.lineTo(s.x, s.y);
              });
              ctx.closePath();
              ctx.fill();
              ctx.stroke();
            }
          }
        }
      }
    }

    if (mode === "connect") {
      pendingOverlaps.forEach((region) => {
        const mixed =
          region.zoneAType === "inout"
            ? region.zoneBType
            : region.zoneBType === "inout"
              ? region.zoneAType
              : "inout";
        const overlayColor = {
          infeed: { stroke: "#22c55e", fill: "#22c55e55" },
          outfeed: { stroke: "#3b82f6", fill: "#3b82f655" },
          inout: { stroke: "#a855f7", fill: "#a855f755" },
        }[mixed];
        ctx.fillStyle = overlayColor.fill;
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

    if (zoneDraw && zoneDraw.currentLocal) {
      const res = scene.resources.find(
        (r) => r.instanceId === zoneDraw.resourceId,
      );
      if (res) {
        const { startLocal, currentLocal } = zoneDraw;
        const corners: [number, number][] = [
          [startLocal.x, startLocal.y],
          [currentLocal.x, startLocal.y],
          [currentLocal.x, currentLocal.y],
          [startLocal.x, currentLocal.y],
        ];
        const worldPoly = corners.map(([x, y]) => {
          const w = localToWorld(res, x, y);
          return [w.x, w.y] as [number, number];
        });
        const col = {
          infeed: { fill: "#22c55e22", stroke: "#22c55e" },
          outfeed: { fill: "#3b82f622", stroke: "#3b82f6" },
          inout: { fill: "#a855f722", stroke: "#a855f7" },
        }[zoneDraw.type];
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

    const barLengthMM = 1000;
    const barPx = barLengthMM * view.scale;
    const bx = 16;
    const by = rect.height - 20;
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
    selectedConnectionId,
    invalidConnectionIds,
    selectedZoneKey,
  ]);

  const pickResource = useCallback(
    (worldX: number, worldY: number) => {
      for (let i = scene.resources.length - 1; i >= 0; i--) {
        const res = scene.resources[i];
        const type = typeById[res.typeId];
        const local = worldToLocal(res, worldX, worldY);
        if (type.geometry && type.geometry.length >= 3) {
          if (pointInPolygon(local.x, local.y, type.geometry)) {
            return { res, local };
          }
        } else {
          const { width: w, height: h } = type.footprint;
          if (Math.abs(local.x) <= w / 2 && Math.abs(local.y) <= h / 2) {
            return { res, local };
          }
        }
      }
      return null;
    },
    [scene.resources, typeById],
  );

  const pickConnection = useCallback(
    (worldX: number, worldY: number) => {
      for (let i = scene.connections.length - 1; i >= 0; i--) {
        const c = scene.connections[i];
        const s = worldToScreen(c.worldPosition.x, c.worldPosition.y);
        const ws = worldToScreen(worldX, worldY);
        const dx = s.x - ws.x;
        const dy = s.y - ws.y;
        if (dx * dx + dy * dy <= 10 * 10) return c;
      }
      return null;
    },
    [scene.connections, worldToScreen],
  );

  const pickZone = useCallback(
    (worldX: number, worldY: number) => {
      for (let i = scene.resources.length - 1; i >= 0; i--) {
        const res = scene.resources[i];
        const zones = getEffectiveZones(res, typeById);
        for (let j = zones.length - 1; j >= 0; j--) {
          const zone = zones[j];
          const poly = zoneToWorldPolygon(res, zone.polygon);
          if (pointInPolygon(worldX, worldY, poly)) {
            return { res, zone };
          }
        }
      }
      return null;
    },
    [scene.resources, typeById],
  );

  const pickOverlapRegion = useCallback(
    (worldX: number, worldY: number) => {
      for (const region of pendingOverlaps) {
        if (pointInPolygon(worldX, worldY, region.polygon)) return region;
      }
      return null;
    },
    [pendingOverlaps],
  );

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
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

      const connHit = pickConnection(world.x, world.y);
      if (connHit) {
        setSelectedConnectionId(connHit.id);
        if (
          connHit.resourceAId === selectedId ||
          connHit.resourceBId === selectedId
        ) {
          // keep resource selection
        } else {
          setSelectedId(connHit.resourceAId);
        }
        setDrag({
          kind: "connection",
          connectionId: connHit.id,
          moved: false,
        });
        return;
      }

      const hit = pickResource(world.x, world.y);
      if (hit) {
        const zoneHit = pickZone(world.x, world.y);
        if (
          zoneHit &&
          zoneHit.res.instanceId === hit.res.instanceId &&
          selectedId === hit.res.instanceId
        ) {
          setSelectedZoneKey(`${zoneHit.res.instanceId}:${zoneHit.zone.id}`);
          return;
        }
        setSelectedId(hit.res.instanceId);
        setSelectedZoneKey(null);
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
        setSelectedZoneKey(null);
        setSelectedId(null);
        setDrag({
          kind: "pan",
          startX: e.clientX,
          startY: e.clientY,
          origOffset: { ...view },
        });
      }
    },
    [
      canvasRef,
      commit,
      connectFirst,
      mode,
      newZoneType,
      pickConnection,
      pickOverlapRegion,
      pickResource,
      pickZone,
      screenToWorld,
      selectedId,
      setConnectFirst,
      setDrag,
      setMode,
      setSelectedConnectionId,
      setSelectedId,
      setSelectedZoneKey,
      setZoneDraw,
      view,
    ],
  );

  const onMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
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
        setDrag((d) => (d ? { ...d, moved: true } : d));
      } else if (drag.kind === "connection") {
        let nx = world.x;
        let ny = world.y;
        if (snapToGrid) {
          nx = Math.round(nx / MM_PER_GRID) * MM_PER_GRID;
          ny = Math.round(ny / MM_PER_GRID) * MM_PER_GRID;
        }
        mutate((s) => {
          const conn = s.connections.find((c) => c.id === drag.connectionId);
          if (!conn) return s;
          const resA = s.resources.find(
            (r) => r.instanceId === conn.resourceAId,
          );
          const resB = s.resources.find(
            (r) => r.instanceId === conn.resourceBId,
          );
          if (!resA || !resB) return s;
          const localA = worldToLocal(resA, nx, ny);
          const localB = worldToLocal(resB, nx, ny);
          return {
            ...s,
            connections: s.connections.map((c) =>
              c.id === drag.connectionId
                ? {
                    ...c,
                    worldPosition: { x: nx, y: ny },
                    localPositionA: { x: localA.x, y: localA.y },
                    localPositionB: { x: localB.x, y: localB.y },
                  }
                : c,
            ),
          };
        });
        setDrag((d) => (d ? { ...d, moved: true } : d));
      } else if (drag.kind === "draw-zone" && zoneDraw) {
        const res = scene.resources.find(
          (r) => r.instanceId === zoneDraw.resourceId,
        );
        if (!res) return;
        const local = worldToLocal(res, world.x, world.y);
        setZoneDraw((z) =>
          z ? { ...z, currentLocal: { x: local.x, y: local.y } } : z,
        );
      }
    },
    [
      canvasRef,
      drag,
      mutate,
      pickResource,
      screenToWorld,
      setHoverResourceId,
      setView,
      scene.resources,
      snapToGrid,
      zoneDraw,
    ],
  );

  const onMouseUp = useCallback(() => {
    if (drag?.kind === "resource" && drag.moved) snapshot();
    if (drag?.kind === "connection" && drag.moved) snapshot();

    if (drag?.kind === "draw-zone" && zoneDraw) {
      const { startLocal, currentLocal, resourceId, type } = zoneDraw;
      const minSize = 50;
      if (
        Math.abs(startLocal.x - currentLocal.x) > minSize &&
        Math.abs(startLocal.y - currentLocal.y) > minSize
      ) {
        const x1 = Math.min(startLocal.x, currentLocal.x);
        const x2 = Math.max(startLocal.x, currentLocal.x);
        const y1 = Math.min(startLocal.y, currentLocal.y);
        const y2 = Math.max(startLocal.y, currentLocal.y);
        const polygon: [number, number][] = [
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
                      label: `Custom ${type}`,
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
    }
    setDrag(null);
  }, [commit, drag, snapshot, zoneDraw, setDrag, setZoneDraw]);

  const onWheel = useCallback(
    (e: WheelEvent) => {
      e.preventDefault();
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
      const worldBefore = screenToWorld(sx, sy);
      const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
      const newScale = Math.max(0.02, Math.min(2, view.scale * factor));
      setView({
        scale: newScale,
        offsetX: sx - worldBefore.x * newScale,
        offsetY: sy - worldBefore.y * newScale,
      });
    },
    [canvasRef, screenToWorld, setView, view.scale],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [canvasRef, onWheel]);

  const onDragOver = useCallback((e: React.DragEvent) => {
    if (e.dataTransfer.types.includes("application/x-resource-type")) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    }
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const typeId = e.dataTransfer.getData("application/x-resource-type");
      if (!typeId) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
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
    },
    [canvasRef, commit, screenToWorld, setSelectedId, snapToGrid],
  );

  return (
    <canvas
      ref={canvasRef}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
      onDragOver={onDragOver}
      onDrop={onDrop}
      className="w-full h-full cursor-crosshair"
    />
  );
}
