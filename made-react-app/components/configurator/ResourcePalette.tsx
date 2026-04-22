import React from "react";
import { RESOURCE_LIBRARY, ZONE_COLORS } from "./lib/resourceLibrary";

interface ResourcePaletteProps {
  onPaletteDragStart: (e: React.DragEvent, typeId: string) => void;
}

export function ResourcePalette({ onPaletteDragStart }: ResourcePaletteProps) {
  return (
    <aside className="border-r border-primary p-4 overflow-y-auto bg-muted">
      <div className="text-xs uppercase tracking-widest text-primary">
        RESOURCE LIBRARY
      </div>
      <div className="flex flex-col gap-2">
        {RESOURCE_LIBRARY.map((t) => (
          <div
            key={t.typeId}
            draggable
            onDragStart={(e) => onPaletteDragStart(e, t.typeId)}
            className="border border-secondary border-l-4 p-3 cursor-grab bg-background hover:bg-card"
            style={{ borderLeftColor: t.color }}
          >
            <div className="text-primary font-medium">{t.name}</div>
            <div className="text-primary text-xs mt-1">
              {t.footprint.width}×{t.footprint.height} mm · {t.vendor}
            </div>
          </div>
        ))}
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
