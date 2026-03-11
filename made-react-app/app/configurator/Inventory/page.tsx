"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";

type InventoryItem = {
  model_number: string;
  component_type: string;
  material: string;
  color: string;
  finish: string;
  nr_fuses: number | null;
  qty_available: number;
  qty_reserved: number;
  qty_total: number;
};

const POLL_INTERVAL_MS = 30_000; // auto-refresh every 30 s

const Configurator = () => {
  const router = useRouter();
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback((showSpinner = false) => {
    if (showSpinner) setRefreshing(true);
    fetch("/api/configurator")
      .then((res) => res.json())
      .then((data) => {
        setInventory(Array.isArray(data) ? data : []);
        setLastUpdated(new Date());
        setLoading(false);
        setRefreshing(false);
      })
      .catch(() => {
        setInventory([]);
        setLoading(false);
        setRefreshing(false);
      });
  }, []);

  // Initial load
  useEffect(() => { load(); }, [load]);

  // Auto-poll every 30 s
  useEffect(() => {
    const id = setInterval(() => load(), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [load]);

  const grouped = Array.isArray(inventory)
    ? inventory.reduce((acc, item) => {
        acc[item.component_type] = acc[item.component_type] || [];
        acc[item.component_type].push(item);
        return acc;
      }, {} as Record<string, InventoryItem[]>)
    : {};

  const qtyColor = (qty: number) => {
    if (qty === 0) return "text-red-500";
    if (qty < 10) return "text-yellow-400";
    return "text-green-500";
  };

  return (
    <div className="max-w-7xl mx-auto px-8 py-10 space-y-12">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Inventory</h2>
          {lastUpdated && (
            <p className="text-xs text-muted-foreground mt-1">
              Last updated {lastUpdated.toLocaleTimeString()} · auto-refreshes every 30 s
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            className="bg-muted text-muted-foreground px-3 py-1.5 rounded hover:bg-accent text-sm disabled:opacity-50"
            onClick={() => load(true)}
            disabled={refreshing}
            type="button"
          >
            {refreshing ? "Refreshing…" : "↻ Refresh"}
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

      {loading ? (
        <div className="text-muted-foreground">Loading inventory...</div>
      ) : (
        Object.entries(grouped).map(([type, items]) => (
          <section key={type} className="space-y-6">
            <h3 className="text-xl font-semibold border-b border-border pb-2">{type}</h3>

            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {items.map((item) => (
                <div
                  key={item.model_number}
                  className="bg-card rounded-xl shadow-sm border border-border p-5 hover:shadow-md transition"
                >
                  <div className="flex justify-between items-start mb-3">
                    <span className="font-mono text-sm text-foreground">
                      {item.model_number}
                    </span>

                    <div className="text-right">
                      <span
                        className={`text-sm font-semibold ${qtyColor(item.qty_available)}`}
                      >
                        {item.qty_available} avail
                      </span>
                      {item.qty_reserved > 0 && (
                        <span className="block text-xs text-orange-500">
                          {item.qty_reserved} reserved
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="mt-3 pt-3 border-t border-border space-y-1 text-sm">
                    {(item.material || item.color || item.finish || item.nr_fuses != null) ? (
                      <>
                        {item.material && (
                          <div className="flex justify-between">
                            <span className="text-foreground">Material</span>
                            <span className="font-medium text-mutedforeground">{item.material}</span>
                          </div>
                        )}
                        {item.color && (
                          <div className="flex justify-between">
                            <span className="text-foreground">Color</span>
                            <span className="font-medium text-foreground">{item.color}</span>
                          </div>
                        )}
                        {item.finish && (
                          <div className="flex justify-between">
                            <span className="text-foreground">Finish</span>
                            <span className="font-medium text-foreground">{item.finish}</span>
                          </div>
                        )}
                        {item.nr_fuses != null && (
                          <div className="flex justify-between">
                            <span className="text-foreground">Fuses</span>
                            <span className="font-medium text-foreground">
                              {item.nr_fuses} {item.nr_fuses === 1 ? "Fuse" : "Fuses"}
                            </span>
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="text-muted-foreground italic text-xs">No properties</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
};

export default Configurator;