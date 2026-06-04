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
import {
  buildLineConfigurationSubmodel,
  buildServiceOfferedSubmodel,
  exportLineConfiguration,
} from "./lib/aasExport";
import {
  AAS_SERVER_URL,
  fetchLineConfiguration,
  fetchProductionLines,
  fetchResourceCapabilities,
  fetchResourceLibrary,
} from "./lib/aasFetch";
import type {
  ProductionLineShell,
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
  const [productionLines, setProductionLines] = useState<ProductionLineShell[]>([]);
  const [selectedLine, setSelectedLine] = useState<string | null>(null);
  const [loadingLine, setLoadingLine] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "ok" | "error">("idle");
  const [staleCount, setStaleCount] = useState(0);

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

  useEffect(() => {
    fetchProductionLines().then(setProductionLines).catch(() => {});
  }, []);

  const typeById = useMemo(
    () =>
      Object.fromEntries(library.map((t) => [t.typeId, t])) as TypeById,
    [library],
  );
  // Ref so the line-load effect can filter stale resources without being in its deps
  const typeByIdRef = useRef<TypeById>(typeById);
  useEffect(() => { typeByIdRef.current = typeById; }, [typeById]);

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

  useEffect(() => {
    if (!selectedLine) return;
    const line = productionLines.find((l) => l.id === selectedLine);
    const submodelId =
      line?.lineConfigSubmodelId ?? `${selectedLine}/Submodels/LineConfiguration`;
    setLoadingLine(true);
    fetchLineConfiguration(submodelId, AAS_SERVER_URL, library)
      .then((loaded) => {
        const known = typeByIdRef.current;
        const validResources = loaded.resources.filter((r) => known[r.typeId]);
        const removed = loaded.resources.length - validResources.length;
        const validIds = new Set(validResources.map((r) => r.instanceId));
        const validConnections = loaded.connections.filter(
          (c) => validIds.has(c.resourceAId) && validIds.has(c.resourceBId),
        );
        setStaleCount(removed);
        commit({ resources: validResources, connections: validConnections });
      })
      .catch(() => {})
      .finally(() => setLoadingLine(false));
  // Only re-run when the selected line changes, not on library/productionLines updates.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLine]);

  const handleSave = useCallback(async () => {
    if (!selectedLine || saving) return;
    setSaving(true);
    setSaveStatus("idle");
    try {
      const line = productionLines.find((l) => l.id === selectedLine);
      const lineConfigId =
        line?.lineConfigSubmodelId ?? `${selectedLine}/Submodels/LineConfiguration`;
      const serviceOfferedId =
        line?.serviceOfferedSubmodelId ?? `${selectedLine}/Submodels/ServiceOffered`;

      const capabilities = await fetchResourceCapabilities(
        scene.resources.map((r) => r.typeId),
      );
      const lineConfigSM = buildLineConfigurationSubmodel(lineConfigId, scene, typeById);
      const serviceOfferedSM = buildServiceOfferedSubmodel(serviceOfferedId, capabilities);
      const res = await fetch("/api/line-configurator/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          serverUrl: AAS_SERVER_URL,
          submodels: [lineConfigSM, serviceOfferedSM],
        }),
      });
      setSaveStatus(res.ok ? "ok" : "error");
    } catch {
      setSaveStatus("error");
    } finally {
      setSaving(false);
    }
  }, [selectedLine, saving, scene, typeById, productionLines]);

  const handleExport = useCallback(() => {
    exportLineConfiguration(scene, typeById);
  }, [scene, typeById]);

  const placedTypeIds = useMemo(
    () => new Set(scene.resources.map((r) => r.typeId)),
    [scene.resources],
  );

  return (
    <div className="flex flex-col h-screen bg-gray-900 text-gray-400 font-mono text-xs">
      {/* Line selector header */}
      <div className="flex items-center gap-2 px-3 py-2 bg-gray-800 border-b border-gray-700 shrink-0">
        <span className="text-gray-500">Line:</span>
        <select
          className="bg-gray-900 border border-gray-600 rounded px-2 py-1 text-gray-300 text-xs"
          value={selectedLine ?? ""}
          onChange={(e) => {
            const val = e.target.value || null;
            setSelectedLine(val);
            setSaveStatus("idle");
            if (!val) commit({ resources: [], connections: [] });
          }}
        >
          <option value="">— none selected —</option>
          {productionLines.map((l) => (
            <option key={l.id} value={l.id}>{l.idShort}</option>
          ))}
        </select>
        {loadingLine && <span className="text-gray-400 italic">Loading…</span>}
        <button
          className="px-3 py-1 rounded bg-blue-700 hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed"
          disabled={!selectedLine || saving}
          onClick={() => { void handleSave(); }}
        >
          {saving ? "Saving…" : "Save to BaSyx"}
        </button>
        {saveStatus === "ok" && <span className="text-green-400">Saved</span>}
        {saveStatus === "error" && <span className="text-red-400">Save failed</span>}
        <button
          className="ml-auto px-3 py-1 rounded bg-red-900 hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed text-red-300"
          disabled={!selectedLine}
          title="Clear all resources and connections from the current line config"
          onClick={() => { commit({ resources: [], connections: [] }); setStaleCount(0); }}
        >
          Reset config
        </button>
      </div>
      {staleCount > 0 && (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-yellow-900/60 border-b border-yellow-700 text-yellow-300 text-xs shrink-0">
          <span>⚠ {staleCount} resource{staleCount > 1 ? "s" : ""} removed — their types are no longer on the AAS server.</span>
          <button className="ml-auto hover:text-yellow-100" onClick={() => setStaleCount(0)}>✕</button>
        </div>
      )}
      <div className="grid grid-cols-[240px_1fr_320px] flex-1 min-h-0">
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
    </div>
  );
}
