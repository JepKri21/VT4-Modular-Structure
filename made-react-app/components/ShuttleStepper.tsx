"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Minus, Plus, Loader2 } from "lucide-react";

interface ShuttleStepperProps {
  shellId: string;
  /** Controlled count. If omitted, the stepper fetches its own count. */
  shuttleCount?: number;
  serverUrl?: string;
  /** Called after a successful add/retire so the parent can refetch. */
  onChanged?: () => void;
}

// Shared +/- control for the number of transport shuttles on a resource.
// Used on both the resource-control card and the line-configurator inspector.
// `add` writes the AAS and pings ReloadConfig (live pickup); `retire` asks the
// Line Controller to drain a shuttle cargo-safely before it leaves.
export function ShuttleStepper({
  shellId,
  shuttleCount,
  serverUrl,
  onChanged,
}: ShuttleStepperProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Internal count: mirrors a controlled prop when given, otherwise self-fetched.
  const [count, setCount] = useState<number | null>(shuttleCount ?? null);

  const refreshCount = useCallback(async () => {
    try {
      const qs = new URLSearchParams({ shellId });
      if (serverUrl) qs.set("serverUrl", serverUrl);
      const res = await fetch(`/api/resource-control/shuttles?${qs.toString()}`);
      if (res.ok) {
        const data = (await res.json()) as { shuttleCount?: number };
        if (typeof data.shuttleCount === "number") setCount(data.shuttleCount);
      }
    } catch {
      /* leave the last known count */
    }
  }, [shellId, serverUrl]);

  // Controlled mode: sync to the prop. Uncontrolled: fetch once on mount.
  useEffect(() => {
    if (shuttleCount !== undefined) setCount(shuttleCount);
    else refreshCount();
  }, [shuttleCount, refreshCount]);

  async function send(action: "add" | "retire") {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/resource-control/shuttles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shellId, action, serverUrl }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { error?: string };
        setError(data.error ?? `Request failed (${res.status})`);
      } else {
        await refreshCount();
        onChanged?.();
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-1.5" title="Number of transport shuttles">
      <span className="text-xs text-muted-foreground">Shuttles</span>
      <Button
        size="sm"
        variant="ghost"
        className="h-7 w-7 p-0"
        disabled={busy || (count ?? 0) <= 0}
        onClick={() => send("retire")}
        title="Retire a shuttle (drained cargo-safely before it leaves)"
      >
        <Minus className="w-3.5 h-3.5" />
      </Button>
      <span className="text-sm font-mono w-5 text-center tabular-nums">
        {busy ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin inline" />
        ) : (
          count ?? "…"
        )}
      </span>
      <Button
        size="sm"
        variant="ghost"
        className="h-7 w-7 p-0"
        disabled={busy}
        onClick={() => send("add")}
        title="Add a shuttle"
      >
        <Plus className="w-3.5 h-3.5" />
      </Button>
      {error && <span className="text-xs text-red-500 ml-1">{error}</span>}
    </div>
  );
}
