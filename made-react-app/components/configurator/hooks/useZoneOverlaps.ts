import { useMemo, useCallback } from "react";
import type {
  Scene,
  TypeById,
  PendingOverlap,
  Connection,
  Resource,
  OverlapRegion,
} from "../lib/types";
import {
  resourceBBox,
  bboxOverlap,
  getEffectiveZones,
  zoneToWorldPolygon,
  ensureCCW,
  clipPolygon,
} from "../lib/geometry";
import { ZONES_COMPATIBLE } from "../lib/resourceLibrary";

export function useZoneOverlaps(scene: Scene, typeById: TypeById) {
  // Station body overlaps (warning)
  const overlaps = useMemo(() => {
    const pairs: [string, string][] = [];
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
    const s = new Set<string>();
    overlaps.forEach(([a, b]) => {
      s.add(a);
      s.add(b);
    });
    return s;
  }, [overlaps]);

  // Zone overlap computation (filtered by compatibility)
  const computeZoneOverlaps = useCallback(
    (resA: Resource, resB: Resource): OverlapRegion[] => {
      const zonesA = getEffectiveZones(resA, typeById);
      const zonesB = getEffectiveZones(resB, typeById);
      const regions: OverlapRegion[] = [];
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

  const isConnectionValid = useCallback(
    (connection: Connection): boolean => {
      const resA = scene.resources.find(
        (r) => r.instanceId === connection.resourceAId,
      );
      const resB = scene.resources.find(
        (r) => r.instanceId === connection.resourceBId,
      );
      if (!resA || !resB) return false;
      return computeZoneOverlaps(resA, resB).some(
        (region) =>
          region.zoneAId === connection.zoneAId &&
          region.zoneBId === connection.zoneBId,
      );
    },
    [scene.resources, computeZoneOverlaps],
  );

  return {
    overlaps,
    overlapSet,
    computeZoneOverlaps,
    isConnectionValid,
  };
}
