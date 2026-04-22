import { useCallback } from "react";
import type { ViewTransform, Point } from "../lib/types";

export function useSceneTransforms(view: ViewTransform) {
  const worldToScreen = useCallback(
    (wx: number, wy: number): Point => ({
      x: wx * view.scale + view.offsetX,
      y: wy * view.scale + view.offsetY,
    }),
    [view],
  );

  const screenToWorld = useCallback(
    (sx: number, sy: number): Point => ({
      x: (sx - view.offsetX) / view.scale,
      y: (sy - view.offsetY) / view.scale,
    }),
    [view],
  );

  return {
    worldToScreen,
    screenToWorld,
  };
}
