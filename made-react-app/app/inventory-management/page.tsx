"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import {
  PackageOpen,
  RefreshCw,
  Server,
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Boxes,
} from "lucide-react";
import type { ComponentWithInventory, ResourceWithAllocations } from "@/lib/inventory";

const POLL_INTERVAL_MS = 30_000;
const STORAGE_KEY = "inventory_server_url";

type PropertyKey = "material" | "color" | "finish" | "currentRating" | "voltageRating" | "version";
const ALL_PROPERTY_KEYS: PropertyKey[] = ["material", "color", "finish", "currentRating", "voltageRating", "version"];

function typeLabel(component: ComponentWithInventory): string {
  const parts = ALL_PROPERTY_KEYS.map((k) => component[k]).filter(Boolean);
  return parts.length > 0 ? (parts as string[]).join(" · ") : "Standard";
}

/* ── ComponentCard ──────────────────────────────────────────────────────── */

function ComponentCard({
  component,
  quantity,
  muted = false,
}: {
  component: ComponentWithInventory;
  quantity: number;
  muted?: boolean;
}) {
  return (
    <div className={`rounded-xl border p-4 flex flex-col gap-2 transition-shadow hover:shadow-md ${
      muted ? "border-border/60 bg-muted/10" : "border-border bg-card"
    }`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-sm truncate">{component.name}</p>
          <p className="text-xs text-muted-foreground mt-1">{typeLabel(component)}</p>
        </div>
        <div className="flex flex-col items-end gap-0.5 shrink-0">
          <span className={`text-2xl font-bold leading-none ${muted ? "text-muted-foreground" : "text-primary"}`}>
            {quantity}
          </span>
          <span className="text-xs text-muted-foreground">
            {muted ? "on AAS" : "allocated"}
          </span>
          {!muted && component.quantityReserved > 0 && (
            <span className="text-xs text-amber-600 dark:text-amber-400">
              {component.quantityReserved} reserved
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── page ───────────────────────────────────────────────────────────────── */

export default function InventoryManagementPage() {
  const [resources, setResources] = useState<ResourceWithAllocations[]>([]);
  const [allComponents, setAllComponents] = useState<ComponentWithInventory[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [lastSyncMessage, setLastSyncMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const [syncUrl, setSyncUrl] = useState("http://localhost:8081");
  const [syncOpen, setSyncOpen] = useState(false);
  const [expandedResources, setExpandedResources] = useState<Set<string>>(new Set());

  useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
    if (saved) setSyncUrl(saved);
  }, []);

  const syncUrlRef = useRef(syncUrl);
  useEffect(() => {
    syncUrlRef.current = syncUrl;
    if (syncUrl.trim()) localStorage.setItem(STORAGE_KEY, syncUrl.trim());
  }, [syncUrl]);

  const loadLocal = useCallback(async () => {
    const [compRes, resRes] = await Promise.all([
      fetch("/api/inventory"),
      fetch("/api/inventory/resources"),
    ]);
    const components = (await compRes.json()) as ComponentWithInventory[];
    const resourceData = (await resRes.json()) as ResourceWithAllocations[];
    setAllComponents(Array.isArray(components) ? components : []);
    setResources(Array.isArray(resourceData) ? resourceData : []);
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
      const data = (await res.json()) as { message?: string; error?: string };
      setLastSyncMessage({
        text: data.error ?? data.message ?? "Sync complete.",
        ok: res.ok && !data.error,
      });
    } catch (err) {
      setLastSyncMessage({ text: String(err), ok: false });
    }
  }, []);

  const refresh = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true);
    await syncFromServer(syncUrlRef.current);
    // Also re-sync resource shells so deleted resources are removed from DB
    if (syncUrlRef.current.trim()) {
      await fetch(
        `/api/inventory/resources?serverUrl=${encodeURIComponent(syncUrlRef.current.trim())}`
      ).catch(() => {});
    }
    await loadLocal().catch(() => {});
    setLoading(false);
    setRefreshing(false);
  }, [syncFromServer, loadLocal]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const id = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  function toggleResource(id: string) {
    setExpandedResources((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const componentById = new Map(allComponents.map((c) => [c.id, c]));

  const activeResources = resources.filter((r) => r.allocations && r.allocations.length > 0);

  const unallocated = allComponents.filter(
    (c) => c.quantityAvailable - c.quantityReserved - (c.quantityAllocated ?? 0) > 0
  );
  const unallocatedByCategory = unallocated.reduce<Record<string, ComponentWithInventory[]>>(
    (acc, c) => { (acc[c.category] ??= []).push(c); return acc; },
    {}
  );

  const hasAnything = activeResources.length > 0 || unallocated.length > 0;

  return (
    <div className="max-w-6xl mx-auto px-8 py-10 space-y-8">
      {/* Tabs */}
      <div className="flex border-b border-border -mx-8 px-8">
        <span className="px-4 py-2 text-sm font-semibold text-primary border-b-2 border-primary">
          Resource Inventory
        </span>
        <Link
          href="/inventory-management/allocation"
          className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          Allocate
        </Link>
      </div>

      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <Boxes className="w-6 h-6 text-primary" />
            <h1 className="text-2xl font-bold">Resource Inventory</h1>
          </div>
          {lastUpdated && (
            <p className="text-xs text-muted-foreground">
              Last synced {lastUpdated.toLocaleTimeString()} · auto-refreshes every 30 s
            </p>
          )}
          {lastSyncMessage && (
            <div className={`flex items-center gap-1.5 text-xs mt-1 ${lastSyncMessage.ok ? "text-primary" : "text-destructive"}`}>
              {lastSyncMessage.ok
                ? <CheckCircle2 className="w-3 h-3 shrink-0" />
                : <AlertCircle className="w-3 h-3 shrink-0" />}
              {lastSyncMessage.text}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => void refresh(true)}
          disabled={refreshing}
          className="flex items-center gap-1.5 text-xs rounded-md border border-border px-3 py-1.5 text-muted-foreground hover:text-foreground disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
          {refreshing ? "Syncing…" : "Sync & Refresh"}
        </button>
      </div>

      {/* AAS Server panel */}
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <button
          type="button"
          onClick={() => setSyncOpen((o) => !o)}
          className="flex items-center gap-2 w-full px-5 py-4 text-left hover:bg-muted/30 transition-colors"
        >
          <Server className="w-4 h-4 text-primary shrink-0" />
          <span className="font-semibold text-sm flex-1">AAS Server</span>
          <span className="text-xs text-muted-foreground mr-2">{syncUrl}</span>
          {syncOpen
            ? <ChevronDown className="w-4 h-4 text-muted-foreground" />
            : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
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
                onClick={() => void refresh(true)}
                className="flex items-center gap-2 rounded-lg bg-primary text-primary-foreground px-4 py-2 text-sm font-semibold disabled:opacity-50 hover:opacity-90 transition-opacity"
              >
                <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
                {refreshing ? "Syncing…" : "Sync now"}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-20 text-muted-foreground text-sm">
          <RefreshCw className="w-4 h-4 animate-spin mr-2" /> Loading…
        </div>
      ) : !hasAnything ? (
        <div className="rounded-xl border border-dashed border-border bg-muted/20 py-20 flex flex-col items-center gap-3 text-center">
          <PackageOpen className="w-12 h-12 text-muted-foreground/30" />
          <p className="text-sm text-muted-foreground">No components in any resource inventory yet.</p>
          <p className="text-xs text-muted-foreground/60 max-w-xs">
            Sync from the AAS server above, then use the{" "}
            <Link href="/inventory-management/allocation" className="underline">Allocate</Link>{" "}
            tab to assign components to resources.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Resource sections */}
          {activeResources.map((resource) => {
            const isExpanded = expandedResources.has(resource.resourceId);

            const byCategoryMap: Record<string, Map<string, { component: ComponentWithInventory; quantity: number }>> = {};
            for (const alloc of resource.allocations) {
              const comp = componentById.get(alloc.componentTypeId);
              if (!comp) continue;
              const cat = alloc.category || comp.category;
              const catMap = (byCategoryMap[cat] ??= new Map());
              const existing = catMap.get(comp.id);
              if (existing) {
                existing.quantity += alloc.quantity;
              } else {
                catMap.set(comp.id, { component: comp, quantity: alloc.quantity });
              }
            }
            const byCategory = Object.fromEntries(
              Object.entries(byCategoryMap).map(([cat, map]) => [cat, Array.from(map.values())])
            );

            const pct = resource.inventorySize > 0
              ? Math.round((resource.slotsUsed / resource.inventorySize) * 100)
              : 0;

            return (
              <div key={resource.resourceId} className="rounded-xl border border-border bg-card overflow-hidden">
                <button
                  type="button"
                  onClick={() => toggleResource(resource.resourceId)}
                  className="flex items-center gap-3 w-full px-5 py-4 text-left hover:bg-muted/30 transition-colors"
                >
                  <Boxes className="w-4 h-4 text-primary shrink-0" />
                  <span className="font-semibold text-sm flex-1">{resource.resourceName}</span>
                  <span className="text-xs text-muted-foreground mr-1">
                    {resource.slotsUsed} / {resource.inventorySize} slots
                  </span>
                  <div className="w-16 h-1.5 rounded-full bg-muted overflow-hidden mr-2">
                    <div className="h-full rounded-full bg-primary/60" style={{ width: `${pct}%` }} />
                  </div>
                  {isExpanded
                    ? <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />
                    : <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />}
                </button>

                {isExpanded && (
                  <div className="border-t border-border px-5 pb-5 pt-4 space-y-6">
                    {Object.entries(byCategory).map(([category, items]) => (
                      <section key={category} className="space-y-3">
                        <div className="flex items-center gap-2 border-b border-border pb-1.5">
                          <h3 className="text-sm font-semibold">{category}</h3>
                          <span className="text-xs text-muted-foreground">
                            {items.reduce((s, i) => s + i.quantity, 0)} allocated
                          </span>
                        </div>
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                          {items.map(({ component, quantity }) => (
                            <ComponentCard
                              key={component.id}
                              component={component}
                              quantity={quantity}
                            />
                          ))}
                        </div>
                      </section>
                    ))}
                  </div>
                )}
              </div>
            );
          })}

          {/* Unallocated section */}
          {Object.keys(unallocatedByCategory).length > 0 && (
            <div className="rounded-xl border border-dashed border-border bg-muted/10 overflow-hidden">
              <div className="flex items-center gap-3 px-5 py-4">
                <PackageOpen className="w-4 h-4 text-muted-foreground shrink-0" />
                <div className="flex-1">
                  <span className="font-semibold text-sm text-muted-foreground">Unallocated Components</span>
                  <p className="text-xs text-muted-foreground/70 mt-0.5">
                    On the AAS server but not assigned to any resource — not available in the store.
                  </p>
                </div>
                <Link
                  href="/inventory-management/allocation"
                  className="text-xs text-primary hover:underline shrink-0"
                >
                  Allocate →
                </Link>
              </div>
              <div className="border-t border-border/60 px-5 pb-5 pt-4 space-y-6">
                {Object.entries(unallocatedByCategory).map(([category, items]) => (
                  <section key={category} className="space-y-3">
                    <div className="flex items-center gap-2 border-b border-border/60 pb-1.5">
                      <h3 className="text-sm font-semibold text-muted-foreground">{category}</h3>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                      {items.map((component) => (
                        <ComponentCard
                          key={component.id}
                          component={component}
                          quantity={Math.max(0, component.quantityAvailable - component.quantityReserved - (component.quantityAllocated ?? 0))}
                          muted
                        />
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
