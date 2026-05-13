export type ZoneType = "infeed" | "outfeed" | "inout";

export type Point = { x: number; y: number };

export type PolygonLocal = [number, number][];

export interface ConnectionZone {
  id: string;
  label: string;
  type: ZoneType;
  polygon: PolygonLocal;
}

export interface ResourceType {
  typeId: string;
  name: string;
  vendor: string;
  category: string;
  color: string;
  footprint: { width: number; height: number };
  geometry?: PolygonLocal;
  connectionZones: ConnectionZone[];
}

export interface CustomZone {
  id: string;
  label: string;
  type: ZoneType;
  polygon: PolygonLocal;
}

export interface Resource {
  instanceId: string;
  typeId: string;
  position: Point;
  rotation: number;
  customZones: CustomZone[];
  zoneOverrides?: Record<string, ZoneType>;
}

export interface Connection {
  id: string;
  resourceAId: string;
  resourceBId: string;
  zoneAId: string;
  zoneBId: string;
  zoneAType: ZoneType;
  zoneBType: ZoneType;
  worldPosition: Point;
  localPositionA: Point;
  localPositionB: Point;
}

export interface Scene {
  resources: Resource[];
  connections: Connection[];
}

export type TypeById = Record<string, ResourceType>;

export type EditorMode = "select" | "connect" | "draw-zone";

export type ViewTransform = {
  scale: number;
  offsetX: number;
  offsetY: number;
};

export type DragState =
  | {
      kind: "pan";
      startX: number;
      startY: number;
      origOffset: ViewTransform;
    }
  | {
      kind: "resource";
      instanceId: string;
      grabOffset: Point;
      moved: boolean;
    }
  | { kind: "draw-zone" }
  | {
      kind: "connection";
      connectionId: string;
      moved: boolean;
    };

export interface ZoneDraw {
  resourceId: string;
  startLocal: Point;
  currentLocal: Point;
  type: ZoneType;
}

export interface OverlapRegion {
  polygon: [number, number][];
  zoneAId: string;
  zoneBId: string;
  zoneAType: ZoneType;
  zoneBType: ZoneType;
  zoneALabel: string;
  zoneBLabel: string;
}

export interface PendingOverlap extends OverlapRegion {
  otherInstanceId: string;
}

export interface ProductionLineShell {
  id: string;
  idShort: string;
  lineConfigSubmodelId?: string;   // IRI of the existing LineConfiguration submodel on the shell
  serviceOfferedSubmodelId?: string; // IRI of the existing ServiceOffered submodel on the shell
}

export interface CapabilityEntry {
  capabilityType: string;
  resourceRef: string;
  capabilityRef: string;
}

