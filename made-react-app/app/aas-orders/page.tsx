"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, CalendarClock, CheckCircle2, ChevronsUp, Loader2, Package, RefreshCw, ShoppingBag, Trash2 } from "lucide-react";
import type { PlacedOrder } from "@/lib/inventory";
import { useOrchestrationSnapshot } from "@/lib/useOrchestrationSnapshot";
import type { LineOrder, OrderStep } from "@/lib/orchestration-snapshot";

const ORDERS_POLL_MS = 10_000;

function formatPlacedAt(value: string | null): string {
  if (!value) return "Unknown time";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function typeLabel(component: { material?: string; color?: string; finish?: string; currentRating?: string; voltageRating?: string; version?: string }): string {
  const parts = [
    component.material,
    component.color,
    component.finish,
    component.currentRating,
    component.voltageRating,
    component.version,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : "Standard";
}

function productCount(order: PlacedOrder): number {
  if (order.totalProducts != null) return order.totalProducts;
  if (order.items.length === 0) return 1;
  return Math.min(...order.items.map((i) => i.quantity));
}

function shortIri(iri: string | null): string {
  if (!iri) return "";
  const segs = iri.split("/");
  return segs[segs.length - 1] || iri;
}

/* ── Live status derivation (mirrors production-monitoring) ──────────────────

   A webshop order (UUID) maps to one or more Line Controller orders named
   `ORD-<first 8 chars of the UUID, uppercased>` (with `-1/-2…` suffixes when a
   batch fans out into multiple products). We derive the order's live state from
   the orchestration snapshot's per-step states, exactly like the dispatch queue.
   When the order isn't in the live snapshot (already finished, or not yet
   dispatched), we fall back to the stored DB status.                          */

type LiveState = "pending" | "queued" | "in_progress" | "completed" | "cancelled";

const ACTIVE_STEP_STATES = ["IN_PROGRESS", "ASSIGNED"];

function lineOrderPrefix(orderId: string): string {
  return `ORD-${orderId.slice(0, 8).toUpperCase()}`;
}

function matchLineOrders(orderId: string, lineOrders: LineOrder[]): LineOrder[] {
  const prefix = lineOrderPrefix(orderId);
  return lineOrders.filter(
    (lo) => lo.order_id === prefix || lo.order_id.startsWith(`${prefix}-`)
  );
}

function deriveProgress(matched: LineOrder[]): { done: number; total: number; current: OrderStep | null } {
  let done = 0;
  let total = 0;
  let current: OrderStep | null = null;
  for (const lo of matched) {
    total += lo.steps.length;
    done += lo.steps.filter((s) => s.state.toUpperCase() === "COMPLETED").length;
    if (!current) {
      current =
        lo.steps.find((s) => s.step_id === lo.current_step) ??
        lo.steps.find((s) => ACTIVE_STEP_STATES.includes(s.state.toUpperCase())) ??
        null;
    }
  }
  return { done, total, current };
}

function resolveState(order: PlacedOrder, matched: LineOrder[]): LiveState {
  if (order.status === "cancelled" || order.cancelledAt) return "cancelled";
  if (matched.length > 0) {
    const { done, total } = deriveProgress(matched);
    if (total > 0 && done === total) return "completed";
    const anyActive = matched.some((lo) =>
      lo.steps.some((s) => ACTIVE_STEP_STATES.includes(s.state.toUpperCase()))
    );
    if (done > 0 || anyActive) return "in_progress";
    return "queued";
  }
  // Not in the live snapshot — trust the stored status.
  if (order.status === "fulfilled") return "completed";
  if (order.status === "in_production") return "in_progress";
  return "pending";
}

const LIVE_STATUS_CONFIG: Record<LiveState, { label: string; className: string }> = {
  pending:     { label: "Awaiting dispatch", className: "border-yellow-300 bg-yellow-50 text-yellow-700 dark:border-yellow-700 dark:bg-yellow-950 dark:text-yellow-300" },
  queued:      { label: "Queued",            className: "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-300" },
  in_progress: { label: "In progress",       className: "border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950 dark:text-blue-300" },
  completed:   { label: "Completed",         className: "border-green-300 bg-green-50 text-green-700 dark:border-green-700 dark:bg-green-950 dark:text-green-300" },
  cancelled:   { label: "Cancelled",         className: "border-destructive/30 bg-destructive/10 text-destructive" },
};

function StatusBadge({ state }: { state: LiveState }) {
  const cfg = LIVE_STATUS_CONFIG[state];
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-medium ${cfg.className}`}>
      {cfg.label}
    </span>
  );
}

function ConnectionBadge({ status }: { status: string }) {
  const cls =
    status === "connected"
      ? "bg-green-100 text-green-800 border-green-200 dark:bg-green-950 dark:text-green-300 dark:border-green-800"
      : status === "error"
        ? "bg-red-100 text-red-800 border-red-200 dark:bg-red-950 dark:text-red-300 dark:border-red-800"
        : "bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${cls}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${status === "connected" ? "bg-green-500" : status === "error" ? "bg-red-500" : "bg-amber-500 animate-pulse"}`} />
      Live: {status}
    </span>
  );
}

export default function AasOrdersPage() {
  const [orders, setOrders] = useState<PlacedOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [prioritizing, setPrioritizing] = useState<string | null>(null);
  const [prioritized, setPrioritized] = useState<Set<string>>(new Set());

  const { snapshot, status: liveStatus } = useOrchestrationSnapshot();
  const lineOrders = snapshot?.orders ?? [];

  const loadOrders = useCallback(async () => {
    setError(null);
    const response = await fetch("/api/inventory/order");
    const data = (await response.json()) as PlacedOrder[] | { error?: string };
    if (!response.ok) {
      throw new Error("error" in data && data.error ? data.error : "Could not load orders");
    }
    setOrders(Array.isArray(data) ? data : []);
  }, []);

  useEffect(() => {
    loadOrders()
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load orders"))
      .finally(() => setLoading(false));
  }, [loadOrders]);

  // Poll the DB for newly placed / cancelled orders; live production status
  // arrives separately and in real time via the MQTT snapshot.
  useEffect(() => {
    const id = setInterval(() => { void loadOrders().catch(() => {}); }, ORDERS_POLL_MS);
    return () => clearInterval(id);
  }, [loadOrders]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await loadOrders();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load orders");
    } finally {
      setRefreshing(false);
    }
  };

  const handlePrioritize = async (orderId: string) => {
    setPrioritizing(orderId);
    try {
      const res = await fetch(`/api/inventory/order/${orderId}/priority`, { method: "POST" });
      const data = (await res.json()) as { error?: string; updated?: number };
      if (!res.ok) {
        throw new Error(data.error ?? "Failed to prioritize order");
      }
      setPrioritized((prev) => new Set(prev).add(orderId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to prioritize order");
    } finally {
      setPrioritizing(null);
    }
  };

  const handleCancelOrder = async (orderId: string) => {
    if (!window.confirm("Cancel this order? Reserved inventory will be released back to stock.")) {
      return;
    }
    setCancelling(orderId);
    try {
      const res = await fetch(`/api/inventory/order?orderId=${orderId}`, { method: "DELETE" });
      if (!res.ok) {
        const data = (await res.json()) as { error?: string };
        throw new Error(data.error ?? "Failed to cancel order");
      }
      await loadOrders();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel order");
    } finally {
      setCancelling(null);
    }
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-background via-background to-muted/25">
      <div className="mx-auto max-w-5xl px-4 py-10 space-y-8">
        <section className="rounded-3xl border border-border bg-card/90 p-6 shadow-sm backdrop-blur">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
                <ShoppingBag className="h-3.5 w-3.5" />
                AAS Orders
              </div>
              <div className="space-y-2">
                <h1 className="text-3xl font-semibold tracking-tight">Placed orders</h1>
                <p className="max-w-2xl text-sm text-muted-foreground">
                  Live order status, driven by the production line. Each order&apos;s progress
                  reflects the real manufacturing steps as they complete.
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <ConnectionBadge status={liveStatus} />
              <button
                type="button"
                onClick={handleRefresh}
                disabled={refreshing}
                className="inline-flex items-center gap-2 rounded-xl border border-border bg-background px-4 py-2 text-sm font-medium hover:bg-muted transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
                Refresh
              </button>
              <Link
                href="/virtual-store"
                className="inline-flex items-center gap-2 rounded-xl border border-border bg-background px-4 py-2 text-sm font-medium hover:bg-muted transition-colors"
              >
                <ArrowLeft className="h-4 w-4" />
                Back to virtual store
              </Link>
            </div>
          </div>
        </section>

        {loading ? (
          <div className="rounded-2xl border border-border bg-card p-10 text-center text-sm text-muted-foreground">
            Loading orders...
          </div>
        ) : error ? (
          <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-5 text-sm text-destructive">
            {error}
          </div>
        ) : orders.length === 0 ? (
          <div className="rounded-2xl border border-border bg-card p-10 text-center">
            <Package className="mx-auto mb-3 h-10 w-10 text-muted-foreground" />
            <h2 className="text-lg font-semibold">No orders yet</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Place an order in the virtual store and it will appear here.
            </p>
            <Link
              href="/virtual-store"
              className="mt-5 inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 transition-opacity"
            >
              Go to virtual store
            </Link>
          </div>
        ) : (
          <div className="grid gap-5">
            {orders.map((order) => {
              const matched = matchLineOrders(order.orderId, lineOrders);
              const state = resolveState(order, matched);
              const { done, total, current } = deriveProgress(matched);
              const pct = total === 0 ? 0 : Math.round((done / total) * 100);
              const showProgress = matched.length > 0 && (state === "in_progress" || state === "queued");

              return (
                <article
                  key={order.orderId}
                  className={`rounded-2xl border bg-card p-5 shadow-sm transition-opacity ${
                    state === "cancelled" ? "opacity-60 border-muted-foreground/30" :
                    state === "completed" ? "border-green-300 dark:border-green-800" :
                    state === "in_progress" ? "border-blue-300 dark:border-blue-800" : "border-border"
                  }`}
                >
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge state={state} />
                        {(state === "in_progress" || state === "completed") && total > 0 && (
                          <span className="text-xs text-muted-foreground">
                            {done} / {total} steps · {pct}%
                          </span>
                        )}
                        <span className="text-xs text-muted-foreground font-mono break-all">
                          {order.orderId}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                        <span className="flex items-center gap-1.5">
                          <CalendarClock className="h-4 w-4" />
                          Placed {formatPlacedAt(order.placedAt)}
                        </span>
                        {order.fulfilledAt && state === "completed" && (
                          <span className="flex items-center gap-1.5">
                            <CheckCircle2 className="h-4 w-4 text-green-600" />
                            Fulfilled {formatPlacedAt(order.fulfilledAt)}
                          </span>
                        )}
                      </div>

                      {showProgress && (
                        <div className="space-y-1.5 pt-1">
                          <div className="h-1.5 w-full max-w-sm overflow-hidden rounded bg-muted">
                            <div className="h-full rounded bg-blue-500 transition-all" style={{ width: `${pct}%` }} />
                          </div>
                          {current && (
                            <div className="text-xs text-muted-foreground">
                              <span className="text-muted-foreground/70">Now:</span>{" "}
                              <span className="font-mono">{current.step_id}</span>
                              {current.assigned_resource && (
                                <>
                                  {" "}<span className="text-muted-foreground/70">on</span>{" "}
                                  <span className="font-mono">{shortIri(current.assigned_resource)}</span>
                                </>
                              )}
                            </div>
                          )}
                        </div>
                      )}

                      {state === "cancelled" && order.cancellationReason && (
                        <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
                          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                          <span>{order.cancellationReason}</span>
                        </div>
                      )}
                    </div>

                    <div className="flex gap-3">
                      <div className="rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm min-w-0">
                        <div className="text-xs uppercase tracking-wide text-muted-foreground mb-2">
                          Products ordered
                        </div>
                        <p className="text-sm font-medium">
                          {productCount(order)} × AAU Mobile Phone
                        </p>
                      </div>
                      {state === "in_progress" && (
                        <div className="inline-flex items-center gap-2 rounded-xl border border-blue-300 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 dark:border-blue-700 dark:bg-blue-950 dark:text-blue-300">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Producing
                        </div>
                      )}
                      {state === "pending" && (
                        <button
                          type="button"
                          onClick={() => handlePrioritize(order.orderId)}
                          disabled={prioritizing === order.orderId || prioritized.has(order.orderId)}
                          title="Move this order to the front of the dispatch queue"
                          className="inline-flex items-center gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-medium text-amber-700 hover:bg-amber-100 disabled:opacity-60 transition-colors dark:border-amber-700 dark:bg-amber-950 dark:text-amber-300 dark:hover:bg-amber-900"
                        >
                          {prioritizing === order.orderId ? (
                            <RefreshCw className="h-4 w-4 animate-spin" />
                          ) : (
                            <ChevronsUp className="h-4 w-4" />
                          )}
                          {prioritized.has(order.orderId) ? "Prioritized" : prioritizing === order.orderId ? "Prioritizing…" : "Prioritize"}
                        </button>
                      )}
                      {state !== "completed" && state !== "cancelled" && (
                        <button
                          type="button"
                          onClick={() => handleCancelOrder(order.orderId)}
                          disabled={cancelling === order.orderId}
                          className="inline-flex items-center gap-2 rounded-xl border border-destructive/30 px-4 py-2 text-sm font-medium text-destructive hover:bg-destructive/5 disabled:opacity-50 transition-colors"
                        >
                          {cancelling === order.orderId ? (
                            <RefreshCw className="h-4 w-4 animate-spin" />
                          ) : (
                            <Trash2 className="h-4 w-4" />
                          )}
                          {cancelling === order.orderId ? "Cancelling…" : "Cancel"}
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="mt-5 space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Components used
                  </h3>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {order.items.map((item) => (
                      <div key={item.orderItemId} className="rounded-xl border border-border bg-background p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="font-medium leading-tight">{item.component.name}</p>
                            <p className="mt-1 text-xs text-muted-foreground">
                              Qty: <span className="font-semibold">{item.quantity}</span>
                            </p>
                          </div>
                          <span className="shrink-0 rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary">
                            {item.component.category}
                          </span>
                        </div>
                        {typeLabel(item.component) !== "Standard" && (
                          <p className="mt-3 text-xs text-muted-foreground">
                            {typeLabel(item.component)}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
