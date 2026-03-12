"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";

type ReleasedOrder = {
  order_id: string;
  product_type: string;
  status: string;
  created_date: string;
  assembled_date: string | null;
  configuration: Record<string, string | number | Record<string, string | number>> | null;
  model_numbers_needed: Record<string, string> | null;
  shell_instances: Record<string, string> | null;
};

export default function ReleasedPage() {
  const router = useRouter();
  const [orders, setOrders] = useState<ReleasedOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetch("/api/configurator/released")
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) {
          setOrders(data);
        } else {
          setError(data.error ?? "Unknown error");
        }
      })
      .catch(() => setError("Could not reach the configurator API"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const configLabel = (key: string) =>
    key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Released Products</h1>
        <div className="flex gap-2">
          <button
            className="bg-muted text-muted-foreground px-3 py-1.5 rounded hover:bg-accent text-sm"
            onClick={load}
            type="button"
          >
            ↻ Refresh
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

      {loading && <p className="text-muted-foreground">Loading released products…</p>}
      {error && <p className="text-red-500">❌ {error}</p>}

      {!loading && !error && orders.length === 0 && (
        <p className="text-muted-foreground">
          No released products yet. Assemble and release an order first.
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {orders.map((order) => (
          <div
            key={order.order_id}
            className="border border-border bg-card rounded-xl p-5 space-y-3 hover:shadow-md transition"
          >
            {/* Header */}
            <div className="flex justify-between items-start">
              <div>
                <span className="font-bold text-lg text-foreground">
                  {order.order_id}
                </span>
                <span className="ml-2 text-sm text-muted-foreground">
                  {order.product_type}
                </span>
              </div>
              <span className="text-xs font-medium px-2 py-1 rounded border bg-purple-500/15 text-purple-500 border-purple-500/30">
                Released
              </span>
            </div>

            {/* Dates */}
            <div className="text-xs text-muted-foreground space-y-0.5">
              <p>Ordered: {order.created_date}</p>
              {order.assembled_date && <p>Released: {order.assembled_date}</p>}
            </div>

            {/* Configuration */}
            {order.configuration && (
              <div className="text-sm border-t border-border pt-2 space-y-1">
                {Object.entries(order.configuration).map(([k, v]) =>
                  typeof v === "object" && v !== null ? (
                    <div key={k}>
                      <p className="text-xs text-muted-foreground uppercase tracking-wide mt-1 mb-0.5">{k.replace(/_/g, " ")}</p>
                      <div className="grid grid-cols-2 gap-x-6 gap-y-0.5 ml-2">
                        {Object.entries(v).map(([pk, pv]) => (
                          <div key={pk} className="flex justify-between">
                            <span className="text-muted-foreground capitalize">{pk}</span>
                            <span className="font-medium text-foreground">{String(pv)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div key={k} className="flex justify-between">
                      <span className="text-muted-foreground">{configLabel(k)}</span>
                      <span className="font-medium text-foreground">{String(v)}</span>
                    </div>
                  )
                )}
              </div>
            )}

            {/* Components used */}
            {order.model_numbers_needed && (
              <div className="text-sm border-t border-border pt-2 space-y-1">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">
                  Components
                </p>
                {Object.entries(order.model_numbers_needed).map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-muted-foreground">{k}</span>
                    <span className="font-mono text-xs font-medium text-foreground">
                      {v}
                    </span>
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
