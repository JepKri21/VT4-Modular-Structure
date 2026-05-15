"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, CalendarClock, CheckCircle2, Factory, Package, RefreshCw, ShoppingBag, Trash2 } from "lucide-react";
import type { OrderStatus, PlacedOrder } from "@/lib/inventory";

function formatPlacedAt(value: string | null): string {
  if (!value) return "Unknown time";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function shortOrderId(orderId: string): string {
  return orderId.slice(0, 8).toUpperCase();
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

const STATUS_CONFIG: Record<OrderStatus, { label: string; className: string }> = {
  pending:       { label: "Pending",       className: "border-yellow-300 bg-yellow-50 text-yellow-700 dark:border-yellow-700 dark:bg-yellow-950 dark:text-yellow-300" },
  in_production: { label: "In production", className: "border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950 dark:text-blue-300" },
  fulfilled:     { label: "Fulfilled",     className: "border-green-300 bg-green-50 text-green-700 dark:border-green-700 dark:bg-green-950 dark:text-green-300" },
  cancelled:     { label: "Cancelled",     className: "border-destructive/30 bg-destructive/10 text-destructive" },
};

function StatusBadge({ status }: { status: OrderStatus }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending;
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-medium ${cfg.className}`}>
      {cfg.label}
    </span>
  );
}

export default function AasOrdersPage() {
  const [orders, setOrders] = useState<PlacedOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [advancing, setAdvancing] = useState<string | null>(null);

  const loadOrders = async () => {
    setError(null);
    const response = await fetch("/api/inventory/order");
    const data = (await response.json()) as PlacedOrder[] | { error?: string };

    if (!response.ok) {
      throw new Error("error" in data && data.error ? data.error : "Could not load orders");
    }

    setOrders(Array.isArray(data) ? data : []);
  };

  useEffect(() => {
    loadOrders()
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load orders"))
      .finally(() => setLoading(false));
  }, []);

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

  const handleAdvanceStatus = async (orderId: string, nextStatus: OrderStatus) => {
    setAdvancing(orderId);
    try {
      const res = await fetch("/api/inventory/order", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ orderId, status: nextStatus }),
      });
      if (!res.ok) {
        const data = (await res.json()) as { error?: string };
        throw new Error(data.error ?? "Failed to update status");
      }
      await loadOrders();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update status");
    } finally {
      setAdvancing(null);
    }
  };

  const handleCancelOrder = async (orderId: string) => {
    if (!window.confirm("Cancel this order? Inventory will be released back to stock.")) {
      return;
    }

    setCancelling(orderId);
    try {
      const res = await fetch(`/api/inventory/order?orderId=${orderId}`, {
        method: "DELETE",
      });

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
                  Type-based component orders ready for production fulfillment. Specific instances
                  will be assigned during manufacturing.
                </p>
              </div>
            </div>

            <div className="flex flex-wrap gap-3">
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
            {orders.map((order) => (
              <article
                key={order.orderId}
                className={`rounded-2xl border bg-card p-5 shadow-sm transition-opacity ${
                  order.status === "cancelled" ? "opacity-60 border-muted-foreground/30" :
                  order.status === "fulfilled" ? "border-green-300 dark:border-green-800" : "border-border"
                }`}
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={order.status} />
                      <span className="text-xs text-muted-foreground font-mono break-all">
                        {order.orderId}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                      <span className="flex items-center gap-1.5">
                        <CalendarClock className="h-4 w-4" />
                        Placed {formatPlacedAt(order.placedAt)}
                      </span>
                      {order.startedAt && (
                        <span className="flex items-center gap-1.5">
                          <Factory className="h-4 w-4" />
                          Started {formatPlacedAt(order.startedAt)}
                        </span>
                      )}
                      {order.fulfilledAt && (
                        <span className="flex items-center gap-1.5">
                          <CheckCircle2 className="h-4 w-4 text-green-600" />
                          Fulfilled {formatPlacedAt(order.fulfilledAt)}
                        </span>
                      )}
                    </div>
                    {order.status === "cancelled" && order.cancellationReason && (
                      <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
                        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                        <span>{order.cancellationReason}</span>
                      </div>
                    )}
                  </div>

                  <div className="flex gap-3">
                    <div className="rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm">
                      <div className="text-xs uppercase tracking-wide text-muted-foreground">
                        Items
                      </div>
                      <div className="mt-1 text-lg font-semibold">{order.items.length}</div>
                    </div>
                    {order.status === "pending" && (
                      <button
                        type="button"
                        onClick={() => handleAdvanceStatus(order.orderId, "in_production")}
                        disabled={advancing === order.orderId}
                        className="inline-flex items-center gap-2 rounded-xl border border-blue-300 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50 transition-colors dark:border-blue-700 dark:bg-blue-950 dark:text-blue-300 dark:hover:bg-blue-900"
                      >
                        {advancing === order.orderId ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Factory className="h-4 w-4" />}
                        {advancing === order.orderId ? "Updating…" : "Start production"}
                      </button>
                    )}
                    {order.status === "in_production" && (
                      <button
                        type="button"
                        onClick={() => handleAdvanceStatus(order.orderId, "fulfilled")}
                        disabled={advancing === order.orderId}
                        className="inline-flex items-center gap-2 rounded-xl border border-green-300 bg-green-50 px-4 py-2 text-sm font-medium text-green-700 hover:bg-green-100 disabled:opacity-50 transition-colors dark:border-green-700 dark:bg-green-950 dark:text-green-300 dark:hover:bg-green-900"
                      >
                        {advancing === order.orderId ? <RefreshCw className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                        {advancing === order.orderId ? "Updating…" : "Mark fulfilled"}
                      </button>
                    )}
                    {order.status !== "fulfilled" && !order.cancelledAt && (
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

                <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
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
              </article>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}