"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  PackageOpen,
  RefreshCw,
  Trash2,
  Server,
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Plus,
} from "lucide-react";
import type { ComponentType } from "@/lib/inventory";

const POLL_INTERVAL_MS = 30_000;
const STORAGE_KEY = "inventory_server_url";

interface ComponentWithInventory extends ComponentType {
  quantityAvailable: number;
  quantityReserved: number;
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

export default function InventoryManagementPage() {
  const [components, setComponents] = useState<ComponentWithInventory[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastSyncMessage, setLastSyncMessage] = useState<{
    text: string;
    ok: boolean;
  } | null>(null);

  const [syncUrl, setSyncUrl] = useState("http://localhost:8081");
  const [syncOpen, setSyncOpen] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [editingQuantity, setEditingQuantity] = useState<string | null>(null);
  const [newQuantity, setNewQuantity] = useState<number>(0);

  // Load persisted server URL from localStorage on mount
  useEffect(() => {
    const saved =
      typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
    if (saved) setSyncUrl(saved);
  }, []);

  const syncUrlRef = useRef(syncUrl);
  useEffect(() => {
    syncUrlRef.current = syncUrl;
    if (syncUrl.trim()) localStorage.setItem(STORAGE_KEY, syncUrl.trim());
  }, [syncUrl]);

  const loadLocal = useCallback(async () => {
    const res = await fetch("/api/inventory");
    const data = (await res.json()) as ComponentWithInventory[];
    setComponents(Array.isArray(data) ? data : []);
    setLastUpdated(new Date());
  }, []);

  const syncFromServer = useCallback(async (url: string) => {
    if (!url.trim()) return;
    try {
      const res = await fetch("/api/inventory/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ serverUrl: url.trim() }),
      });
      const data = (await res.json()) as {
        message?: string;
        error?: string;
      };
      if (!res.ok || data.error) {
        setLastSyncMessage({
          text: data.error ?? `Server returned ${res.status}`,
          ok: false,
        });
      } else {
        setLastSyncMessage({
          text: data.message ?? "Sync complete.",
          ok: true,
        });
      }
    } catch (err) {
      setLastSyncMessage({ text: String(err), ok: false });
    }
  }, []);

  // Refresh = sync from server + reload local DB
  const refresh = useCallback(
    async (showSpinner = false) => {
      if (showSpinner) setRefreshing(true);
      await syncFromServer(syncUrlRef.current);
      await loadLocal().catch(() => setComponents([]));
      setLoading(false);
      setRefreshing(false);
    },
    [syncFromServer, loadLocal]
  );

  // Initial load + auto-refresh every 30 s
  useEffect(() => {
    refresh();
  }, [refresh]);
  useEffect(() => {
    const id = setInterval(() => refresh(), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const handleRemove = async (componentTypeId: string) => {
    await fetch(
      `/api/inventory?id=${encodeURIComponent(componentTypeId)}`,
      { method: "DELETE" }
    );
    setComponents((prev) =>
      prev.filter((item) => item.id !== componentTypeId)
    );
  };

  const handleUpdateQuantity = async (
    componentTypeId: string,
    quantity: number
  ) => {
    try {
      const res = await fetch("/api/inventory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: "update_inventory",
          componentTypeId,
          quantity,
        }),
      });

      if (!res.ok) throw new Error("Failed to update quantity");

      setComponents((prev) =>
        prev.map((c) =>
          c.id === componentTypeId
            ? { ...c, quantityAvailable: quantity }
            : c
        )
      );

      setEditingQuantity(null);
      setNewQuantity(0);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update quantity");
    }
  };

  const handleClearAll = async () => {
    if (!confirmClear) {
      setConfirmClear(true);
      return;
    }
    await Promise.all(
      components.map((item) =>
        fetch(
          `/api/inventory?id=${encodeURIComponent(item.id)}`,
          { method: "DELETE" }
        )
      )
    );
    setComponents([]);
    setConfirmClear(false);
  };

  // Group by category
  const grouped = components.reduce(
    (acc, component) => {
      const category = component.category || "Uncategorized";
      acc[category] = acc[category] ?? [];
      acc[category].push(component);
      return acc;
    },
    {} as Record<string, ComponentWithInventory[]>
  );

  return (
    <div className="max-w-6xl mx-auto px-8 py-10 space-y-8">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <PackageOpen className="w-6 h-6 text-primary" />
            <h1 className="text-2xl font-bold">Component Inventory</h1>
          </div>
          {lastUpdated && (
            <p className="text-xs text-muted-foreground">
              Last synced {lastUpdated.toLocaleTimeString()} · auto-refreshes
              every 30 s
            </p>
          )}
          {lastSyncMessage && (
            <div
              className={`flex items-center gap-1.5 text-xs mt-1 ${
                lastSyncMessage.ok ? "text-primary" : "text-destructive"
              }`}
            >
              {lastSyncMessage.ok ? (
                <CheckCircle2 className="w-3 h-3 shrink-0" />
              ) : (
                <AlertCircle className="w-3 h-3 shrink-0" />
              )}
              {lastSyncMessage.text}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => refresh(true)}
            disabled={refreshing}
            className="flex items-center gap-1.5 text-xs rounded-md border border-border px-3 py-1.5 text-muted-foreground hover:text-foreground disabled:opacity-50 transition-colors"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`}
            />
            {refreshing ? "Syncing…" : "Sync & Refresh"}
          </button>
          {components.length > 0 && (
            <button
              type="button"
              onClick={handleClearAll}
              className={`flex items-center gap-1.5 text-xs rounded-md border px-3 py-1.5 transition-colors ${
                confirmClear
                  ? "border-destructive text-destructive bg-destructive/5"
                  : "border-border text-muted-foreground hover:text-foreground"
              }`}
            >
              <Trash2 className="w-3.5 h-3.5" />
              {confirmClear ? "Confirm clear all" : "Clear all"}
            </button>
          )}
        </div>
      </div>

      {/* Server URL panel */}
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <button
          type="button"
          onClick={() => setSyncOpen((o) => !o)}
          className="flex items-center gap-2 w-full px-5 py-4 text-left hover:bg-muted/30 transition-colors"
        >
          <Server className="w-4 h-4 text-primary shrink-0" />
          <span className="font-semibold text-sm flex-1">AAS Server</span>
          <span className="text-xs text-muted-foreground mr-2">{syncUrl}</span>
          {syncOpen ? (
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted-foreground" />
          )}
        </button>
        {syncOpen && (
          <div className="px-5 pb-5 flex flex-col gap-3 border-t border-border">
            <p className="text-xs text-muted-foreground pt-3">
              The server URL is synced on every refresh and auto-saved.
            </p>
            <div className="flex gap-2 flex-wrap">
              <input
                type="text"
                value={syncUrl}
                onChange={(e) => setSyncUrl(e.target.value)}
                placeholder="http://localhost:8081"
                className="flex-1 min-w-48 rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <button
                type="button"
                disabled={refreshing}
                onClick={() => refresh(true)}
                className="flex items-center gap-2 rounded-lg bg-primary text-primary-foreground px-4 py-2 text-sm font-semibold disabled:opacity-50 hover:opacity-90 transition-opacity"
              >
                <RefreshCw
                  className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`}
                />
                {refreshing ? "Syncing…" : "Sync now"}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Components */}
      {loading ? (
        <div className="flex items-center justify-center py-20 text-muted-foreground text-sm">
          <RefreshCw className="w-4 h-4 animate-spin mr-2" /> Loading…
        </div>
      ) : components.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-muted/20 py-20 flex flex-col items-center gap-3 text-center">
          <PackageOpen className="w-12 h-12 text-muted-foreground/30" />
          <p className="text-sm text-muted-foreground">
            No component types in inventory yet.
          </p>
          <p className="text-xs text-muted-foreground/60 max-w-xs">
            Upload a component via the{" "}
            <a href="/aas-configurator" className="underline">
              AAS Configurator
            </a>{" "}
            or make sure the AAS server is running and click{" "}
            <strong>Sync &amp; Refresh</strong>.
          </p>
        </div>
      ) : (
        <div className="space-y-10">
          {Object.entries(grouped).map(([category, items]) => {
            const totalAvailable = items.reduce(
              (s, c) => s + c.quantityAvailable,
              0
            );
            const totalReserved = items.reduce(
              (s, c) => s + c.quantityReserved,
              0
            );
            return (
              <section key={category} className="space-y-4">
                <div className="flex items-center gap-3 border-b border-border pb-2">
                  <h2 className="text-lg font-semibold">{category}</h2>
                  <span className="text-sm text-muted-foreground">
                    {items.length} type
                    {items.length !== 1 ? "s" : ""} · {totalAvailable} available
                    {totalReserved > 0 && ` · ${totalReserved} reserved`}
                  </span>
                </div>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                  {items.map((component) => (
                    <div
                      key={component.id}
                      className="bg-card rounded-xl border border-border p-4 flex flex-col gap-3 hover:shadow-md transition-shadow"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <p className="font-semibold text-sm truncate">
                            {component.name}
                          </p>
                          <p className="text-xs text-muted-foreground mt-1">
                            {typeLabel(component)}
                          </p>
                        </div>
                        <div className="flex flex-col items-end gap-1.5 shrink-0">
                          <span className="text-2xl font-bold text-primary leading-none">
                            {component.quantityAvailable}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            available
                          </span>
                          {component.quantityReserved > 0 && (
                            <span className="text-xs text-amber-600 dark:text-amber-400">
                              {component.quantityReserved} reserved
                            </span>
                          )}
                        </div>
                      </div>

                      {component.description && (
                        <div className="border-t border-border pt-3 text-xs text-muted-foreground">
                          {component.description}
                        </div>
                      )}

                      <div className="flex gap-2">
                        {editingQuantity === component.id ? (
                          <>
                            <input
                              type="number"
                              min="0"
                              value={newQuantity}
                              onChange={(e) =>
                                setNewQuantity(parseInt(e.target.value) || 0)
                              }
                              className="flex-1 rounded-md border border-border px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                              autoFocus
                            />
                            <button
                              type="button"
                              onClick={() =>
                                handleUpdateQuantity(component.id, newQuantity)
                              }
                              className="px-2 py-1 rounded-md bg-primary text-primary-foreground text-xs font-medium hover:opacity-90"
                            >
                              Save
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setEditingQuantity(null);
                                setNewQuantity(0);
                              }}
                              className="px-2 py-1 rounded-md border border-border text-xs hover:bg-muted"
                            >
                              Cancel
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => {
                                setEditingQuantity(component.id);
                                setNewQuantity(component.quantityAvailable);
                              }}
                              className="flex-1 flex items-center justify-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:text-foreground hover:border-primary transition-colors"
                            >
                              <Plus className="w-3 h-3" /> Edit qty
                            </button>
                            <button
                              type="button"
                              onClick={() => handleRemove(component.id)}
                              className="flex items-center justify-center rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:text-destructive hover:border-destructive transition-colors"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
