"use client";

// PhoneConfigurator — composites layered PNGs of the AAU Mobile Phone onto
// a <canvas> based on the current configuration. Layer order (bottom up):
//   1. /ProductCardImages/BC{color}.png   — bottom cover
//   2. /ProductCardImages/PCBF{n}.png     — PCB with n fuses (1/2/3)
//   3. /ProductCardImages/TC{color}.png   — top cover
//
// Images are cached in a module-level map so swapping configuration
// reuses already-decoded HTMLImageElements and avoids flicker.

import { useEffect, useRef } from "react";

const CANVAS_SIZE = 800;
const BASE = "/ProductCardImages";

const COLORS = ["Black", "White", "Blue", "Green", "Red", "Gray"] as const;
const FUSES = [1, 2, 3] as const;

const imageCache = new Map<string, Promise<HTMLImageElement>>();

function loadImage(src: string): Promise<HTMLImageElement> {
  let p = imageCache.get(src);
  if (!p) {
    p = new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error(`Failed to load ${src}`));
      img.src = src;
    });
    imageCache.set(src, p);
  }
  return p;
}

// Warm the cache once with every variant so the first configuration
// swap on a freshly-mounted configurator does not show a flash of an
// empty canvas.
let warmed = false;
function warmCache() {
  if (warmed) return;
  warmed = true;
  for (const c of COLORS) {
    void loadImage(`${BASE}/BC${c}.png`);
    void loadImage(`${BASE}/TC${c}.png`);
  }
  for (const n of FUSES) {
    void loadImage(`${BASE}/PCBF${n}.png`);
  }
}

interface Props {
  topColor: string;
  bottomColor: string;
  fuseCount: number;
  className?: string;
}

export default function PhoneConfigurator({
  topColor,
  bottomColor,
  fuseCount,
  className,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    warmCache();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let cancelled = false;
    const srcs = [
      `${BASE}/BC${bottomColor}.png`,
      `${BASE}/PCBF${fuseCount}.png`,
      `${BASE}/TC${topColor}.png`,
    ];

    Promise.all(srcs.map(loadImage))
      .then((images) => {
        if (cancelled) return;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        for (const img of images) {
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        // Surface the missing-asset case to the dev console rather than
        // silently leaving a blank canvas.
        console.warn("[PhoneConfigurator]", err);
      });

    return () => {
      cancelled = true;
    };
  }, [topColor, bottomColor, fuseCount]);

  return (
    <canvas
      ref={canvasRef}
      width={CANVAS_SIZE}
      height={CANVAS_SIZE}
      className={className}
    />
  );
}
