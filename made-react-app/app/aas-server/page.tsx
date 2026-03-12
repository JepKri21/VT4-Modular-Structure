"use client";

import { useEffect, useState } from "react";

type ShellResult = { id: string; type: string; status: number; ok: boolean };

export default function AasServerPage() {
  const [shells, setShells] = useState<{ id: string }[]>([]);
  const [loadingShells, setLoadingShells] = useState(false);
  const [shellError, setShellError] = useState<string | null>(null);

  const [clearing, setClearing] = useState(false);
  const [clearResult, setClearResult] = useState<{
    deleted: number;
    failed: number;
    results: ShellResult[];
  } | null>(null);

  const fetchShells = async () => {
    setLoadingShells(true);
    setShellError(null);
    try {
      const res = await fetch("/api/aas/shells");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Failed to fetch shells");
      setShells(data.result ?? []);
    } catch (e) {
      setShellError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingShells(false);
    }
  };

  useEffect(() => {
    fetchShells();
  }, []);

  const clearAllShells = async () => {
    if (
      !confirm(
        `Delete all ${shells.length} shell(s) and their submodels from the AAS server?\nThis cannot be undone.`
      )
    )
      return;

    setClearing(true);
    setClearResult(null);
    try {
      const res = await fetch("/api/aas/shells", { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Clear failed");
      setClearResult(data);
      setShells([]);
    } catch (e) {
      setShellError(e instanceof Error ? e.message : String(e));
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-10">
      <h1 className="text-2xl font-bold">AAS Server</h1>

      {/* ── Shells panel ─────────────────────────────────────── */}
      <section className="border border-border rounded-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">
            Shells on server
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              ({shells.length})
            </span>
          </h2>

          <div className="flex gap-3">
            <button
              onClick={fetchShells}
              disabled={loadingShells}
              className="px-4 py-2 rounded border border-border text-sm hover:bg-muted disabled:opacity-40"
            >
              {loadingShells ? "Loading…" : "Refresh"}
            </button>

            <button
              onClick={clearAllShells}
              disabled={clearing || shells.length === 0}
              className="px-4 py-2 rounded bg-destructive text-destructive-foreground text-sm font-medium hover:bg-destructive/90 disabled:opacity-40"
            >
              {clearing ? "Clearing…" : "Clear All Shells"}
            </button>
          </div>
        </div>

        {shellError && (
          <p className="text-destructive text-sm">{shellError}</p>
        )}

        {/* Result summary after a clear */}
        {clearResult && (
          <div className="rounded-md border border-border p-3 text-sm space-y-1">
            <p className="font-medium">
              Clear complete —{" "}
              <span className="text-green-400">{clearResult.deleted} deleted</span>
              {clearResult.failed > 0 && (
                <span className="text-destructive ml-2">
                  {clearResult.failed} failed
                </span>
              )}
            </p>
            {clearResult.results
              .filter((r) => !r.ok)
              .map((r) => (
                <p key={`${r.type}-${r.id}`} className="text-destructive text-xs truncate">
                  FAIL ({r.status}) → [{r.type}] {r.id}
                </p>
              ))}
          </div>
        )}

        {/* Shell list */}
        {shells.length === 0 && !loadingShells ? (
          <p className="text-muted-foreground text-sm">No shells on server.</p>
        ) : (
          <ul className="divide-y divide-border max-h-96 overflow-y-auto text-sm">
            {shells.map((s) => (
              <li key={s.id} className="py-2 truncate font-mono text-xs text-muted-foreground">
                {s.id}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
