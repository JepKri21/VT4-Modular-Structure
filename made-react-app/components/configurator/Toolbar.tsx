import React from "react";
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
} from "lucide-react";
import type { EditorMode, ZoneType } from "./lib/types";

interface ToolbarProps {
  mode: EditorMode;
  setMode: (mode: EditorMode) => void;
  canUndo: boolean;
  canRedo: boolean;
  undo: () => void;
  redo: () => void;
  snapToGrid: boolean;
  setSnapToGrid: (snap: boolean) => void;
  alwaysShowZones: boolean;
  setAlwaysShowZones: (show: boolean) => void;
  overlaps: [string, string][];
  newZoneType: ZoneType;
  setNewZoneType: (type: ZoneType) => void;
  handleExport: () => void;
  invalidConnectionCount: number;
}

function ToolbarGroup({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex bg-gray-800 border border-gray-600">
      {children}
    </div>
  );
}

function ToolbarBtn({
  children,
  active,
  disabled,
  onClick,
  title,
  accent,
}: {
  children: React.ReactNode;
  active?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  title?: string;
  accent?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`px-3 py-2 text-xs border-r border-gray-600 ${
        accent
          ? "bg-yellow-500 text-gray-900"
          : active
            ? "bg-gray-700 text-gray-100"
            : disabled
              ? "text-gray-500 cursor-not-allowed"
              : "text-gray-400 hover:text-gray-100"
      }`}
    >
      {children}
    </button>
  );
}

export function Toolbar({
  mode,
  setMode,
  canUndo,
  canRedo,
  undo,
  redo,
  snapToGrid,
  setSnapToGrid,
  alwaysShowZones,
  setAlwaysShowZones,
  overlaps,
  newZoneType,
  setNewZoneType,
  handleExport,
  invalidConnectionCount,
}: ToolbarProps) {
  return (
    <div className="absolute top-3 left-3 right-3 z-10 flex gap-2 items-center">
      <ToolbarGroup>
        <ToolbarBtn
          active={mode === "select"}
          onClick={() => {
            setMode("select");
            // setConnectFirst(null);
            // setZoneDraw(null);
          }}
          title="Select / move"
        >
          <Move size={13} />
        </ToolbarBtn>
        <ToolbarBtn
          active={mode === "connect"}
          onClick={() => {
            setMode("connect");
            // setConnectFirst(null);
            // setZoneDraw(null);
          }}
          title="Connect two resources"
        >
          <Link2 size={13} />
        </ToolbarBtn>
        <ToolbarBtn
          active={mode === "draw-zone"}
          onClick={() => {
            setMode("draw-zone");
            // setConnectFirst(null);
          }}
          title="Draw a new zone on selected resource"
        >
          <Pencil size={13} />
        </ToolbarBtn>
      </ToolbarGroup>

      {mode === "draw-zone" && (
        <div className="flex bg-gray-800 border border-gray-600">
          {Object.entries({
            infeed: { fill: "#22c55e22", stroke: "#22c55e", label: "Infeed" },
            outfeed: { fill: "#3b82f622", stroke: "#3b82f6", label: "Outfeed" },
            inout: { fill: "#a855f722", stroke: "#a855f7", label: "In/Out" },
          }).map(([key, col]) => (
            <button
              key={key}
              onClick={() => setNewZoneType(key as ZoneType)}
              title={col.label}
              className={`px-3 py-2 text-xs border-r border-gray-600 last:border-r-0 ${
                newZoneType === key ? "text-gray-100" : "text-gray-400"
              }`}
            >
              <div className="flex items-center gap-2">
                <div
                  className="w-3 h-3 border border-gray-600"
                  style={{
                    backgroundColor:
                      newZoneType === key ? col.fill : "transparent",
                  }}
                />
                {col.label}
              </div>
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
          onClick={() => setSnapToGrid(!snapToGrid)}
          title="Snap to grid"
        >
          <Grid3x3 size={13} />
        </ToolbarBtn>
        <ToolbarBtn
          active={alwaysShowZones}
          onClick={() => setAlwaysShowZones(!alwaysShowZones)}
          title="Always show zones"
        >
          {alwaysShowZones ? <Eye size={13} /> : <EyeOff size={13} />}
        </ToolbarBtn>
      </ToolbarGroup>
      <div className="flex-1" />
      {overlaps.length > 0 && (
        <div className="flex items-center gap-2 bg-red-500/10 text-red-500 px-3 py-2 border border-red-500/40 text-xs">
          <AlertTriangle size={13} />
          {overlaps.length} station body overlap{overlaps.length > 1 ? "s" : ""}
        </div>
      )}
      {invalidConnectionCount > 0 && (
        <div className="flex items-center gap-2 bg-yellow-500/10 text-yellow-500 px-3 py-2 border border-yellow-500/40 text-xs">
          <AlertTriangle size={13} />
          {invalidConnectionCount} invalid connection
          {invalidConnectionCount > 1 ? "s" : ""}
        </div>
      )}
      <ToolbarBtn onClick={handleExport} title="Export AAS JSON" accent>
        <Download size={13} />
        <span className="ml-2">Export</span>
      </ToolbarBtn>
    </div>
  );
}
