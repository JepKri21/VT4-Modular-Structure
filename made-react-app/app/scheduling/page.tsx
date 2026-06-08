"use client";

import { useEffect, useMemo, useState } from "react";

// MES queue dashboard.
// Polls /api/mes/orders every 3 s and /api/mes/stats every 30 s.
// Features:
//   - five summary cards
//   - search box (resource_id, product, order_id, batch_id, status)
//   - "Show completed/cancelled" toggle (off by default to keep the UI
//     usable past a few hundred orders)
//   - priority editor on PENDING rows
//   - estimated delivery column (avg lead time × queue position / capacity)
//   - batch coordinates (e.g. "3/5")
//   - Reset on RELEASED, Retry on ABORTED, Cancel on PENDING

interface MesOrder {
  id: number;
  order_id: string;
  line_id: string | null;
  product_ref: string | null;
  priority: number;
  status: "PENDING" | "RELEASED" | "COMPLETED" | "ABORTED" | "CANCELLED";
  issued_at: string;
  released_at: string | null;
  completed_at: string | null;
  batch_id: string | null;
  batch_index: number;
  batch_total: number;
  attempt_count: number;
  next_attempt_at: string | null;
}

interface Summary {
  pending: number;
  released: number;
  completed: number;
  aborted: number;
  cancelled: number;
}

interface Stats {
  avg_lead_ms: number | null;
  sample_size: number;
  max_concurrent: number;
}

const POLL_ORDERS_MS = 3000;
const POLL_STATS_MS = 30_000;

const STATUS_LABEL: Record<MesOrder["status"], string> = {
  PENDING: "Pending",
  RELEASED: "In flight",
  COMPLETED: "Completed",
  ABORTED: "Aborted",
  CANCELLED: "Cancelled",
};

const STATUS_TINT: Record<MesOrder["status"], string> = {
  PENDING: "text-amber-700 bg-amber-50 border-amber-200",
  RELEASED: "text-blue-700 bg-blue-50 border-blue-200",
  COMPLETED: "text-green-700 bg-green-50 border-green-200",
  ABORTED: "text-red-700 bg-red-50 border-red-200",
  CANCELLED: "text-muted-foreground bg-muted border-border",
};

const TERMINAL: MesOrder["status"][] = ["COMPLETED", "CANCELLED"];

function fmtDuration(ms: number | null): string {
  if (ms == null || !Number.isFinite(ms)) return "—";
  if (ms < 60_000) return `${(ms / 1000).toFixed(0)} s`;
  if (ms < 3_600_000) return `${(ms / 60_000).toFixed(1)} min`;
  return `${(ms / 3_600_000).toFixed(1)} h`;
}

export default function SchedulingPage() {
  const [orders, setOrders] = useState<MesOrder[]>([]);
  const [summary, setSummary] = useState<Summary>({
    pending: 0,
    released: 0,
    completed: 0,
    aborted: 0,
    cancelled: 0,
  });
  const [stats, setStats] = useState<Stats>({
    avg_lead_ms: null,
    sample_size: 0,
    max_concurrent: 2,
  });
  const [error, setError] = useState<string | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);
  const [query, setQuery] = useState("");

  const refresh = async () => {
    try {
      const res = await fetch("/api/mes/orders", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setOrders(data.orders ?? []);
      setSummary(data.summary ?? summary);
      setError(null);
    } catch (err) {
      setError(String(err));
    }
  };

  const refreshStats = async () => {
    try {
      const res = await fetch("/api/mes/stats", { cache: "no-store" });
      if (!res.ok) return;
      setStats(await res.json());
    } catch {
      /* leave previous */
    }
  };

  useEffect(() => {
    refresh();
    refreshStats();
    const a = setInterval(refresh, POLL_ORDERS_MS);
    const b = setInterval(refreshStats, POLL_STATS_MS);
    return () => {
      clearInterval(a);
      clearInterval(b);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Mutations
  const cancelOrder = async (orderId: string) => {
    if (!confirm(`Cancel pending order ${orderId}?`)) return;
    const res = await fetch(`/api/mes/orders/${encodeURIComponent(orderId)}`, {
      method: "DELETE",
    });
    if (!res.ok) alert((await res.json().catch(() => ({}))).error ?? "cancel failed");
    refresh();
  };

  const resetOrder = async (orderId: string) => {
    const res = await fetch(`/api/mes/orders/${encodeURIComponent(orderId)}/reset`, {
      method: "POST",
    });
    if (!res.ok) alert((await res.json().catch(() => ({}))).error ?? "reset failed");
    refresh();
  };

  const retryOrder = async (orderId: string) => {
    const res = await fetch(`/api/mes/orders/${encodeURIComponent(orderId)}/retry`, {
      method: "POST",
    });
    if (!res.ok) alert((await res.json().catch(() => ({}))).error ?? "retry failed");
    refresh();
  };

  const updatePriority = async (orderId: string, priority: number) => {
    const res = await fetch(`/api/mes/orders/${encodeURIComponent(orderId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ priority }),
    });
    if (!res.ok) alert((await res.json().catch(() => ({}))).error ?? "priority update failed");
    refresh();
  };

  // ── Derived

  // Filter + sort. We don't fight the API order; it already returns
  // PENDING > RELEASED > terminal; we just hide terminal rows by default.
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return orders.filter((o) => {
      if (!showCompleted && TERMINAL.includes(o.status)) return false;
      if (!q) return true;
      const hay = [
        o.order_id,
        o.batch_id ?? "",
        o.line_id ?? "",
        o.product_ref ?? "",
        o.status,
      ]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [orders, showCompleted, query]);

  // Queue position for each PENDING row (1 = next to release).
  const pendingPositions = useMemo(() => {
    const positions = new Map<string, number>();
    let pos = 0;
    // The orders list isn't sorted by priority within PENDING from the
    // API (it sorts by status bucket first, priority second). Re-sort
    // PENDING here so position 1 really is "next out".
    const pending = orders
      .filter((o) => o.status === "PENDING")
      .sort(
        (a, b) =>
          a.priority - b.priority ||
          new Date(a.issued_at).getTime() - new Date(b.issued_at).getTime(),
      );
    for (const o of pending) positions.set(o.order_id, ++pos);
    return positions;
  }, [orders]);

  const estimateMs = (o: MesOrder): number | null => {
    if (stats.avg_lead_ms == null) return null;
    if (o.status !== "PENDING") return null;
    const pos = pendingPositions.get(o.order_id) ?? 0;
    if (!pos) return null;
    // Position 1 enters service when the next slot frees up; position N
    // waits for (N-1) more slots to free. Spread over `max_concurrent`
    // parallel lanes.
    const lanes = Math.max(1, stats.max_concurrent || 1);
    const slotsAhead = Math.ceil(pos / lanes);
    return slotsAhead * stats.avg_lead_ms;
  };

  return (
    <div className="p-6 space-y-6">
      <header className="flex flex-wrap items-baseline gap-4">
        <h1 className="text-2xl font-bold uppercase">Scheduling</h1>
        <span className="text-sm text-muted-foreground">
          MES order queue · polls every 3 s · lead-time avg from{" "}
          {stats.sample_size} completion(s) over the last 24 h
          {stats.avg_lead_ms != null
            ? ` (${fmtDuration(stats.avg_lead_ms)})`
            : ""}
        </span>
      </header>

      {error && (
        <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
          {error}
        </div>
      )}

      <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <SummaryCard label="Pending" value={summary.pending} tint={STATUS_TINT.PENDING} />
        <SummaryCard label="In flight" value={summary.released} tint={STATUS_TINT.RELEASED} />
        <SummaryCard label="Completed" value={summary.completed} tint={STATUS_TINT.COMPLETED} />
        <SummaryCard label="Aborted" value={summary.aborted} tint={STATUS_TINT.ABORTED} />
        <SummaryCard label="Cancelled" value={summary.cancelled} tint={STATUS_TINT.CANCELLED} />
      </section>

      <section className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="Search by order / batch / line / product / status…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="px-3 py-1.5 rounded-md bg-muted text-sm focus:outline-none focus:ring-1 focus:ring-primary flex-1 min-w-64"
        />
        <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
          <input
            type="checkbox"
            checked={showCompleted}
            onChange={(e) => setShowCompleted(e.target.checked)}
          />
          Show completed &amp; cancelled
        </label>
        <span className="text-xs text-muted-foreground">
          {filtered.length} of {orders.length} shown
        </span>
      </section>

      <section className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted">
            <tr className="border-b">
              <th className="text-left p-2 whitespace-nowrap">Order</th>
              <th className="text-left p-2 whitespace-nowrap">Batch</th>
              <th className="text-left p-2 whitespace-nowrap">Product</th>
              <th className="text-left p-2 whitespace-nowrap">Line</th>
              <th className="text-left p-2 whitespace-nowrap">Priority</th>
              <th className="text-left p-2 whitespace-nowrap">Status</th>
              <th className="text-right p-2 whitespace-nowrap">Attempt</th>
              <th className="text-left p-2 whitespace-nowrap">Issued</th>
              <th className="text-left p-2 whitespace-nowrap">Est. delivery</th>
              <th className="text-left p-2 whitespace-nowrap">Action</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td
                  colSpan={10}
                  className="p-4 text-center text-muted-foreground"
                >
                  {orders.length === 0
                    ? "No orders."
                    : "No orders match the filters."}
                </td>
              </tr>
            )}
            {filtered.map((o) => {
              const eta = estimateMs(o);
              const etaDate =
                eta != null ? new Date(Date.now() + eta) : null;
              return (
                <tr key={o.id} className="border-b">
                  <td className="p-2 font-mono text-xs whitespace-nowrap">
                    {o.order_id}
                  </td>
                  <td className="p-2 whitespace-nowrap text-xs">
                    {o.batch_total > 1 ? (
                      <span title={o.batch_id ?? ""}>
                        <span className="font-mono">{o.batch_id ?? "—"}</span>{" "}
                        <span className="text-muted-foreground">
                          ({o.batch_index}/{o.batch_total})
                        </span>
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="p-2 whitespace-nowrap">
                    {o.product_ref ?? "—"}
                  </td>
                  <td className="p-2 whitespace-nowrap">
                    {o.line_id ?? "—"}
                  </td>
                  <td className="p-2">
                    {o.status === "PENDING" ? (
                      <PriorityEditor
                        value={o.priority}
                        onChange={(p) => updatePriority(o.order_id, p)}
                      />
                    ) : (
                      <span className="text-muted-foreground">{o.priority}</span>
                    )}
                  </td>
                  <td className="p-2">
                    <span
                      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium ${STATUS_TINT[o.status]}`}
                    >
                      {STATUS_LABEL[o.status]}
                    </span>
                  </td>
                  <td className="p-2 text-right">{o.attempt_count}</td>
                  <td className="p-2 text-muted-foreground whitespace-nowrap">
                    {new Date(o.issued_at).toLocaleString()}
                  </td>
                  <td className="p-2 text-muted-foreground whitespace-nowrap">
                    {etaDate
                      ? `${etaDate.toLocaleTimeString()} (${fmtDuration(eta)})`
                      : "—"}
                  </td>
                  <td className="p-2 whitespace-nowrap space-x-2">
                    {o.status === "PENDING" && (
                      <button
                        onClick={() => cancelOrder(o.order_id)}
                        className="text-red-600 hover:underline text-xs"
                      >
                        Cancel
                      </button>
                    )}
                    {o.status === "RELEASED" && (
                      <button
                        onClick={() => resetOrder(o.order_id)}
                        className="text-amber-600 hover:underline text-xs"
                        title="Flip back to PENDING so the dispatcher republishes"
                      >
                        Reset
                      </button>
                    )}
                    {(o.status === "ABORTED" || o.status === "CANCELLED") && (
                      <button
                        onClick={() => retryOrder(o.order_id)}
                        className="text-blue-600 hover:underline text-xs"
                      >
                        Retry
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  tint,
}: {
  label: string;
  value: number;
  tint: string;
}) {
  return (
    <div className={`rounded-md border p-3 ${tint}`}>
      <div className="text-[10px] uppercase tracking-wider opacity-80">
        {label}
      </div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
    </div>
  );
}

function PriorityEditor({
  value,
  onChange,
}: {
  value: number;
  onChange: (next: number) => void;
}) {
  return (
    <div className="inline-flex items-center gap-1">
      <button
        onClick={() => onChange(Math.max(1, value - 1))}
        className="px-1.5 rounded border bg-background hover:bg-muted text-xs"
        title="Higher priority"
      >
        −
      </button>
      <span className="w-7 text-center text-sm tabular-nums">{value}</span>
      <button
        onClick={() => onChange(Math.min(999, value + 1))}
        className="px-1.5 rounded border bg-background hover:bg-muted text-xs"
        title="Lower priority"
      >
        +
      </button>
    </div>
  );
}
