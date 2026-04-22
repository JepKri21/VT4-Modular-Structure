"use client";

import React from "react";
import { RotateCw, Trash2, X, AlertTriangle } from "lucide-react";
import type { Scene, TypeById, ZoneType } from "./lib/types";
import { localToWorld, worldToLocal, getEffectiveZones } from "./lib/geometry";

interface InspectorProps {
  selectedId: string | null;
  scene: Scene;
  typeById: TypeById;
  commit: (updater: Scene | ((prev: Scene) => Scene)) => void;
  setSelectedId: (id: string | null) => void;
  selectedConnectionId: string | null;
  setSelectedConnectionId: (id: string | null) => void;
  invalidConnectionIds: Set<string>;
  selectedZoneKey: string | null;
  setSelectedZoneKey: (key: string | null) => void;
}

function InspectorRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-[80px_1fr] items-center gap-2 mb-2 text-xs">
      <div className="text-primary">{label}</div>
      <div>{children}</div>
    </div>
  );
}

function NumInput({
  value,
  onChange,
  suffix,
}: {
  value: number;
  onChange: (v: number) => void;
  suffix?: string;
}) {
  return (
    <div className="flex items-center border border-primary bg-muted rounded">
      <input
        type="number"
        value={Math.round(value)}
        onChange={(e) => onChange(Number(e.target.value))}
        className="flex-1 bg-transparent border-none text-primary px-2 py-1 text-xs font-mono outline-none"
      />
      {suffix && <span className="text-primary px-2 text-xs">{suffix}</span>}
    </div>
  );
}

export function Inspector({
  selectedId,
  scene,
  typeById,
  commit,
  setSelectedId,
  selectedConnectionId,
  setSelectedConnectionId,
  invalidConnectionIds,
  selectedZoneKey,
  setSelectedZoneKey,
}: InspectorProps) {
  const selected = scene.resources.find((r) => r.instanceId === selectedId);
  const selectedType = selected ? typeById[selected.typeId] : null;

  const selectedConnections = selected
    ? scene.connections.filter(
        (c) =>
          c.resourceAId === selected.instanceId ||
          c.resourceBId === selected.instanceId,
      )
    : [];

  const rotateResource = (instanceId: string, deltaDeg: number) => {
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

  if (!selected || !selectedType) {
    return (
      <aside className="border-l border-muted p-4 overflow-y-auto bg-muted">
        <div className="text-xs uppercase tracking-widest text-primary mb-3">
          INSPECTOR
        </div>
        <div className="text-primary text-xs mt-4">
          No resource selected. Click a resource on the canvas to inspect its
          properties.
        </div>
      </aside>
    );
  }

  return (
    <aside className="border-l border-muted p-4 overflow-y-auto bg-muted">
      <div className="text-xs uppercase tracking-widest text-primary mb-3">
        INSPECTOR
      </div>
      <div>
        <div
          className="p-3 mb-4 border-l-4"
          style={{ borderLeftColor: selectedType.color }}
        >
          <div className="text-primary font-medium text-sm">
            {selectedType.name}
          </div>
          <div className="text-gray-1000 text-xs mt-1">
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
                  connections: s.connections.map((c) => ({
                    ...c,
                    worldPosition:
                      c.resourceAId === selectedId
                        ? { x: v, y: c.worldPosition.y }
                        : c.resourceBId === selectedId
                          ? { x: v, y: c.worldPosition.y }
                          : c.worldPosition,
                  })),
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
                  connections: s.connections.map((c) => ({
                    ...c,
                    worldPosition:
                      c.resourceAId === selectedId
                        ? { x: c.worldPosition.x, y: v }
                        : c.resourceBId === selectedId
                          ? { x: c.worldPosition.x, y: v }
                          : c.worldPosition,
                  })),
                };
              })
            }
            suffix="mm"
          />
        </InspectorRow>

        <InspectorRow label="Rotation">
          <div className="flex gap-2 items-center">
            <NumInput
              value={selected.rotation}
              onChange={(v) => {
                const delta = (((v - selected.rotation) % 360) + 360) % 360;
                rotateResource(selected.instanceId, delta);
              }}
              suffix="°"
            />
            <button
              onClick={() => rotateResource(selected.instanceId, 90)}
              className="bg-gray-700 border border-gray-600 text-gray-400 px-2 py-1 text-xs"
              title="Rotate +90°"
            >
              <RotateCw size={11} />
            </button>
          </div>
        </InspectorRow>

        <InspectorRow label="Footprint">
          <div className="text-primary">
            {selectedType.footprint.width} × {selectedType.footprint.height} mm
          </div>
        </InspectorRow>

        {(() => {
          const allZones = getEffectiveZones(selected, typeById);
          const zoneKey = selectedZoneKey;
          const parsedZoneId =
            zoneKey && zoneKey.startsWith(`${selected.instanceId}:`)
              ? zoneKey.slice(selected.instanceId.length + 1)
              : null;
          const activeZone = parsedZoneId
            ? allZones.find((z) => z.id === parsedZoneId) || null
            : null;
          const zoneMeta = {
            infeed: { label: "Infeed", color: "#22c55e" },
            outfeed: { label: "Outfeed", color: "#3b82f6" },
            inout: { label: "In/Out", color: "#a855f7" },
          } as const;

          return (
            <div className="mt-6">
              <div className="text-xs uppercase tracking-widest text-primary mb-2">
                WORK AREAS ({allZones.length})
              </div>
              {allZones.map((zone) => {
                const isCustom = (selected.customZones || []).some(
                  (c) => c.id === zone.id,
                );
                const isActive =
                  zoneKey === `${selected.instanceId}:${zone.id}`;
                const meta = zoneMeta[zone.type];
                return (
                  <div
                    key={zone.id}
                    onClick={() =>
                      setSelectedZoneKey(`${selected.instanceId}:${zone.id}`)
                    }
                    className={`cursor-pointer border p-2 mb-2 text-xs flex items-start justify-between gap-3 ${
                      isActive
                        ? "border-card bg-primary"
                        : "border-primary hover:border-secondary"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <div
                        className="w-3 h-3 mt-0.5 border border-primary"
                        style={{ backgroundColor: meta.color }}
                      />
                      <div>
                        <div
                          className={`
                        ${isActive ? "text-background" : "text-primary"}`}
                        >
                          {zone.label}
                        </div>
                        <div
                          className={`text-[11px] mt-1
                        ${isActive ? "text-background" : "text-primary"}`}
                        >
                          {meta.label}
                          {isCustom ? " (custom)" : ""}
                        </div>
                      </div>
                    </div>
                    {isCustom && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          commit((s) => ({
                            ...s,
                            resources: s.resources.map((r) =>
                              r.instanceId === selectedId
                                ? {
                                    ...r,
                                    customZones: r.customZones.filter(
                                      (cz) => cz.id !== zone.id,
                                    ),
                                  }
                                : r,
                            ),
                          }));
                          if (isActive) setSelectedZoneKey(null);
                        }}
                        className="text-background hover:text-card"
                      >
                        <X size={12} />
                      </button>
                    )}
                  </div>
                );
              })}

              {activeZone && (
                <div className="border border-primary p-2 mb-2 text-xs bg-muted">
                  <div className="text-primary text-[11px] mb-2">
                    Change type for "{activeZone.label}"
                  </div>
                  <div className="flex gap-1">
                    {(["infeed", "outfeed", "inout"] as const).map((t) => {
                      const m = zoneMeta[t];
                      const active = activeZone.type === t;
                      return (
                        <button
                          key={t}
                          type="button"
                          onClick={() => {
                            const isCustom = (selected.customZones || []).some(
                              (c) => c.id === activeZone.id,
                            );
                            commit((s) => ({
                              ...s,
                              resources: s.resources.map((r) => {
                                if (r.instanceId !== selectedId) return r;
                                if (isCustom) {
                                  return {
                                    ...r,
                                    customZones: r.customZones.map((cz) =>
                                      cz.id === activeZone.id
                                        ? { ...cz, type: t }
                                        : cz,
                                    ),
                                  };
                                }
                                return {
                                  ...r,
                                  zoneOverrides: {
                                    ...(r.zoneOverrides || {}),
                                    [activeZone.id]: t,
                                  },
                                };
                              }),
                            }));
                          }}
                          className={`flex-1 px-2 py-1 border flex items-center justify-center gap-1 ${
                            active
                              ? "border-yellow-500 text-gray-100"
                              : "border-gray-600 text-gray-400 hover:border-gray-500"
                          }`}
                        >
                          <div
                            className="w-2.5 h-2.5 border border-gray-600"
                            style={{ backgroundColor: m.color }}
                          />
                          {m.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })()}

        <div className="mt-6">
          <div className="text-xs uppercase tracking-widest text-primary mb-2">
            CONNECTIONS ({selectedConnections.length})
          </div>
          {selectedConnections.length === 0 ? (
            <div className="text-primary text-xs">
              No connections. Use link mode and click on an overlap region to
              connect.
            </div>
          ) : (
            selectedConnections.map((connection) => {
              const otherId =
                connection.resourceAId === selected.instanceId
                  ? connection.resourceBId
                  : connection.resourceAId;
              const other = scene.resources.find(
                (r) => r.instanceId === otherId,
              );
              const otherType = other ? typeById[other.typeId] : null;
              const thisZoneId =
                connection.resourceAId === selected.instanceId
                  ? connection.zoneAId
                  : connection.zoneBId;
              const thisZoneType =
                connection.resourceAId === selected.instanceId
                  ? connection.zoneAType
                  : connection.zoneBType;
              const thisLocal =
                connection.resourceAId === selected.instanceId
                  ? connection.localPositionA
                  : connection.localPositionB;
              const isConnectionSelected =
                connection.id === selectedConnectionId;
              const isInvalid = invalidConnectionIds.has(connection.id);

              const sel = selected;
              const isASide = connection.resourceAId === sel.instanceId;
              const updateConnWorld = (wx: number, wy: number) => {
                commit((s) => ({
                  ...s,
                  connections: s.connections.map((c) => {
                    if (c.id !== connection.id) return c;
                    const resA = s.resources.find(
                      (r) => r.instanceId === c.resourceAId,
                    );
                    const resB = s.resources.find(
                      (r) => r.instanceId === c.resourceBId,
                    );
                    if (!resA || !resB) return c;
                    const la = worldToLocal(resA, wx, wy);
                    const lb = worldToLocal(resB, wx, wy);
                    return {
                      ...c,
                      worldPosition: { x: wx, y: wy },
                      localPositionA: { x: la.x, y: la.y },
                      localPositionB: { x: lb.x, y: lb.y },
                    };
                  }),
                }));
              };
              const updateConnLocal = (lx: number, ly: number) => {
                commit((s) => ({
                  ...s,
                  connections: s.connections.map((c) => {
                    if (c.id !== connection.id) return c;
                    const resA = s.resources.find(
                      (r) => r.instanceId === c.resourceAId,
                    );
                    const resB = s.resources.find(
                      (r) => r.instanceId === c.resourceBId,
                    );
                    if (!resA || !resB) return c;
                    const thisRes = isASide ? resA : resB;
                    const otherRes = isASide ? resB : resA;
                    const world = localToWorld(thisRes, lx, ly);
                    const otherLocal = worldToLocal(otherRes, world.x, world.y);
                    return {
                      ...c,
                      worldPosition: { x: world.x, y: world.y },
                      localPositionA: isASide
                        ? { x: lx, y: ly }
                        : { x: otherLocal.x, y: otherLocal.y },
                      localPositionB: isASide
                        ? { x: otherLocal.x, y: otherLocal.y }
                        : { x: lx, y: ly },
                    };
                  }),
                }));
              };
              return (
                <div
                  key={connection.id}
                  onClick={() => setSelectedConnectionId(connection.id)}
                  className={`cursor-pointer w-full text-left border p-2 mb-2 text-xs ${
                    isConnectionSelected
                      ? "border-yellow-500 bg-muted"
                      : "border-gray-600 bg-muted hover:border-gray-500"
                  }`}
                >
                  <div className="flex justify-between items-center gap-2">
                    <span className="text-primary">
                      ↔ {otherType?.name ?? "Unknown"}
                    </span>
                    <div className="flex items-center gap-2">
                      {isInvalid ? (
                        <span className="inline-flex items-center gap-1 text-red-500 text-[11px]">
                          <AlertTriangle size={12} /> Invalid
                        </span>
                      ) : null}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          commit((s) => ({
                            ...s,
                            connections: s.connections.filter(
                              (c) => c.id !== connection.id,
                            ),
                          }));
                          if (selectedConnectionId === connection.id) {
                            setSelectedConnectionId(null);
                          }
                        }}
                        className="text-primary hover:text-gray-100"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                  <div className="text-gray-400 mt-1 text-[11px]">
                    {thisZoneId} ({thisZoneType})
                  </div>
                  {isConnectionSelected ? (
                    <div
                      className="mt-2 space-y-2"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="text-gray-400 text-[11px]">
                        Local (this resource)
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <NumInput
                          value={thisLocal.x}
                          onChange={(v) => updateConnLocal(v, thisLocal.y)}
                          suffix="mm"
                        />
                        <NumInput
                          value={thisLocal.y}
                          onChange={(v) => updateConnLocal(thisLocal.x, v)}
                          suffix="mm"
                        />
                      </div>
                      <div className="text-gray-400 text-[11px]">Global</div>
                      <div className="grid grid-cols-2 gap-2">
                        <NumInput
                          value={connection.worldPosition.x}
                          onChange={(v) =>
                            updateConnWorld(v, connection.worldPosition.y)
                          }
                          suffix="mm"
                        />
                        <NumInput
                          value={connection.worldPosition.y}
                          onChange={(v) =>
                            updateConnWorld(connection.worldPosition.x, v)
                          }
                          suffix="mm"
                        />
                      </div>
                      <div className="text-gray-500 text-[11px]">
                        Tip: drag the point on the canvas to reposition.
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="text-gray-400 text-[11px] mt-1">
                        local: {Math.round(thisLocal.x)},{" "}
                        {Math.round(thisLocal.y)} mm
                      </div>
                      <div className="text-gray-400 text-[11px] mt-1">
                        world: {Math.round(connection.worldPosition.x)},{" "}
                        {Math.round(connection.worldPosition.y)} mm
                      </div>
                    </>
                  )}
                </div>
              );
            })
          )}
        </div>

        <button
          type="button"
          onClick={() => {
            commit((s) => ({
              ...s,
              resources: s.resources.filter((r) => r.instanceId !== selectedId),
              connections: s.connections.filter(
                (c) =>
                  c.resourceAId !== selectedId && c.resourceBId !== selectedId,
              ),
            }));
            setSelectedId(null);
          }}
          className="mt-4 w-full rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-500 hover:bg-red-500/20"
        >
          <div className="flex items-center justify-center gap-2">
            <Trash2 size={12} />
            Remove resource
          </div>
        </button>
      </div>
    </aside>
  );
}
