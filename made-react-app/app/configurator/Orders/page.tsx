"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type Order = {
  order_id: string;
  product_type: string;
  status: string;
  created_date: string;
  configuration: Record<string, string | number>;
  model_numbers_needed: Record<string, string>;
};

const statusColors: Record<string, string> = {
  pending:     "bg-yellow-400/15 text-yellow-400 border-yellow-400/30",
  step1_done:  "bg-teal-400/15 text-teal-400 border-teal-400/30",
  step2_done:  "bg-blue-200/15 text-blue-200 border-blue-200/30",
  assembling:  "bg-blue-600/15 text-blue-200 border-blue-600/30",
  assembled:   "bg-teal-400/15 text-teal-400 border-teal-400/30",
  released:    "bg-purple-500/15 text-purple-500 border-purple-500/30",
  cancelled:   "bg-red-500/15 text-red-500 border-red-500/30",
};

const statusLabel: Record<string, string> = {
  pending:    "Pending",
  step1_done: "Step 1 Done",
  step2_done: "Step 2 Done",
  assembling: "Assembling",
  assembled:  "Assembled ✓",
  released:   "Released",
  cancelled:  "Cancelled",
};

export default function OrdersPage() {
  const router = useRouter();
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [releasing, setReleasing] = useState<string | null>(null);
  const [assembling, setAssembling] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);

  const load = () => {
    setLoading(true);
    fetch("/api/configurator/orders")
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) {
          setOrders(data);
          setError(null);
        } else {
          setError(data.error ?? "Unknown error");
        }
      })
      .catch(() => setError("Could not reach the configurator API"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const releaseOrder = async (orderId: string) => {    if (!confirm(`Release order ${orderId}? This marks the phone as shipped and removes it from inventory.`)) return;
    setReleasing(orderId);
    try {
      const res = await fetch(`/api/configurator/order/${orderId}/release`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Release failed");
      load();
    } catch (e) {
      alert(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setReleasing(null);
    }
  };

  const assembleOrder = async (orderId: string) => {
    setAssembling(orderId);
    try {
      const res = await fetch(`/api/configurator/order/${orderId}/assemble`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Assembly failed");
      load();
    } catch (e) {
      alert(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setAssembling(null);
    }
  };

  const cancelOrder = async (orderId: string) => {
    if (!confirm(`Cancel order ${orderId}? Reserved components will be released back to inventory.`)) return;
    setCancelling(orderId);
    try {
      const res = await fetch(`/api/configurator/order/${orderId}/cancel`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Cancel failed");
      load();
    } catch (e) {
      alert(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setCancelling(null);
    }
  };

  const resetDb = async () => {
    if (!confirm("Reset the entire database? This will delete ALL orders, reservations, and inventory, then re-sync from disk. Use this after deleting instance files.")) return;
    setResetting(true);
    try {
      const res = await fetch("/api/configurator/reset", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Reset failed");
      load();
    } catch (e) {
      alert(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Configuration Orders</h1>
        <div className="flex gap-2">
          <button
            className="bg-muted text-muted-foreground px-3 py-1.5 rounded hover:bg-accent text-sm"
            onClick={load}
            type="button"
          >
            ↻ Refresh
          </button>
          <button
            className="bg-red-700/80 text-white px-3 py-1.5 rounded hover:bg-red-700 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={resetDb}
            disabled={resetting}
            type="button"
          >
            {resetting ? "Resetting…" : "🗑 Reset DB"}
          </button>
          <button
            className="bg-muted text-muted-foreground px-3 py-1.5 rounded hover:bg-accent text-sm"
            onClick={() => router.push("/configurator")}
            type="button"
          >
            ← Configurator
          </button>
        </div>
      </div>

      {loading && <p className="text-foreground">Loading orders…</p>}
      {error   && <p className="text-red-500">❌ {error}</p>}

      {!loading && !error && orders.length === 0 && (
        <p className="text-foreground">No orders yet. Place one in the configurator.</p>
      )}

      <div className="space-y-4">
        {orders.map((order) => (
          <div key={order.order_id} className="border border-border bg-card rounded p-4 space-y-3">
            {/* Header */}
            <div className="flex justify-between items-start">
              <div>
                <span className="font-bold text-lg text-foreground">{order.order_id}</span>
                <span className="ml-2 text-sm text-foreground">{order.product_type}</span>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`text-xs font-medium px-2 py-1 rounded border ${
                    statusColors[order.status] ?? "bg-muted/50 text-muted-foreground border-border"
                  }`}
                >
                  {statusLabel[order.status] ?? order.status}
                </span>

                {/* Assemble button — pending or mid-assembly */}
                {["pending", "step1_done", "step2_done"].includes(order.status) && (
                  <button
                    onClick={() => assembleOrder(order.order_id)}
                    disabled={assembling === order.order_id}
                    className="text-xs font-medium px-3 py-1 rounded border bg-teal-600 text-white border-teal-600/50 hover:bg-teal-600/80 disabled:opacity-50 disabled:cursor-not-allowed"
                    type="button"
                  >
                    {assembling === order.order_id ? "Assembling…" : "⚙ Assemble"}
                  </button>
                )}

                {/* Release button — only shown for fully assembled orders */}
                {order.status === "assembled" && (
                  <button
                    onClick={() => releaseOrder(order.order_id)}
                    disabled={releasing === order.order_id}
                    className="text-xs font-medium px-3 py-1 rounded border bg-purple-500 text-white border-purple-500/50 hover:bg-purple-500/80 disabled:opacity-50 disabled:cursor-not-allowed"
                    type="button"
                  >
                    {releasing === order.order_id ? "Releasing…" : "🚀 Release"}
                  </button>
                )}

                {/* Cancel button — available while not yet assembled/released */}
                {["pending", "step1_done", "step2_done", "assembling"].includes(order.status) && (
                  <button
                    onClick={() => cancelOrder(order.order_id)}
                    disabled={cancelling === order.order_id}
                    className="text-xs font-medium px-3 py-1 rounded border bg-red-600/80 text-white border-red-600/50 hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed"
                    type="button"
                  >
                    {cancelling === order.order_id ? "Cancelling…" : "✕ Cancel"}
                  </button>
                )}
              </div>
            </div>

            <p className="text-xs text-foreground">{order.created_date}</p>

            {/* Configuration summary */}
            {order.configuration && (
              <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm border-t border-border pt-2">
                {Object.entries(order.configuration).map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-foreground capitalize">
                      {k.replace(/_/g, " ")}
                    </span>
                    <span className="font-medium text-foreground">{String(v)}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Model numbers */}
            {order.model_numbers_needed && (
              <div className="space-y-1 text-sm border-t border-border pt-2">
                <p className="text-xs text-foreground uppercase tracking-wide mb-1">
                  Reserved Components
                </p>
                {Object.entries(order.model_numbers_needed).map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-foreground">{k}</span>
                    <span className="font-mono text-xs font-medium text-foreground">{v}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
