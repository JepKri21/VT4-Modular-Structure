import React from "react";
import { ZONE_COLORS } from "./lib/resourceLibrary";
import type { ResourceType } from "./lib/types";

interface ResourcePaletteProps {
  onPaletteDragStart: (e: React.DragEvent, typeId: string) => void;
  library: ResourceType[];
  placedTypeIds: Set<string>;
  loading: boolean;
  error: string | null;
}

export function ResourcePalette({
  onPaletteDragStart,
  library,
  placedTypeIds,
  loading,
  error,
}: ResourcePaletteProps) {
  return (
    <aside className="border-r border-primary p-4 overflow-y-auto bg-muted">
      <div className="text-xs uppercase tracking-widest text-primary">
        RESOURCE LIBRARY
      </div>

      {loading && (
        <div className="text-primary text-xs mt-2">Loading from AAS…</div>
      )}
      {error && (
        <div className="text-red-500 text-xs mt-2 wrap-break-word">
          Failed to load resources: {error}
        </div>
      )}
      {!loading && !error && library.length === 0 && (
        <div className="text-primary text-xs mt-2">
          No resources with a ResourceZones submodel found on the AAS server.
        </div>
      )}

      <div className="flex flex-col gap-2 mt-2">
        {library.map((t) => {
          const isPlaced = placedTypeIds.has(t.typeId);
          return (
            <div
              key={t.typeId}
              draggable={!isPlaced}
              onDragStart={(e) => {
                if (isPlaced) {
                  e.preventDefault();
                  return;
                }
                onPaletteDragStart(e, t.typeId);
              }}
              className={`border border-secondary border-l-4 p-3 bg-background ${
                isPlaced
                  ? "opacity-40 cursor-not-allowed"
                  : "cursor-grab hover:bg-card"
              }`}
              style={{ borderLeftColor: t.color }}
              title={isPlaced ? "Already placed" : t.typeId}
            >
              <div className="text-primary font-medium">
                {t.name}
                {isPlaced && (
                  <span className="ml-2 text-[10px] uppercase tracking-wider text-primary/70">
                    placed
                  </span>
                )}
              </div>
              <div className="text-primary text-xs mt-1">
                {Math.round(t.footprint.width)}×{Math.round(t.footprint.height)} mm
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-6 text-xs uppercase tracking-widest text-primary mb-2">
        ZONE TYPES
      </div>
      <div className="flex flex-col gap-2">
        {Object.entries(ZONE_COLORS).map(([key, col]) => (
          <div key={key} className="flex items-center gap-3 text-xs">
            <div
              className="w-4 h-4 border border-gray-600"
              style={{ backgroundColor: col.stroke }}
            />
            <span className="text-primary">{col.label}</span>
          </div>
        ))}
      </div>

      <div className="mt-6 text-xs uppercase tracking-widest text-primary mb-2">
        SHORTCUTS
      </div>
      <div className="text-primary text-xs leading-relaxed">
        <div>drag from palette → place</div>
        <div>R → rotate 90°</div>
        <div>⌫ → delete selected</div>
        <div>alt+drag / wheel → pan / zoom</div>
        <div>⌘Z / ⌘⇧Z → undo / redo</div>
        <div>esc → cancel mode</div>
      </div>
    </aside>
  );
}
