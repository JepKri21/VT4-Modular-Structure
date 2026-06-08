"use client";

import { Fragment, useEffect, useMemo, useState } from "react";

interface StationStock {
  resource_id: string;
  on_hand: number;
  updated_at: string;
}

interface InventoryRow {
  component_type_iri: string;
  name: string;
  category: string | null;
  kind: "RAW" | "INTERMEDIATE" | "FINISHED" | null;
  lead_time_days: number;
  reorder_strategy: "LOT_FOR_LOT" | "JIT";
  reorder_point: number;
  reorder_quantity: number;
  unit_cost: string;
  on_hand_total: number;
  by_station: StationStock[];
}

const STRATEGIES: InventoryRow["reorder_strategy"][] = ["JIT", "LOT_FOR_LOT"];
const STRATEGY_LABEL: Record<InventoryRow["reorder_strategy"], string> = {
  JIT: "JIT",
  LOT_FOR_LOT: "Lot-for-lot",
};

const KIND_LABEL: Record<NonNullable<InventoryRow["kind"]>, string> = {
  RAW: "Raw",
  INTERMEDIATE: "Intermediate",
  FINISHED: "Finished",
};

const POLL_MS = 5000;

export default function InventoryTab() {
  const [rows, setRows] = useState<InventoryRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [kindFilter, setKindFilter] = useState<"RAW" | "ALL">("RAW");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const refresh = async () => {
    try {
      const res = await fetch("/api/mrp/inventory", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setRows(data.rows ?? []);
      setError(null);
    } catch (err) {
      setError(String(err));
    }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((r) => {
      if (kindFilter === "RAW" && r.kind !== "RAW") return false;
      if (!q) return true;
      return [r.name, r.category ?? "", r.component_type_iri]
        .join(" ")
        .toLowerCase()
        .includes(q);
    });
  }, [rows, query, kindFilter]);

  const lowStockCount = useMemo(
    () =>
      rows.filter(
        (r) => r.kind === "RAW" && r.on_hand_total <= r.reorder_point,
      ).length,
    [rows],
  );

  const toggleExpand = (iri: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(iri)) next.delete(iri);
      else next.add(iri);
      return next;
    });

  const updateField = async (
    iri: string,
    key: keyof InventoryRow,
    value: unknown,
  ) => {
    setRows((prev) =>
      prev.map((r) =>
        r.component_type_iri === iri ? { ...r, [key]: value } : r,
      ),
    );
    const res = await fetch("/api/mrp/materials", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ component_type_iri: iri, [key]: value }),
    });
    if (!res.ok) {
      alert((await res.json().catch(() => ({}))).error ?? "update failed");
      refresh();
    }
  };

  return (
    <div className="space-y-4">
      {error && (
        <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
          {error}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="Search by material name, category, or IRI…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="px-3 py-1.5 rounded-md bg-muted text-sm focus:outline-none focus:ring-1 focus:ring-primary flex-1 min-w-72"
        />
        <select
          value={kindFilter}
          onChange={(e) =>
            setKindFilter(e.target.value as "RAW" | "ALL")
          }
          className="px-2 py-1.5 rounded-md bg-muted text-sm"
        >
          <option value="RAW">Raw only</option>
          <option value="ALL">All (incl. intermediates & finished)</option>
        </select>
        {lowStockCount > 0 && (
          <span className="text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-3 py-0.5">
            {lowStockCount} raw materials at/below reorder point
          </span>
        )}
        <span className="text-xs text-muted-foreground">
          {filtered.length} of {rows.length} shown
        </span>
      </div>

      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted">
            <tr className="border-b">
              <th className="text-left p-2 whitespace-nowrap">Material</th>
              <th className="text-left p-2 whitespace-nowrap">Kind</th>
              <th className="text-left p-2 whitespace-nowrap">Category</th>
              <th className="text-right p-2 whitespace-nowrap">On hand</th>
              <th className="text-left p-2 whitespace-nowrap">Strategy</th>
              <th className="text-right p-2 whitespace-nowrap">Reorder pt.</th>
              <th className="text-right p-2 whitespace-nowrap">Reorder qty.</th>
              <th className="text-right p-2 whitespace-nowrap">Lead (d)</th>
              <th className="text-right p-2 whitespace-nowrap">Unit cost</th>
              <th className="text-left p-2 whitespace-nowrap">Stations</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td
                  colSpan={10}
                  className="p-4 text-center text-muted-foreground"
                >
                  {rows.length === 0
                    ? "No materials yet. Start a station with InventoryLevel publishing and reload."
                    : "No materials match the filters."}
                </td>
              </tr>
            )}
            {filtered.map((r) => {
              const low =
                r.kind === "RAW" && r.on_hand_total <= r.reorder_point;
              const open = expanded.has(r.component_type_iri);
              return (
                <Fragment key={r.component_type_iri}>
                  <tr className={`border-b ${low ? "bg-amber-50" : ""}`}>
                    <td className="p-2">
                      <div className="font-medium">{r.name}</div>
                      <div
                        className="text-[10px] font-mono text-muted-foreground truncate max-w-md"
                        title={r.component_type_iri}
                      >
                        {r.component_type_iri}
                      </div>
                    </td>
                    <td className="p-2 whitespace-nowrap text-xs">
                      {r.kind ? KIND_LABEL[r.kind] : "—"}
                    </td>
                    <td className="p-2 whitespace-nowrap">
                      {r.category ?? "—"}
                    </td>
                    <td
                      className={`p-2 text-right font-semibold tabular-nums ${low ? "text-amber-700" : ""}`}
                    >
                      {r.on_hand_total}
                    </td>
                    <td className="p-2">
                      <select
                        value={r.reorder_strategy}
                        onChange={(e) =>
                          updateField(
                            r.component_type_iri,
                            "reorder_strategy",
                            e.target.value,
                          )
                        }
                        className="px-2 py-0.5 rounded border bg-background text-xs"
                      >
                        {STRATEGIES.map((s) => (
                          <option key={s} value={s}>
                            {STRATEGY_LABEL[s]}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="p-2 text-right">
                      <NumberCell
                        value={r.reorder_point}
                        onCommit={(v) =>
                          updateField(r.component_type_iri, "reorder_point", v)
                        }
                      />
                    </td>
                    <td className="p-2 text-right">
                      <NumberCell
                        value={r.reorder_quantity}
                        onCommit={(v) =>
                          updateField(
                            r.component_type_iri,
                            "reorder_quantity",
                            v,
                          )
                        }
                      />
                    </td>
                    <td className="p-2 text-right">
                      <NumberCell
                        value={r.lead_time_days}
                        onCommit={(v) =>
                          updateField(r.component_type_iri, "lead_time_days", v)
                        }
                      />
                    </td>
                    <td className="p-2 text-right">
                      <NumberCell
                        value={Number(r.unit_cost)}
                        step={0.01}
                        onCommit={(v) =>
                          updateField(r.component_type_iri, "unit_cost", v)
                        }
                      />
                    </td>
                    <td className="p-2">
                      {r.by_station.length === 0 ? (
                        <span className="text-xs text-muted-foreground">—</span>
                      ) : (
                        <button
                          onClick={() => toggleExpand(r.component_type_iri)}
                          className="text-xs text-primary hover:underline"
                        >
                          {r.by_station.length} station(s){" "}
                          <span>{open ? "▾" : "▸"}</span>
                        </button>
                      )}
                    </td>
                  </tr>
                  {open && (
                    <tr className="border-b bg-muted/40">
                      <td colSpan={10} className="p-2">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-muted-foreground">
                              <th className="text-left p-1">Station</th>
                              <th className="text-right p-1">On hand</th>
                              <th className="text-left p-1">Updated</th>
                            </tr>
                          </thead>
                          <tbody>
                            {r.by_station.map((s) => (
                              <tr key={s.resource_id}>
                                <td className="p-1 font-mono">
                                  {s.resource_id}
                                </td>
                                <td className="p-1 text-right">{s.on_hand}</td>
                                <td className="p-1 text-muted-foreground">
                                  {new Date(s.updated_at).toLocaleString()}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function NumberCell({
  value,
  step = 1,
  onCommit,
}: {
  value: number;
  step?: number;
  onCommit: (next: number) => void;
}) {
  const [local, setLocal] = useState<string>(String(value));
  useEffect(() => setLocal(String(value)), [value]);

  const commit = () => {
    const v = Number(local);
    if (Number.isFinite(v) && v !== value) onCommit(v);
    else setLocal(String(value));
  };

  return (
    <input
      type="number"
      step={step}
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") setLocal(String(value));
      }}
      className="px-1.5 py-0.5 rounded border bg-background text-xs w-20 text-right tabular-nums"
    />
  );
}
