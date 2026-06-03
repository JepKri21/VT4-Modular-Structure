"use client";

import Link from "next/link";
import { useState, useEffect, useCallback, useRef } from "react";
import {
  Boxes,
  CheckCircle2,
  Circle,
  RefreshCw,
  X,
  Server,
  Plus,
  Minus,
  AlertCircle,
  AlertTriangle,
  PackageOpen,
} from "lucide-react";
import type { ComponentWithInventory, ResourceWithAllocations } from "@/lib/inventory";

const POLL_INTERVAL_MS = 30_000;

/* ── helpers ─────────────────────────────────────────────────────────────── */

type PropertyKey = "material" | "color" | "finish" | "currentRating" | "voltageRating" | "version";

const PROPERTY_LABELS: Record<PropertyKey, string> = {
  material: "Material",
  color: "Color",
  finish: "Finish",
  currentRating: "Current",
  voltageRating: "Voltage",
  version: "Type",
};

const ALL_PROPERTY_KEYS: PropertyKey[] = [
  "material", "color", "finish", "currentRating", "voltageRating", "version",
];

function getDifferentiatingKeys(components: ComponentWithInventory[]): Set<PropertyKey> {
  const keys = new Set<PropertyKey>();
  for (const key of ALL_PROPERTY_KEYS) {
    const values = new Set(components.map((c) => c[key] ?? null));
    if (values.size > 1) keys.add(key);
  }
  return keys;
}

function differentiatingPropertyItems(
  component: ComponentWithInventory,
  diffKeys: Set<PropertyKey>
): Array<{ label: string; value: string }> {
  const items: Array<{ label: string; value: string }> = [];
  for (const key of diffKeys) {
    const val = component[key];
    items.push({ label: PROPERTY_LABELS[key], value: val ?? "—" });
  }
  if (items.length === 0) {
    for (const key of ALL_PROPERTY_KEYS) {
      const val = component[key];
      if (val) items.push({ label: PROPERTY_LABELS[key], value: val });
    }
  }
  return items;
}

function typeLabel(component: ComponentWithInventory): string {
  const parts = [
    component.material, component.color, component.finish,
    component.currentRating, component.voltageRating, component.version,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : "Standard";
}

/* ── TypeCard ─────────────────────────────────────────────────────────────── */

interface TypeCardProps {
  component: ComponentWithInventory;
  netAvailable: number;
  quantity: number;
  locked: boolean;
  onAdd: () => void;
  onRemove: () => void;
  onQuantityChange: (qty: number) => void;
  diffKeys: Set<PropertyKey>;
}

function TypeCard({
  component, netAvailable, quantity, locked,
  onAdd, onRemove, onQuantityChange, diffKeys,
}: TypeCardProps) {
  const isSelected = quantity > 0;
  const outOfStock = netAvailable === 0 && !isSelected;
  const disabled = locked && !isSelected;

  return (
    <div className={`rounded-xl border p-4 flex flex-col gap-3 transition-all
      ${isSelected ? "border-primary/60 bg-primary/5 shadow-sm"
        : disabled ? "border-border bg-muted/10 opacity-40 pointer-events-none"
        : outOfStock ? "border-border bg-muted/20 opacity-60"
        : "border-border bg-card hover:shadow-sm hover:border-primary/30"}`}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
        <div className="min-w-0 flex-1">
          <p className="break-words font-semibold text-sm leading-tight">{component.name}</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {differentiatingPropertyItems(component, diffKeys).map((item) => (
              <span key={`${item.label}-${item.value}`}
                className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                {item.label}: {item.value}
              </span>
            ))}
          </div>
        </div>
        <div className="flex shrink-0 flex-row items-baseline justify-between gap-2 sm:flex-col sm:items-end sm:justify-start sm:gap-0">
          <span className={`text-xl font-bold leading-none sm:text-2xl ${outOfStock ? "text-destructive" : "text-primary"}`}>
            {netAvailable}
          </span>
          <span className="text-[11px] leading-none text-muted-foreground sm:text-xs">available</span>
        </div>
      </div>

      {isSelected ? (
        <div className="flex flex-col gap-2">
          {netAvailable > 1 && (
            <div className="flex items-center gap-2 bg-primary/10 rounded-md px-2 py-1">
              <button type="button" onClick={() => onQuantityChange(Math.max(1, quantity - 1))}
                disabled={quantity <= 1}
                className="p-1 hover:bg-primary/20 rounded disabled:opacity-50 transition-colors">
                <Minus className="w-3.5 h-3.5" />
              </button>
              <span className="flex-1 text-center text-sm font-semibold">{quantity}</span>
              <button type="button" onClick={() => onQuantityChange(Math.min(netAvailable, quantity + 1))}
                disabled={quantity >= netAvailable}
                className="p-1 hover:bg-primary/20 rounded disabled:opacity-50 transition-colors">
                <Plus className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
          <button type="button" onClick={onRemove}
            className="flex items-center justify-center gap-1.5 w-full rounded-md border border-primary/50 bg-primary/10 text-primary px-3 py-1.5 text-xs font-semibold hover:bg-destructive/10 hover:text-destructive hover:border-destructive/50 transition-colors">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Selected — click to remove
          </button>
        </div>
      ) : (
        <button type="button" onClick={onAdd} disabled={outOfStock}
          className="flex items-center justify-center gap-1.5 w-full rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:border-primary/50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
          {outOfStock ? <X className="w-3.5 h-3.5" /> : <Circle className="w-3.5 h-3.5" />}
          {outOfStock ? "Out of Stock" : "Select"}
        </button>
      )}
    </div>
  );
}

/* ── ResourcePanel ────────────────────────────────────────────────────────── */

interface ResourcePanelProps {
  resources: ResourceWithAllocations[];
  loading: boolean;
  loaded: boolean;
  lockedCategory: string | null;
  totalSelected: number;
  allocating: boolean;
  onAllocate: (resource: ResourceWithAllocations) => void;
  serverUrl: string;
  onServerUrlChange: (v: string) => void;
  onLoad: () => void;
  error: string | null;
}

function ResourcePanel({
  resources, loading, loaded, lockedCategory, totalSelected,
  allocating, onAllocate, serverUrl, onServerUrlChange, onLoad, error,
}: ResourcePanelProps) {
  const compatible = lockedCategory
    ? resources.filter((r) =>
        r.supportedCategories.some(
          (sc) => sc.toLowerCase() === lockedCategory.toLowerCase()
        )
      )
    : resources;

  return (
    <aside className="flex flex-col gap-4">
      <div className="rounded-xl border border-border bg-card p-4 space-y-3 sticky top-6">
        <h2 className="font-semibold text-sm flex items-center gap-2">
          <Boxes className="w-4 h-4 text-primary" />
          Allocate to Resource
        </h2>

        {/* Server URL */}
        <div className="flex gap-2">
          <div className="flex-1 flex items-center gap-2 rounded-lg border border-border bg-muted/30 px-2.5 py-1.5 text-xs">
            <Server className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
            <input
              type="text"
              value={serverUrl}
              onChange={(e) => onServerUrlChange(e.target.value)}
              placeholder="http://localhost:8081"
              className="flex-1 bg-transparent outline-none placeholder:text-muted-foreground"
            />
          </div>
          <button type="button" onClick={onLoad} disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs hover:bg-muted disabled:opacity-50 transition-colors whitespace-nowrap">
            <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
            {loaded ? "Refresh" : "Load"}
          </button>
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">
            <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {!loaded && !loading && (
          <p className="text-xs text-muted-foreground text-center py-4">
            Enter an AAS server URL and click Load.
          </p>
        )}

        {loaded && compatible.length === 0 && resources.length > 0 && lockedCategory && (
          <div className="flex items-start gap-2 rounded-lg border border-amber-400/40 bg-amber-400/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            <span>No resource supports <strong>{lockedCategory}</strong>.</span>
          </div>
        )}

        {loaded && resources.length === 0 && (
          <p className="text-xs text-muted-foreground text-center py-4">
            No resources with inventory found on the AAS server.
          </p>
        )}

        {/* Resource cards */}
        <div className="flex flex-col gap-3">
          {compatible.map((resource) => {
            const notEnoughSlots = totalSelected > resource.slotsAvailable;
            const canAllocate = totalSelected > 0 && !notEnoughSlots;
            const pct = resource.inventorySize > 0
              ? Math.round((resource.slotsUsed / resource.inventorySize) * 100)
              : 0;

            return (
              <div key={resource.resourceId}
                className={`rounded-lg border p-3 space-y-2.5 transition-all
                  ${canAllocate ? "border-border bg-card" : "border-border bg-muted/20 opacity-70"}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-semibold text-xs leading-tight">{resource.resourceName}</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {resource.supportedCategories.map((cat) => (
                        <span key={cat}
                          className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium
                            ${lockedCategory && cat.toLowerCase() === lockedCategory.toLowerCase()
                              ? "bg-primary/15 text-primary"
                              : "bg-muted text-muted-foreground"}`}>
                          {cat}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-base font-bold leading-none text-primary">{resource.slotsAvailable}</p>
                    <p className="text-[10px] text-muted-foreground">of {resource.inventorySize}</p>
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="h-1 rounded-full bg-muted overflow-hidden">
                    <div className="h-full rounded-full bg-primary/60 transition-all" style={{ width: `${pct}%` }} />
                  </div>
                </div>

                {notEnoughSlots && totalSelected > 0 && (
                  <p className="text-[10px] text-destructive flex items-center gap-1">
                    <AlertCircle className="w-3 h-3 shrink-0" />
                    Only {resource.slotsAvailable} slot{resource.slotsAvailable !== 1 ? "s" : ""} free
                  </p>
                )}

                <button type="button" onClick={() => onAllocate(resource)}
                  disabled={!canAllocate || allocating}
                  className="flex items-center justify-center gap-1.5 w-full rounded-md bg-primary text-primary-foreground px-3 py-1.5 text-xs font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 transition-opacity">
                  {allocating ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Boxes className="w-3 h-3" />}
                  {allocating ? "Allocating..." : "Allocate here"}
                </button>
              </div>
            );
          })}
        </div>

        {totalSelected === 0 && loaded && compatible.length > 0 && (
          <p className="text-xs text-muted-foreground text-center py-2">
            Select components to enable allocation.
          </p>
        )}
      </div>
    </aside>
  );
}

/* ── page ─────────────────────────────────────────────────────────────────── */

export default function AllocationPage() {
  const [allComponents, setAllComponents] = useState<ComponentWithInventory[]>([]);
  const [allAllocations, setAllAllocations] = useState<Array<{ componentTypeId: string; quantity: number }>>([]);
  const [componentsLoading, setComponentsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [selections, setSelections] = useState<Record<string, number>>({});
  const [lockedCategory, setLockedCategory] = useState<string | null>(null);

  const [serverUrl, setServerUrl] = useState("");
  const [resources, setResources] = useState<ResourceWithAllocations[]>([]);
  const [resourcesLoading, setResourcesLoading] = useState(false);
  const [resourcesLoaded, setResourcesLoaded] = useState(false);
  const [resourceError, setResourceError] = useState<string | null>(null);

  const [allocating, setAllocating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<{ resourceName: string; items: Array<{ name: string; qty: number; label: string }> } | null>(null);

  const serverUrlRef = useRef("");

  // Keep ref in sync when user edits the URL input
  useEffect(() => {
    serverUrlRef.current = serverUrl;
  }, [serverUrl]);

  const fetchComponents = useCallback(async () => {
    const [compRes, allocRes] = await Promise.all([
      fetch("/api/inventory"),
      fetch("/api/inventory/allocations"),
    ]);
    const components = (await compRes.json()) as ComponentWithInventory[];
    const allocations = (await allocRes.json()) as Array<{ componentTypeId: string; quantity: number }>;
    setAllComponents(Array.isArray(components) ? components : []);
    setAllAllocations(Array.isArray(allocations) ? allocations : []);
  }, []);

  useEffect(() => {
    fetchComponents().then(() => setComponentsLoading(false)).catch(() => setComponentsLoading(false));
  }, [fetchComponents]);

  const loadResources = useCallback(async () => {
    const sv = serverUrlRef.current;
    setResourcesLoading(true);
    setResourceError(null);
    const url = sv
      ? `/api/inventory/resources?serverUrl=${encodeURIComponent(sv)}`
      : "/api/inventory/resources";
    try {
      const res = await fetch(url);
      if (!res.ok) {
        const data = (await res.json()) as { error?: string };
        throw new Error(data.error ?? "Failed to load resources");
      }
      const data = (await res.json()) as ResourceWithAllocations[];
      setResources(Array.isArray(data) ? data : []);
      setResourcesLoaded(true);
      if (sv) localStorage.setItem("inventory_server_url", sv);

      // Silently clean up stale allocations on every refresh
      if (sv) {
        try {
          const cleanupRes = await fetch("/api/inventory/allocations/cleanup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ serverUrl: sv }),
          });
          if (cleanupRes.ok) {
            await fetchComponents();
            const res2 = await fetch(url);
            if (res2.ok) {
              const data2 = (await res2.json()) as ResourceWithAllocations[];
              setResources(Array.isArray(data2) ? data2 : []);
            }
          }
        } catch {
          // ignore cleanup errors — don't block the refresh
        }
      }
    } catch (err) {
      setResourceError(String(err));
    }
    setResourcesLoading(false);
  }, [fetchComponents]);

  // Auto-load on mount if a server URL is already saved
  useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem("inventory_server_url") ?? "" : "";
    serverUrlRef.current = saved;
    setServerUrl(saved);
    if (saved) void loadResources();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Periodic refresh every 30 s once the panel is loaded
  useEffect(() => {
    const id = setInterval(() => void loadResources(), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [loadResources]);

  // Net available = stock - reserved - already allocated in DB
  const totalAllocatedByType = new Map<string, number>();
  for (const a of allAllocations) {
    totalAllocatedByType.set(a.componentTypeId, (totalAllocatedByType.get(a.componentTypeId) ?? 0) + a.quantity);
  }
  function netAvailable(component: ComponentWithInventory): number {
    return Math.max(0, component.quantityAvailable - component.quantityReserved - (totalAllocatedByType.get(component.id) ?? 0));
  }

  const totalSelected = Object.values(selections).reduce((s, v) => s + v, 0);

  function handleAdd(component: ComponentWithInventory) {
    setSelections((prev) => ({ ...prev, [component.id]: 1 }));
    setLockedCategory(component.category);
    setSuccess(null);
  }

  function handleRemove(componentId: string) {
    setSelections((prev) => {
      const next = { ...prev };
      delete next[componentId];
      // Unlock category if nothing left selected
      if (Object.keys(next).length === 0) setLockedCategory(null);
      return next;
    });
  }

  function handleQuantityChange(componentId: string, qty: number) {
    setSelections((prev) => ({ ...prev, [componentId]: qty }));
  }

  async function handleAllocate(resource: ResourceWithAllocations) {
    setAllocating(true);
    setError(null);
    const items = Object.entries(selections)
      .filter(([, qty]) => qty > 0)
      .map(([componentTypeId, quantity]) => ({ componentTypeId, quantity }));

    try {
      const res = await fetch("/api/inventory/allocations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resourceId: resource.resourceId, items, serverUrl: serverUrl || undefined }),
      });
      if (!res.ok) {
        const data = (await res.json()) as { error?: string };
        throw new Error(data.error ?? "Allocation failed");
      }

      // Show success, reset selections
      setSuccess({
        resourceName: resource.resourceName,
        items: items.map(({ componentTypeId, quantity }) => {
          const comp = allComponents.find((c) => c.id === componentTypeId);
          return { name: comp?.name ?? componentTypeId, qty: quantity, label: comp ? typeLabel(comp) : "" };
        }),
      });
      setSelections({});
      setLockedCategory(null);

      // Refresh inventory counts and resource slots
      await fetchComponents();
      await loadResources();
    } catch (err) {
      setError(String(err));
    }
    setAllocating(false);
  }

  // Group and filter components
  const grouped = allComponents.reduce<Record<string, ComponentWithInventory[]>>((acc, comp) => {
    (acc[comp.category] ??= []).push(comp);
    return acc;
  }, {});

  return (
    <div className="max-w-7xl mx-auto px-4 lg:px-8 py-10 space-y-6">
      {/* Tabs */}
      <div className="flex border-b border-border">
        <Link href="/inventory-management"
          className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
          Resource Inventory
        </Link>
        <span className="px-4 py-2 text-sm font-semibold text-primary border-b-2 border-primary">
          Allocate
        </span>
      </div>

      {/* Page header */}
      <div className="flex items-start gap-4 justify-between">
        <div className="flex items-start gap-4">
          <div className="flex-shrink-0 w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center">
            <Boxes className="w-6 h-6 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Allocate Components</h1>
            <p className="text-muted-foreground text-sm mt-0.5">
              Select components, then allocate them to a resource inventory.
              {lockedCategory && (
                <span className="ml-2 font-medium text-primary">
                  Category locked: {lockedCategory}
                </span>
              )}
            </p>
          </div>
        </div>
        <button type="button"
          onClick={() => { setRefreshing(true); void fetchComponents().then(() => setRefreshing(false)); }}
          disabled={refreshing}
          className="flex items-center gap-1.5 text-xs rounded-md border border-border px-3 py-1.5 text-muted-foreground hover:text-foreground disabled:opacity-50 transition-colors shrink-0">
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Global error */}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span className="flex-1">{error}</span>
          <button type="button" onClick={() => setError(null)}><X className="w-4 h-4" /></button>
        </div>
      )}

      {/* Success banner */}
      {success && (
        <div className="flex items-start gap-3 rounded-xl border border-primary/40 bg-primary/5 px-4 py-3 text-sm">
          <CheckCircle2 className="w-5 h-5 text-primary mt-0.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-primary">Allocated to {success.resourceName}</p>
            <p className="text-muted-foreground text-xs mt-0.5">
              {success.items.map((i) => `${i.qty}× ${i.name}`).join(", ")}
            </p>
          </div>
          <button type="button" onClick={() => setSuccess(null)}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>
      )}

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-8 items-start">

        {/* Left: Components */}
        <div className="space-y-8">
          {componentsLoading ? (
            <div className="flex items-center justify-center py-16 text-muted-foreground text-sm">
              <RefreshCw className="w-4 h-4 animate-spin mr-2" /> Loading...
            </div>
          ) : allComponents.length === 0 ? (
            <div className="flex items-start gap-3 rounded-xl border border-amber-400/40 bg-amber-400/5 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>
                No components in inventory.{" "}
                <Link href="/inventory-management" className="underline font-medium">
                  Sync from AAS server first.
                </Link>
              </span>
            </div>
          ) : (
            Object.entries(grouped).map(([category, components]) => {
              const available = components.filter((c) => netAvailable(c) > 0 || (selections[c.id] ?? 0) > 0);
              if (available.length === 0) return null;

              const isLockedOut = lockedCategory !== null && lockedCategory !== category;
              const diffKeys = getDifferentiatingKeys(available);

              return (
                <section key={category} className={`space-y-3 transition-opacity ${isLockedOut ? "opacity-30 pointer-events-none" : ""}`}>
                  <div className="flex items-center gap-2 border-b border-border pb-2">
                    <h2 className="text-sm font-semibold">{category}</h2>
                    {available.some((c) => (selections[c.id] ?? 0) > 0) && (
                      <span className="text-xs text-primary flex items-center gap-1 ml-auto">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        {available.filter((c) => (selections[c.id] ?? 0) > 0).reduce((s, c) => s + (selections[c.id] ?? 0), 0)} selected
                      </span>
                    )}
                    {isLockedOut && (
                      <span className="text-xs text-muted-foreground ml-auto">
                        Clear selection to enable
                      </span>
                    )}
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {available.map((component) => (
                      <TypeCard
                        key={component.id}
                        component={component}
                        netAvailable={netAvailable(component)}
                        quantity={selections[component.id] ?? 0}
                        locked={isLockedOut}
                        diffKeys={diffKeys}
                        onAdd={() => handleAdd(component)}
                        onRemove={() => handleRemove(component.id)}
                        onQuantityChange={(qty) => handleQuantityChange(component.id, qty)}
                      />
                    ))}
                  </div>
                </section>
              );
            })
          )}

          {/* Clear button */}
          {totalSelected > 0 && (
            <div className="flex items-center gap-3 pt-2 border-t border-border">
              <button type="button"
                onClick={() => { setSelections({}); setLockedCategory(null); }}
                className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
                <X className="w-4 h-4" />
                Clear selection ({totalSelected} item{totalSelected !== 1 ? "s" : ""})
              </button>
              <Link href="/inventory-management"
                className="ml-auto flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
                <PackageOpen className="w-4 h-4" />
                Back to Inventory
              </Link>
            </div>
          )}
        </div>

        {/* Right: Resources */}
        <ResourcePanel
          resources={resources}
          loading={resourcesLoading}
          loaded={resourcesLoaded}
          lockedCategory={lockedCategory}
          totalSelected={totalSelected}
          allocating={allocating}
          onAllocate={(r) => void handleAllocate(r)}
          serverUrl={serverUrl}
          onServerUrlChange={setServerUrl}
          onLoad={() => void loadResources()}
          error={resourceError}
        />
      </div>
    </div>
  );
}
