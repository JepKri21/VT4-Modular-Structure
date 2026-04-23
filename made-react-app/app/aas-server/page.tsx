"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Server,
  Trash2,
  Unplug,
} from "lucide-react";

/* ──────────────────────────────── types ── */

type ShellRef = { keys: { value: string }[] };
type AasShell = {
  id: string;
  idShort?: string;
  assetInformation?: { globalAssetId?: string };
  submodels?: ShellRef[];
};

type DeleteResult = { id: string; type: string; status: number; ok: boolean };

type DeleteSummary = { deleted: number; failed: number; results: DeleteResult[] };

/* ──────────────────────────────── helpers ── */

function cls(...parts: (string | false | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

function inputClass() {
  return "w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary";
}

/* ──────────────────────────────── submodel detail row ── */

function SubmodelList({ shell }: { shell: AasShell }) {
  const [open, setOpen] = useState(false);
  const refs = shell.submodels ?? [];
  if (refs.length === 0) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-xs text-primary hover:underline"
      >
        {refs.length} submodel{refs.length !== 1 ? "s" : ""}
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      {open && (
        <ul className="mt-1 space-y-0.5 pl-2 border-l border-border">
          {refs.map((r, i) => (
            <li key={i} className="text-[11px] font-mono text-muted-foreground truncate max-w-xs">
              {r.keys?.[0]?.value ?? "—"}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ──────────────────────────────── page ── */

export default function AasServerPage() {
  const [serverUrl, setServerUrl] = useState("http://localhost:8081");
  const [draftUrl, setDraftUrl] = useState("http://localhost:8081");

  const [shells, setShells] = useState<AasShell[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  const [selected, setSelected] = useState<Set<string>>(new Set());

  type OpState = "idle" | "running" | "done" | "error";
  const [deleteState, setDeleteState] = useState<OpState>("idle");
  const [deleteSummary, setDeleteSummary] = useState<DeleteSummary | null>(null);

  const fetchShells = useCallback(async (url: string) => {
    setLoading(true);
    setError(null);
    setDeleteSummary(null);
    try {
      const res = await fetch(`/api/aas/shells?server=${encodeURIComponent(url)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `Server returned ${res.status}`);
      setShells(data.result ?? []);
      setConnected(true);
      setSelected(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setConnected(false);
      setShells([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchShells(serverUrl);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connect = () => {
    const url = draftUrl.trim();
    setServerUrl(url);
    fetchShells(url);
  };

  /* ── selection helpers ── */

  const allSelected = shells.length > 0 && selected.size === shells.length;
  const someSelected = selected.size > 0 && !allSelected;

  const toggleAll = () => {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(shells.map((s) => s.id)));
    }
  };

  const toggleOne = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  /* ── delete helpers ── */

  const doDelete = async (ids?: string[]) => {
    setDeleteState("running");
    setDeleteSummary(null);
    try {
      const res = await fetch("/api/aas/shells", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ server: serverUrl, ids }),
      });
      const data: DeleteSummary = await res.json();
      setDeleteSummary(data);
      setDeleteState(data.failed === 0 ? "done" : "error");
      // Remove successfully deleted shells from local list
      const deletedIds = new Set(
        data.results.filter((r) => r.ok && r.type === "shell").map((r) => r.id)
      );
      setShells((prev) => prev.filter((s) => !deletedIds.has(s.id)));
      setSelected((prev) => {
        const next = new Set(prev);
        deletedIds.forEach((id) => next.delete(id));
        return next;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setDeleteState("error");
    }
  };

  const deleteSelected = () => {
    if (selected.size === 0) return;
    doDelete([...selected]);
  };

  const deleteAll = () => {
    if (shells.length === 0) return;
    if (!confirm(`Delete all ${shells.length} shell(s) and their submodels?\nThis cannot be undone.`)) return;
    doDelete();
  };

  const deleteOne = (id: string) => {
    if (!confirm(`Delete this shell and its submodels?\n${id}`)) return;
    doDelete([id]);
  };

  /* ── render ── */

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-5xl mx-auto flex flex-col gap-6">

        {/* ── header ── */}
        <div className="flex items-center gap-3">
          <Server className="w-6 h-6 text-primary" />
          <h1 className="text-2xl font-bold">AAS Server Manager</h1>
          {connected && (
            <span className="flex items-center gap-1 text-xs text-primary bg-primary/10 rounded-full px-2 py-0.5">
              <Check className="w-3 h-3" /> Connected
            </span>
          )}
        </div>

        {/* ── server URL input ── */}
        <div className="rounded-xl border border-border bg-card p-5 flex flex-col gap-3">
          <h2 className="font-semibold text-sm flex items-center gap-2">
            <Unplug className="w-4 h-4 text-primary" />
            Server Connection
          </h2>
          <div className="flex gap-2">
            <input
              type="text"
              className={inputClass()}
              value={draftUrl}
              onChange={(e) => setDraftUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && connect()}
              placeholder="http://localhost:8081"
            />
            <button
              type="button"
              onClick={connect}
              disabled={loading}
              className="flex items-center gap-2 rounded-lg bg-primary text-primary-foreground px-4 py-2 text-sm font-semibold disabled:opacity-40 hover:opacity-90 shrink-0"
            >
              {loading ? (
                <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Connecting…</>
              ) : (
                "Connect"
              )}
            </button>
            <button
              type="button"
              onClick={() => fetchShells(serverUrl)}
              disabled={loading || !connected}
              className="flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm hover:bg-muted disabled:opacity-40 shrink-0"
            >
              <RefreshCw className={cls("w-3.5 h-3.5", loading && "animate-spin")} />
              Refresh
            </button>
          </div>
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              {error}
            </div>
          )}
        </div>

        {/* ── action bar ── */}
        {connected && (
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-sm text-muted-foreground flex-1">
              {shells.length} shell{shells.length !== 1 ? "s" : ""} on server
              {selected.size > 0 && ` · ${selected.size} selected`}
            </span>

            {selected.size > 0 && (
              <button
                type="button"
                onClick={deleteSelected}
                disabled={deleteState === "running"}
                className="flex items-center gap-2 rounded-lg bg-destructive text-destructive-foreground px-4 py-2 text-sm font-semibold disabled:opacity-40 hover:opacity-90"
              >
                {deleteState === "running" ? (
                  <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Deleting…</>
                ) : (
                  <><Trash2 className="w-3.5 h-3.5" /> Delete Selected ({selected.size})</>
                )}
              </button>
            )}

            <button
              type="button"
              onClick={deleteAll}
              disabled={deleteState === "running" || shells.length === 0}
              className="flex items-center gap-2 rounded-lg border border-destructive text-destructive px-4 py-2 text-sm font-semibold disabled:opacity-40 hover:bg-destructive hover:text-destructive-foreground transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" /> Delete All
            </button>
          </div>
        )}

        {/* ── delete result summary ── */}
        {deleteSummary && (
          <div className={cls(
            "rounded-xl border p-4 text-sm flex flex-col gap-2",
            deleteSummary.failed === 0
              ? "border-primary/30 bg-primary/5 text-primary"
              : "border-destructive/40 bg-destructive/10 text-destructive"
          )}>
            <p className="font-semibold">
              {deleteSummary.failed === 0
                ? `Deleted ${deleteSummary.deleted} item${deleteSummary.deleted !== 1 ? "s" : ""} successfully.`
                : `${deleteSummary.deleted} deleted · ${deleteSummary.failed} failed`}
            </p>
            {deleteSummary.results.filter((r) => !r.ok).map((r, i) => (
              <p key={i} className="text-xs font-mono truncate">
                FAIL ({r.status}) [{r.type}] {r.id}
              </p>
            ))}
          </div>
        )}

        {/* ── shell table ── */}
        {connected && (
          <div className="rounded-xl border border-border overflow-hidden">
            {shells.length === 0 && !loading ? (
              <div className="p-8 text-center text-sm text-muted-foreground">
                No shells found on this server.
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-muted border-b border-border">
                  <tr>
                    <th className="w-10 px-4 py-3 text-left">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        ref={(el) => { if (el) el.indeterminate = someSelected; }}
                        onChange={toggleAll}
                        className="w-4 h-4 accent-primary cursor-pointer"
                      />
                    </th>
                    <th className="px-4 py-3 text-left font-semibold text-xs uppercase tracking-wide text-muted-foreground">
                      ID Short
                    </th>
                    <th className="px-4 py-3 text-left font-semibold text-xs uppercase tracking-wide text-muted-foreground hidden md:table-cell">
                      Shell ID
                    </th>
                    <th className="px-4 py-3 text-left font-semibold text-xs uppercase tracking-wide text-muted-foreground hidden lg:table-cell">
                      Asset ID
                    </th>
                    <th className="px-4 py-3 text-left font-semibold text-xs uppercase tracking-wide text-muted-foreground">
                      Submodels
                    </th>
                    <th className="w-20 px-4 py-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {shells.map((shell) => {
                    const isSelected = selected.has(shell.id);
                    return (
                      <tr
                        key={shell.id}
                        className={cls(
                          "transition-colors",
                          isSelected ? "bg-primary/5" : "hover:bg-muted/50"
                        )}
                      >
                        <td className="px-4 py-3">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleOne(shell.id)}
                            className="w-4 h-4 accent-primary cursor-pointer"
                          />
                        </td>
                        <td className="px-4 py-3 font-medium">
                          {shell.idShort ?? <span className="text-muted-foreground italic">—</span>}
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground truncate max-w-[260px] hidden md:table-cell">
                          {shell.id}
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground truncate max-w-[200px] hidden lg:table-cell">
                          {shell.assetInformation?.globalAssetId ?? "—"}
                        </td>
                        <td className="px-4 py-3">
                          <SubmodelList shell={shell} />
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            type="button"
                            onClick={() => deleteOne(shell.id)}
                            disabled={deleteState === "running"}
                            className="flex items-center gap-1 rounded-md border border-destructive/40 text-destructive px-2.5 py-1 text-xs hover:bg-destructive hover:text-destructive-foreground transition-colors disabled:opacity-40"
                          >
                            <Trash2 className="w-3 h-3" /> Delete
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
