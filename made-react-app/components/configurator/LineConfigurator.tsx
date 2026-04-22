"use client";

import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  useMemo,
} from "react";
import { useHistory } from "./hooks/useHistory";
import { useSceneTransforms } from "./hooks/useSceneTransforms";
import { useZoneOverlaps } from "./hooks/useZoneOverlaps";
import { localToWorld } from "./lib/geometry";
import { exportLineConfiguration } from "./lib/aasExport";
import { fetchResourceLibrary } from "./lib/aasFetch";
import type {
  Scene,
  ZoneType,
  ResourceType,
  TypeById,
  EditorMode,
  ViewTransform,
  DragState,
  ZoneDraw,
  PendingOverlap,
} from "./lib/types";

import { ResourcePalette } from "./ResourcePalette";
import { CanvasView } from "./CanvasView";
import { Inspector } from "./Inspector";
import { Toolbar } from "./Toolbar";

export default function LineConfigurator() {
  const [library, setLibrary] = useState<ResourceType[]>([]);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [libraryLoading, setLibraryLoading] = useState(true);

  const reloadLibrary = useCallback(async () => {
    setLibraryLoading(true);
    try {
      const lib = await fetchResourceLibrary();
      setLibrary(lib);
      setLibraryError(null);
    } catch (e) {
      setLibraryError(e instanceof Error ? e.message : String(e));
    } finally {
      setLibraryLoading(false);
    }
  }, []);

  useEffect(() => {
    reloadLibrary();
  }, [reloadLibrary]);

  const typeById = useMemo(
    () =>
      Object.fromEntries(library.map((t) => [t.typeId, t])) as TypeById,
    [library],
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
  } = useHistory<Scene>({ resources: [], connections: [] });

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [view, setView] = useState<ViewTransform>({
    scale: 0.15,
    offsetX: 400,
    offsetY: 300,
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoverResourceId, setHoverResourceId] = useState<string | null>(null);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [mode, setMode] = useState<EditorMode>("select");
  const [snapToGrid, setSnapToGrid] = useState(true);
  const [alwaysShowZones, setAlwaysShowZones] = useState(false);
  const [connectFirst, setConnectFirst] = useState<string | null>(null);
  const [pendingOverlaps, setPendingOverlaps] = useState<PendingOverlap[]>([]);
  const [selectedConnectionId, setSelectedConnectionId] = useState<
    string | null
  >(null);
  const [zoneDraw, setZoneDraw] = useState<ZoneDraw | null>(null);
  const [newZoneType, setNewZoneType] = useState<ZoneType>("inout");
  const [selectedZoneKey, setSelectedZoneKey] = useState<string | null>(null);

  const { worldToScreen, screenToWorld } = useSceneTransforms(view);
  const { overlaps, overlapSet, computeZoneOverlaps, isConnectionValid } =
    useZoneOverlaps(scene, typeById);

  // Zone overlap computation for pending connections
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
    const all: PendingOverlap[] = [];
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

  const invalidConnectionIds = useMemo(
    () =>
      new Set(
        scene.connections.filter((c) => !isConnectionValid(c)).map((c) => c.id),
      ),
    [scene.connections, isConnectionValid],
  );

  useEffect(() => {
    if (!selectedId) {
      setSelectedConnectionId(null);
      return;
    }
    if (!selectedConnectionId) return;
    const belongsToSelected = scene.connections.some(
      (c) =>
        c.id === selectedConnectionId &&
        (c.resourceAId === selectedId || c.resourceBId === selectedId),
    );
    if (!belongsToSelected) {
      setSelectedConnectionId(null);
    }
  }, [scene.connections, selectedConnectionId, selectedId]);

  useEffect(() => {
    const isEditable = (t: EventTarget | null): boolean => {
      const el = t as HTMLElement | null;
      if (!el) return false;
      const tag = el.tagName;
      return (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        el.isContentEditable === true
      );
    };

    const onKey = (e: KeyboardEvent) => {
      if (isEditable(e.target)) return;

      const meta = e.metaKey || e.ctrlKey;
      if (meta && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
        return;
      }
      if (meta && e.key.toLowerCase() === "y") {
        e.preventDefault();
        redo();
        return;
      }

      if (e.key === "Escape") {
        setMode("select");
        setConnectFirst(null);
        setZoneDraw(null);
        setSelectedZoneKey(null);
        return;
      }

      if (e.key.toLowerCase() === "r" && selectedId) {
        e.preventDefault();
        commit((s) => {
          const res = s.resources.find((r) => r.instanceId === selectedId);
          if (!res) return s;
          const newRes = { ...res, rotation: (res.rotation + 90) % 360 };
          return {
            ...s,
            resources: s.resources.map((r) =>
              r.instanceId === selectedId ? newRes : r,
            ),
            connections: s.connections.map((c) => {
              if (c.resourceAId === selectedId)
                return {
                  ...c,
                  worldPosition: localToWorld(
                    newRes,
                    c.localPositionA.x,
                    c.localPositionA.y,
                  ),
                };
              if (c.resourceBId === selectedId)
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
        return;
      }

      if (e.key === "Backspace" || e.key === "Delete") {
        if (selectedConnectionId) {
          e.preventDefault();
          commit((s) => ({
            ...s,
            connections: s.connections.filter(
              (c) => c.id !== selectedConnectionId,
            ),
          }));
          setSelectedConnectionId(null);
          return;
        }
        if (selectedId) {
          e.preventDefault();
          commit((s) => ({
            ...s,
            resources: s.resources.filter((r) => r.instanceId !== selectedId),
            connections: s.connections.filter(
              (c) => c.resourceAId !== selectedId && c.resourceBId !== selectedId,
            ),
          }));
          setSelectedId(null);
          setSelectedZoneKey(null);
        }
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    commit,
    redo,
    selectedConnectionId,
    selectedId,
    undo,
  ]);

  // Placeholder handlers
  const onPaletteDragStart = useCallback(
    (e: React.DragEvent, typeId: string) => {
      e.dataTransfer.setData("application/x-resource-type", typeId);
      e.dataTransfer.effectAllowed = "copy";
    },
    [],
  );

  const handleExport = useCallback(() => {
    exportLineConfiguration(scene, typeById);
  }, [scene, typeById]);

  const placedTypeIds = useMemo(
    () => new Set(scene.resources.map((r) => r.typeId)),
    [scene.resources],
  );

  return (
    <div className="grid grid-cols-[240px_1fr_320px] h-screen bg-gray-900 text-gray-400 font-mono text-xs">
      <ResourcePalette
        onPaletteDragStart={onPaletteDragStart}
        library={library}
        placedTypeIds={placedTypeIds}
        loading={libraryLoading}
        error={libraryError}
      />
      <div className="relative">
        <Toolbar
          mode={mode}
          setMode={setMode}
          canUndo={canUndo}
          canRedo={canRedo}
          undo={undo}
          redo={redo}
          snapToGrid={snapToGrid}
          setSnapToGrid={setSnapToGrid}
          alwaysShowZones={alwaysShowZones}
          setAlwaysShowZones={setAlwaysShowZones}
          overlaps={overlaps}
          newZoneType={newZoneType}
          setNewZoneType={setNewZoneType}
          invalidConnectionCount={invalidConnectionIds.size}
          handleExport={handleExport}
          onRefreshLibrary={reloadLibrary}
          libraryLoading={libraryLoading}
        />
        <CanvasView
          canvasRef={canvasRef}
          scene={scene}
          view={view}
          setView={setView}
          mode={mode}
          selectedId={selectedId}
          setSelectedId={setSelectedId}
          hoverResourceId={hoverResourceId}
          setHoverResourceId={setHoverResourceId}
          overlapSet={overlapSet}
          connectFirst={connectFirst}
          setConnectFirst={setConnectFirst}
          pendingOverlaps={pendingOverlaps}
          alwaysShowZones={alwaysShowZones}
          zoneDraw={zoneDraw}
          setZoneDraw={setZoneDraw}
          typeById={typeById}
          drag={drag}
          setDrag={setDrag}
          commit={commit}
          mutate={mutate}
          snapshot={snapshot}
          worldToScreen={worldToScreen}
          screenToWorld={screenToWorld}
          snapToGrid={snapToGrid}
          newZoneType={newZoneType}
          setMode={setMode}
          selectedConnectionId={selectedConnectionId}
          setSelectedConnectionId={setSelectedConnectionId}
          invalidConnectionIds={invalidConnectionIds}
          selectedZoneKey={selectedZoneKey}
          setSelectedZoneKey={setSelectedZoneKey}
        />
      </div>
      <Inspector
        selectedId={selectedId}
        scene={scene}
        typeById={typeById}
        commit={commit}
        setSelectedId={setSelectedId}
        selectedConnectionId={selectedConnectionId}
        setSelectedConnectionId={setSelectedConnectionId}
        invalidConnectionIds={invalidConnectionIds}
        selectedZoneKey={selectedZoneKey}
        setSelectedZoneKey={setSelectedZoneKey}
      />
    </div>
  );
}
