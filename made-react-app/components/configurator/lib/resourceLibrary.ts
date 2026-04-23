import type { ResourceType, ZoneType } from "./types";

export const RESOURCE_LIBRARY: ResourceType[] = [
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

export interface ZoneColorSpec {
  fill: string;
  stroke: string;
  strokeActive: string;
  label: string;
}

export const ZONE_COLORS: Record<ZoneType, ZoneColorSpec> = {
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

export const ZONES_COMPATIBLE = (a: ZoneType, b: ZoneType): boolean => {
  if (a === "inout" || b === "inout") return true;
  return (
    (a === "infeed" && b === "outfeed") || (a === "outfeed" && b === "infeed")
  );
};

export const MM_PER_GRID = 200;
