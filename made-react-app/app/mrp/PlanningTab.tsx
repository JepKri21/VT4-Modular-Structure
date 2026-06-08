"use client";

import { useEffect, useMemo, useState } from "react";

// Planning tab: forecast (moving-average over completed orders), MPS
// (editable weekly targets), and the Run MRP button. The button POSTs
// to /api/mrp/run, which proposes POs; the user reviews them on the
// Purchase Orders tab.

interface ForecastByProduct {
  product_iri: string;
  product_name: string | null;
  history: Array<{ week_start: string; units: number }>;
  avg_weekly: number;
  forecast: Array<{ week_start: string; projected_units: number }>;
}

interface ForecastResp {
  lookback_weeks: number;
  horizon_weeks: number;
  by_product: ForecastByProduct[];
}

interface MpsRow {
  id: number;
  week_start: string;
  finished_product_type_iri: string;
  quantity_target: number;
  notes: string | null;
  product_name: string | null;
  product_kind: string | null;
}

interface MaterialOption {
  component_type_iri: string;
  name: string;
  kind: string | null;
}

interface BomFinishedProduct {
  parent_iri: string;       // type-only, what we send to the MPS row
  parent_full_iri: string;  // for display tooltip
  parent_name: string;
}

interface RunResp {
  success: boolean;
  mps_entries_considered: number;
  bom_edges_walked: number;
  materials_with_gross_requirement: number;
  proposed_pos_created: number;
}

const POLL_MS = 15_000;

function nextMonday(): string {
  const d = new Date();
  const day = d.getUTCDay() || 7;
  // ISO week starts Monday. Pick the upcoming one (if today is Mon, use today).
  if (day !== 1) d.setUTCDate(d.getUTCDate() + (8 - day));
  return d.toISOString().slice(0, 10);
}

export default function PlanningTab() {
  const [forecast, setForecast] = useState<ForecastResp | null>(null);
  const [lookback, setLookback] = useState(4);
  const [horizon, setHorizon] = useState(4);

  const [mps, setMps] = useState<MpsRow[]>([]);
  const [materials, setMaterials] = useState<MaterialOption[]>([]);
  const [finishedFromBom, setFinishedFromBom] = useState<BomFinishedProduct[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [newProduct, setNewProduct] = useState("");
  const [newWeek, setNewWeek] = useState(nextMonday());
  const [newQty, setNewQty] = useState(10);

  const [lastRun, setLastRun] = useState<RunResp | null>(null);
  const [running, setRunning] = useState(false);

  const refresh = async () => {
    try {
      const [f, m, mat, bom] = await Promise.all([
        fetch(
          `/api/mrp/forecast?lookback_weeks=${lookback}&horizon_weeks=${horizon}`,
          { cache: "no-store" },
        ),
        fetch("/api/mrp/mps", { cache: "no-store" }),
        fetch("/api/mrp/materials", { cache: "no-store" }),
        // BOM endpoint surfaces every preset-defined finished product
        // even before one has been physically built and stored.
        fetch("/api/mrp/bom", { cache: "no-store" }),
      ]);
      if (!f.ok || !m.ok || !mat.ok || !bom.ok) {
        throw new Error(
          `HTTP ${f.status}/${m.status}/${mat.status}/${bom.status}`,
        );
      }
      setForecast(await f.json());
      setMps((await m.json()).rows ?? []);
      setMaterials((await mat.json()).rows ?? []);
      const bomJson = await bom.json();
      const finished: BomFinishedProduct[] = (bomJson.entries ?? [])
        .filter(
          (e: { parent_kind?: string }) => e.parent_kind === "FINISHED",
        )
        .map((e: { parent_iri: string; parent_full_iri: string; parent_name: string }) => ({
          parent_iri: e.parent_iri,
          parent_full_iri: e.parent_full_iri,
          parent_name: e.parent_name,
        }));
      setFinishedFromBom(finished);
      setError(null);
    } catch (err) {
      setError(String(err));
    }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [lookback, horizon]);

  // Merge catalog FINISHED rows with preset-derived ones. Catalog entries
  // only appear after a phone has actually been built and stored, so the
  // preset list is what makes the dropdown useful from day one. Dedupe
  // by IRI; prefer catalog name when both sources have the same product.
  const finishedProducts = useMemo(() => {
    const byIri = new Map<string, MaterialOption>();
    for (const m of materials) {
      if (m.kind === "FINISHED") byIri.set(m.component_type_iri, m);
    }
    for (const b of finishedFromBom) {
      if (!byIri.has(b.parent_iri)) {
        byIri.set(b.parent_iri, {
          component_type_iri: b.parent_iri,
          name: b.parent_name,
          kind: "FINISHED",
        });
      }
    }
    return Array.from(byIri.values()).sort((a, b) =>
      a.name.localeCompare(b.name),
    );
  }, [materials, finishedFromBom]);

  const addMps = async () => {
    if (!newProduct || !newWeek || newQty < 0) {
      alert("Pick a product, a week, and a non-negative quantity.");
      return;
    }
    const res = await fetch("/api/mrp/mps", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        week_start: newWeek,
        finished_product_type_iri: newProduct,
        quantity_target: newQty,
      }),
    });
    if (!res.ok) {
      alert((await res.json().catch(() => ({}))).error ?? "add failed");
      return;
    }
    refresh();
  };

  const removeMps = async (id: number) => {
    if (!confirm("Remove this MPS entry?")) return;
    const res = await fetch(`/api/mrp/mps/${id}`, { method: "DELETE" });
    if (!res.ok) alert("delete failed");
    refresh();
  };

  const runMrp = async () => {
    if (
      !confirm(
        "Run MRP now? Proposed POs will be created against open requirements.",
      )
    )
      return;
    setRunning(true);
    try {
      const res = await fetch("/api/mrp/run", { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        alert(data.error ?? "MRP run failed");
        return;
      }
      setLastRun(data);
      refresh();
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      {error && (
        <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
          {error}
        </div>
      )}

      {/* Forecast */}
      <section className="space-y-3">
        <header className="flex flex-wrap items-baseline gap-3">
          <h2 className="text-base font-semibold">Forecast</h2>
          <label className="text-xs text-muted-foreground flex items-center gap-1">
            Lookback (weeks)
            <input
              type="number"
              min={1}
              max={52}
              value={lookback}
              onChange={(e) =>
                setLookback(
                  Math.max(1, Math.min(52, Number(e.target.value) || 4)),
                )
              }
              className="px-1 py-0.5 rounded border bg-background w-16 text-xs"
            />
          </label>
          <label className="text-xs text-muted-foreground flex items-center gap-1">
            Horizon (weeks)
            <input
              type="number"
              min={0}
              max={26}
              value={horizon}
              onChange={(e) =>
                setHorizon(
                  Math.max(0, Math.min(26, Number(e.target.value) || 0)),
                )
              }
              className="px-1 py-0.5 rounded border bg-background w-16 text-xs"
            />
          </label>
        </header>

        {forecast === null || forecast.by_product.length === 0 ? (
          <div className="rounded-md border p-4 text-sm text-muted-foreground">
            No completed orders in the lookback window — forecast unavailable.
            Run orders to produce history.
          </div>
        ) : (
          <div className="space-y-3">
            {forecast.by_product.map((p) => (
              <div key={p.product_iri} className="rounded-md border p-3">
                <div className="flex items-baseline gap-2 mb-2">
                  <span className="font-medium">
                    {p.product_name ?? p.product_iri}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    avg {p.avg_weekly} units/week
                  </span>
                </div>
                <div className="text-xs grid grid-cols-2 md:grid-cols-4 gap-2">
                  <div>
                    <div className="text-[10px] uppercase text-muted-foreground mb-1">
                      History
                    </div>
                    <ul className="space-y-0.5">
                      {p.history.map((h) => (
                        <li
                          key={h.week_start}
                          className="flex justify-between gap-2"
                        >
                          <span className="text-muted-foreground">
                            {h.week_start}
                          </span>
                          <span className="tabular-nums">{h.units}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="md:col-span-3">
                    <div className="text-[10px] uppercase text-muted-foreground mb-1">
                      Forecast
                    </div>
                    <ul className="grid grid-cols-2 md:grid-cols-4 gap-1">
                      {p.forecast.map((f) => (
                        <li
                          key={f.week_start}
                          className="flex justify-between gap-2 bg-muted/40 px-2 py-0.5 rounded"
                        >
                          <span className="text-muted-foreground">
                            {f.week_start}
                          </span>
                          <span className="tabular-nums">
                            {f.projected_units}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* MPS */}
      <section className="space-y-3">
        <header className="flex flex-wrap items-baseline gap-3">
          <h2 className="text-base font-semibold">
            Master Production Schedule
          </h2>
          <span className="text-xs text-muted-foreground">
            Weekly targets per finished product
          </span>
        </header>

        <div className="rounded-md border p-3 bg-muted/30 space-y-2">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-muted-foreground flex flex-col gap-1 flex-1 min-w-64">
              Product
              <select
                value={newProduct}
                onChange={(e) => setNewProduct(e.target.value)}
                className="px-2 py-1.5 rounded border bg-background text-sm"
              >
                <option value="">— pick —</option>
                {finishedProducts.map((m) => (
                  <option
                    key={m.component_type_iri}
                    value={m.component_type_iri}
                  >
                    {m.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-muted-foreground flex flex-col gap-1">
              Week start (Mon)
              <input
                type="date"
                value={newWeek}
                onChange={(e) => setNewWeek(e.target.value)}
                className="px-2 py-1.5 rounded border bg-background text-sm"
              />
            </label>
            <label className="text-xs text-muted-foreground flex flex-col gap-1">
              Quantity
              <input
                type="number"
                min={0}
                value={newQty}
                onChange={(e) =>
                  setNewQty(Math.max(0, Number(e.target.value) || 0))
                }
                className="px-2 py-1.5 rounded border bg-background text-sm w-24 tabular-nums"
              />
            </label>
            <button
              type="button"
              onClick={addMps}
              className="px-4 py-1.5 rounded-md bg-primary text-background text-sm font-medium hover:opacity-90"
            >
              Add / update
            </button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Same (week, product) replaces the existing target.
          </p>
        </div>

        {mps.length === 0 ? (
          <div className="rounded-md border p-4 text-sm text-muted-foreground">
            No MPS entries yet. Add weekly production targets.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted">
                <tr className="border-b">
                  <th className="text-left p-2 whitespace-nowrap">Week</th>
                  <th className="text-left p-2 whitespace-nowrap">Product</th>
                  <th className="text-right p-2 whitespace-nowrap">Target</th>
                  <th className="text-left p-2 w-12"></th>
                </tr>
              </thead>
              <tbody>
                {mps.map((row) => (
                  <tr key={row.id} className="border-b">
                    <td className="p-2 whitespace-nowrap">
                      {row.week_start.slice(0, 10)}
                    </td>
                    <td className="p-2">
                      <div className="font-medium">
                        {row.product_name ?? row.finished_product_type_iri}
                      </div>
                      <div className="text-[10px] font-mono text-muted-foreground truncate">
                        {row.finished_product_type_iri}
                      </div>
                    </td>
                    <td className="p-2 text-right tabular-nums font-semibold">
                      {row.quantity_target}
                    </td>
                    <td className="p-2 text-right">
                      <button
                        onClick={() => removeMps(row.id)}
                        className="text-red-600 hover:underline text-xs"
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* MRP run */}
      <section className="rounded-md border p-3 space-y-2 bg-muted/30">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-base font-semibold">Run MRP</h2>
          <button
            type="button"
            onClick={runMrp}
            disabled={running}
            className="px-4 py-1.5 rounded-md bg-primary text-background text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            {running ? "Running…" : "Run now"}
          </button>
          {lastRun && (
            <span className="text-xs text-muted-foreground">
              Last run: {lastRun.mps_entries_considered} MPS row(s) ·{" "}
              {lastRun.bom_edges_walked} BOM edge(s) walked ·{" "}
              {lastRun.materials_with_gross_requirement} material(s) needed
              · {lastRun.proposed_pos_created} PO(s) proposed
            </span>
          )}
        </div>
        <p className="text-[11px] text-muted-foreground">
          Explodes MPS targets through the BOM, subtracts on-hand and open
          POs, and proposes new POs per material strategy. Review under
          Purchase Orders.
        </p>
      </section>
    </div>
  );
}
