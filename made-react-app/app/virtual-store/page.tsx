"use client";

import Link from "next/link";
import { useState, useEffect, useCallback } from "react";
import {
  Smartphone,
  CheckCircle2,
  Circle,
  ShoppingCart,
  AlertCircle,
  RefreshCw,
  X,
  Server,
  Plus,
  Minus,
} from "lucide-react";
import type { ComponentType, ComponentWithInventory } from "@/lib/inventory";

/* ── BOM slot definitions ──────────────────────────────────────────────── */

interface BomSlot {
  id: string;
  label: string;
  description: string;
  required: boolean;
  categoryFilter: string;
  maxQuantity?: number;
}

interface Selection {
  component: ComponentWithInventory;
  quantity: number;
}

interface ProductConfig {
  id: string;
  selections: Record<string, Selection | null>;
}

/* ── helpers ────────────────────────────────────────────────────────────── */

function useSessionId(): string {
  const [id] = useState(() => {
    if (typeof window === "undefined") return "ssr";
    let s = sessionStorage.getItem("vs_session");
    if (!s) {
      s = crypto.randomUUID();
      sessionStorage.setItem("vs_session", s);
    }
    return s;
  });
  return id;
}

function componentPropertyItems(component: ComponentType): Array<{ label: string; value: string }> {
  const items: Array<{ label: string; value: string }> = [];
  if (component.material) items.push({ label: "Material", value: component.material });
  if (component.color) items.push({ label: "Color", value: component.color });
  if (component.finish) items.push({ label: "Finish", value: component.finish });
  if (component.currentRating) items.push({ label: "Current", value: component.currentRating });
  if (component.voltageRating) items.push({ label: "Voltage", value: component.voltageRating });
  if (component.version) items.push({ label: "Type", value: component.version });
  if (items.length === 0) items.push({ label: "Properties", value: "Standard" });
  return items;
}

function componentSummary(component: ComponentType): string {
  return `${component.category}${component.version ? ` - ${component.version}` : ""}`;
}

function typeLabel(component: ComponentType): string {
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

/* ── TypeCard ────────────────────────────────────────────────────────────── */

interface TypeCardProps {
  component: ComponentType;
  available: number;
  maxQuantity?: number;
  isSelected: boolean;
  quantity: number;
  onSelect: () => void;
  onDeselect: () => void;
  onQuantityChange: (qty: number) => void;
  selecting: boolean;
}

function TypeCard({
  component,
  available,
  maxQuantity,
  isSelected,
  quantity,
  onSelect,
  onDeselect,
  onQuantityChange,
  selecting,
}: TypeCardProps) {
  const outOfStock = available === 0 && !isSelected;

  return (
    <div
      className={`rounded-xl border p-4 flex flex-col gap-3 transition-all ${
        isSelected
          ? "border-primary/60 bg-primary/5 shadow-sm"
          : outOfStock
            ? "border-border bg-muted/20 opacity-60"
            : "border-border bg-card hover:shadow-sm hover:border-primary/30"
      }`}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
        <div className="min-w-0 flex-1">
          <p className="break-words font-semibold text-sm leading-tight sm:text-base">
            {component.category}
          </p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {componentPropertyItems(component).map((item) => (
              <span
                key={`${item.label}-${item.value}`}
                className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
              >
                {item.label}: {item.value}
              </span>
            ))}
          </div>
        </div>
        <div className="flex shrink-0 flex-row items-baseline justify-between gap-2 sm:flex-col sm:items-end sm:justify-start sm:gap-0">
          <span
            className={`text-xl font-bold leading-none sm:text-2xl ${
              outOfStock ? "text-destructive" : "text-primary"
            }`}
          >
            {available}
          </span>
          <span className="text-[11px] leading-none text-muted-foreground sm:text-xs">available</span>
        </div>
      </div>

      {isSelected ? (
        <div className="flex flex-col gap-2">
          {Math.min(maxQuantity ?? available, available) > 1 && (
            <div className="flex items-center gap-2 bg-primary/10 rounded-md px-2 py-1">
              <button
                type="button"
                onClick={() => onQuantityChange(Math.max(1, quantity - 1))}
                disabled={quantity <= 1 || selecting}
                className="p-1 hover:bg-primary/20 rounded disabled:opacity-50 transition-colors"
              >
                <Minus className="w-3.5 h-3.5" />
              </button>
              <span className="flex-1 text-center text-sm font-semibold">{quantity}</span>
              <button
                type="button"
                onClick={() => onQuantityChange(Math.min(maxQuantity ?? available, available, quantity + 1))}
                disabled={quantity >= Math.min(maxQuantity ?? available, available) || selecting}
                className="p-1 hover:bg-primary/20 rounded disabled:opacity-50 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
          <button
            type="button"
            onClick={onDeselect}
            disabled={selecting}
            className="flex items-center justify-center gap-1.5 w-full rounded-md border border-primary/50 bg-primary/10 text-primary px-3 py-1.5 text-xs font-semibold hover:bg-destructive/10 hover:text-destructive hover:border-destructive/50 transition-colors disabled:opacity-50"
          >
            {selecting ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <CheckCircle2 className="w-3.5 h-3.5" />
            )}
            {selecting ? "Updating..." : "Selected - click to remove"}
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={onSelect}
          disabled={outOfStock || selecting}
          className="flex items-center justify-center gap-1.5 w-full rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:border-primary/50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {selecting ? (
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
          ) : outOfStock ? (
            <X className="w-3.5 h-3.5" />
          ) : (
            <Circle className="w-3.5 h-3.5" />
          )}
          {selecting ? "Loading..." : outOfStock ? "Out of Stock" : "Select"}
        </button>
      )}
    </div>
  );
}

/* ── page ──────────────────────────────────────────────────────────────────── */

export default function VirtualStorePage() {
  const sessionId = useSessionId();

  const [bomSlots, setBomSlots] = useState<BomSlot[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(true);
  const [allComponents, setAllComponents] = useState<ComponentWithInventory[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [products, setProducts] = useState<ProductConfig[]>([]);
  const [selectingKey, setSelectingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ordering, setOrdering] = useState(false);
  const [orderPlaced, setOrderPlaced] = useState(false);
  const [orderSummary, setOrderSummary] = useState<ProductConfig[]>([]);
  const [currentOrderId, setCurrentOrderId] = useState<string | null>(null);
  const [cancellingOrder, setCancellingOrder] = useState(false);
  const [mesPayload, setMesPayload] = useState<Record<string, unknown> | null>(null);
  const [mesExpanded, setMesExpanded] = useState(false);
  const [mesCopied, setMesCopied] = useState(false);

  const emptySelections = useCallback(
    (slots: BomSlot[]) => Object.fromEntries(slots.map((s) => [s.id, null])),
    []
  );

  const newProduct = useCallback(
    (slots: BomSlot[]): ProductConfig => ({ id: crypto.randomUUID(), selections: emptySelections(slots) }),
    [emptySelections]
  );

  const fetchComponents = useCallback(async () => {
    const res = await fetch("/api/inventory");
    const data = (await res.json()) as ComponentWithInventory[];
    setAllComponents(Array.isArray(data) ? data : []);
  }, []);

  useEffect(() => {
    const serverUrl =
      typeof window !== "undefined"
        ? (localStorage.getItem("inventory_server_url") ?? "")
        : "";
    const url = serverUrl
      ? `/api/inventory/bom-slots?serverUrl=${encodeURIComponent(serverUrl)}`
      : "/api/inventory/bom-slots";

    fetch(url)
      .then((r) => r.json())
      .then((data: BomSlot[]) => {
        if (Array.isArray(data)) {
          setBomSlots(data);
          setProducts([{ id: crypto.randomUUID(), selections: emptySelections(data) }]);
        }
      })
      .catch(() => setError("Could not load product template."))
      .finally(() => setSlotsLoading(false));
  }, [emptySelections]);

  useEffect(() => {
    fetchComponents().then(() => setLoading(false)).catch(() => setLoading(false));
  }, [fetchComponents]);

  const addProduct = () =>
    setProducts((prev) => [...prev, newProduct(bomSlots)]);

  const removeProduct = (productId: string) =>
    setProducts((prev) => prev.length > 1 ? prev.filter((p) => p.id !== productId) : prev);

  const handleSelect = (productId: string, slotId: string, component: ComponentWithInventory) =>
    setProducts((prev) =>
      prev.map((p) =>
        p.id !== productId ? p : { ...p, selections: { ...p.selections, [slotId]: { component, quantity: 1 } } }
      )
    );

  const handleDeselect = (productId: string, slotId: string) =>
    setProducts((prev) =>
      prev.map((p) =>
        p.id !== productId ? p : { ...p, selections: { ...p.selections, [slotId]: null } }
      )
    );

  const handleQuantityChange = (productId: string, slotId: string, newQty: number) =>
    setProducts((prev) =>
      prev.map((p) => {
        if (p.id !== productId) return p;
        const sel = p.selections[slotId];
        if (!sel) return p;
        return { ...p, selections: { ...p.selections, [slotId]: { ...sel, quantity: Math.max(1, newQty) } } };
      })
    );

  const handleCancelAll = () =>
    setProducts([newProduct(bomSlots)]);

  const handleOrder = async () => {
    setOrdering(true);
    setError(null);

    // Aggregate component quantities across all products
    const merged = new Map<string, number>();
    for (const product of products) {
      for (const sel of Object.values(product.selections)) {
        if (!sel) continue;
        merged.set(sel.component.id, (merged.get(sel.component.id) ?? 0) + sel.quantity);
      }
    }
    const items = Array.from(merged.entries()).map(([componentTypeId, quantity]) => ({
      componentTypeId,
      quantity,
    }));

    // Per-product configs for MES payload (slot label + component + quantity)
    const productConfigs = products.map((p) => ({
      items: Object.entries(p.selections)
        .filter(([, sel]) => sel !== null)
        .map(([slotId, sel]) => ({
          slotLabel: bomSlots.find((s) => s.id === slotId)?.label ?? slotId,
          componentTypeId: sel!.component.id,
          quantity: sel!.quantity,
        })),
    }));

    try {
      const res = await fetch("/api/inventory/order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          items,
          session: sessionId,
          totalProducts: products.length,
          productConfigs,
        }),
      });

      if (!res.ok) {
        const errData = (await res.json()) as { error?: string };
        throw new Error(errData.error ?? "Failed to place order");
      }

      const data = (await res.json()) as { orderId: string; mesPayload?: Record<string, unknown> };
      setOrderSummary([...products]);
      setCurrentOrderId(data.orderId);
      setMesPayload(data.mesPayload ?? null);
      setOrderPlaced(true);
    } catch (err) {
      setError(String(err));
    }
    setOrdering(false);
  };

  const handleCancelOrder = async () => {
    if (!currentOrderId) return;
    setCancellingOrder(true);
    try {
      await fetch(`/api/inventory/order?orderId=${currentOrderId}`, { method: "DELETE" });
      setOrderPlaced(false);
      setCurrentOrderId(null);
      setOrderSummary([]);
      setMesPayload(null);
      setMesExpanded(false);
      setProducts([newProduct(bomSlots)]);
      await fetchComponents();
    } catch (err) {
      setError(String(err));
    }
    setCancellingOrder(false);
  };

  const handleReset = async () => {
    setOrderPlaced(false);
    setCurrentOrderId(null);
    setOrderSummary([]);
    setMesPayload(null);
    setMesExpanded(false);
    setProducts([newProduct(bomSlots)]);
    setLoading(true);
    await fetchComponents();
    setLoading(false);
  };

  const requiredFilled =
    products.length > 0 &&
    products.every((p) => bomSlots.filter((s) => s.required).every((s) => p.selections[s.id] !== null));

  const anySelection = products.some((p) => Object.values(p.selections).some((v) => v !== null));

  /* ── order confirmation ── */
  if (orderPlaced) {
    return (
      <div className="max-w-2xl mx-auto py-16 flex flex-col items-center gap-6 text-center">
        <CheckCircle2 className="w-16 h-16 text-primary" />
        <h2 className="text-2xl font-bold">Order Placed!</h2>
        <p className="text-muted-foreground">
          Your component order has been created and is ready for production fulfillment.
          Specific instances will be assigned during manufacturing.
        </p>
        {currentOrderId && (
          <p className="text-xs text-muted-foreground font-mono bg-muted px-3 py-1.5 rounded-md">
            Order ID: {currentOrderId.slice(0, 8).toUpperCase()}
          </p>
        )}

        <div className="w-full flex flex-col gap-3 text-left">
          {orderSummary.map((product, idx) => (
            <div key={product.id} className="rounded-xl border border-border bg-card p-5">
              <h3 className="font-semibold text-sm mb-3">
                Product {idx + 1}
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  ({bomSlots.filter((s) => product.selections[s.id] !== null).length} components)
                </span>
              </h3>
              <ul className="flex flex-col gap-2">
                {bomSlots.map((slot) => {
                  const sel = product.selections[slot.id];
                  return (
                    <li key={slot.id} className="flex items-center gap-3 text-sm">
                      {sel ? (
                        <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0" />
                      ) : (
                        <Circle className="w-4 h-4 text-muted-foreground/40 flex-shrink-0" />
                      )}
                      <span className="text-muted-foreground w-32 flex-shrink-0">{slot.label}</span>
                      {sel ? (
                        <>
                          <span className="font-medium flex-1">{componentSummary(sel.component)}</span>
                          <span className="text-xs text-muted-foreground">
                            {sel.quantity}x {typeLabel(sel.component)}
                          </span>
                        </>
                      ) : (
                        <span className="text-xs text-muted-foreground italic flex-1">—</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>

        {mesPayload && (
          <div className="w-full rounded-xl border border-border bg-card overflow-hidden">
            <button
              type="button"
              onClick={() => setMesExpanded((v) => !v)}
              className="w-full flex items-center justify-between px-5 py-3 text-sm font-semibold hover:bg-muted/40 transition-colors"
            >
              <span>MES Payload (JSON)</span>
              <span className="text-xs text-muted-foreground font-normal">
                {mesExpanded ? "Hide" : "Show"}
              </span>
            </button>
            {mesExpanded && (
              <div className="border-t border-border">
                <div className="flex justify-end px-4 pt-2">
                  <button
                    type="button"
                    onClick={() => {
                      void navigator.clipboard.writeText(JSON.stringify(mesPayload, null, 2));
                      setMesCopied(true);
                      setTimeout(() => setMesCopied(false), 2000);
                    }}
                    className="text-xs text-muted-foreground hover:text-foreground transition-colors px-2 py-1 rounded hover:bg-muted"
                  >
                    {mesCopied ? "Copied!" : "Copy"}
                  </button>
                </div>
                <pre className="px-5 pb-5 pt-2 text-xs font-mono overflow-x-auto text-left whitespace-pre-wrap break-all text-muted-foreground">
                  {JSON.stringify(mesPayload, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}

        <div className="flex gap-3">
          <button
            type="button"
            onClick={handleCancelOrder}
            disabled={cancellingOrder}
            className="flex items-center gap-2 rounded-lg border border-destructive/50 text-destructive px-4 py-2 text-sm hover:bg-destructive/5 disabled:opacity-50 transition-colors"
          >
            {cancellingOrder ? <RefreshCw className="w-4 h-4 animate-spin" /> : <X className="w-4 h-4" />}
            {cancellingOrder ? "Cancelling..." : "Cancel Order"}
          </button>
          <button
            type="button"
            onClick={handleReset}
            disabled={cancellingOrder}
            className="flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm hover:bg-muted disabled:opacity-50 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Configure Another
          </button>
          <Link
            href="/aas-orders"
            className="flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm hover:bg-muted transition-colors"
          >
            View Orders
          </Link>
        </div>
      </div>
    );
  }

  /* ── main page ── */
  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-10">
      {/* Header */}
      <div className="flex items-start gap-5">
        <div className="flex-shrink-0 w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center">
          <Smartphone className="w-8 h-8 text-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold">AAU Mobile Phone</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Configure each product independently. Specific instances will be assigned during production.
          </p>
        </div>
        <button
          type="button"
          onClick={() => { setRefreshing(true); fetchComponents().then(() => setRefreshing(false)); }}
          disabled={refreshing}
          className="flex items-center gap-1.5 text-xs rounded-md border border-border px-3 py-1.5 text-muted-foreground hover:text-foreground disabled:opacity-50 transition-colors flex-shrink-0"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span className="flex-1">{error}</span>
          <button type="button" onClick={() => setError(null)}>
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Empty inventory */}
      {!loading && allComponents.length === 0 && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-400/40 bg-amber-400/5 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
          <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <span>
            No component types available. Upload via the{" "}
            <a href="/aas-configurator" className="underline font-medium">AAS Configurator</a>{" "}
            or{" "}
            <a href="/inventory-management" className="underline font-medium">sync from server</a>.
          </span>
        </div>
      )}

      {/* Products */}
      {loading || slotsLoading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground text-sm">
          <RefreshCw className="w-4 h-4 animate-spin mr-2" /> Loading...
        </div>
      ) : (
        <div className="space-y-12">
          {products.map((product, productIdx) => {
            // How many of each component type are already claimed by other products in this order
            const otherAllocated = new Map<string, number>();
            for (const other of products) {
              if (other.id === product.id) continue;
              for (const sel of Object.values(other.selections)) {
                if (!sel) continue;
                otherAllocated.set(
                  sel.component.id,
                  (otherAllocated.get(sel.component.id) ?? 0) + sel.quantity
                );
              }
            }

            return (
            <div key={product.id} className="space-y-6">
              {/* Product header */}
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center w-7 h-7 rounded-full bg-primary/10 text-primary text-xs font-bold flex-shrink-0">
                  {productIdx + 1}
                </div>
                <span className="font-semibold text-base">Product {productIdx + 1}</span>
                {products.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeProduct(product.id)}
                    className="ml-auto flex items-center gap-1 text-xs text-muted-foreground hover:text-destructive transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                    Remove
                  </button>
                )}
              </div>

              {/* BOM slots for this product */}
              <div className="space-y-6 pl-10">
                {bomSlots.map((slot) => {
                  const slotComponents = allComponents.filter(
                    (c) => c.category.toLowerCase() === slot.categoryFilter.toLowerCase()
                  );
                  const selectedForSlot = product.selections[slot.id];
                  const key = `${product.id}__${slot.id}`;

                  return (
                    <section key={slot.id} className="space-y-3">
                      <div className="flex items-center gap-2 border-b border-border pb-2">
                        <h2 className="text-sm font-semibold">{slot.label}</h2>
                        {slot.required ? (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-primary/10 text-primary font-medium">
                            Required
                          </span>
                        ) : (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-medium">
                            Optional
                          </span>
                        )}
                        {selectedForSlot && (
                          <span className="text-xs text-primary flex items-center gap-1 ml-auto">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            {componentSummary(selectedForSlot.component)} × {selectedForSlot.quantity}
                          </span>
                        )}
                        {slotComponents.length === 0 && !selectedForSlot && (
                          <span className="text-xs text-muted-foreground/70 ml-auto">No types available</span>
                        )}
                      </div>

                      {slotComponents.length === 0 ? (
                        <p className="text-sm text-muted-foreground italic pl-1">{slot.description}</p>
                      ) : (
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                          {slotComponents.map((component) => (
                            <TypeCard
                              key={component.id}
                              component={component}
                              available={Math.max(0, (component.quantityAvailable ?? 0) - (component.quantityReserved ?? 0) - (otherAllocated.get(component.id) ?? 0))}
                              maxQuantity={slot.maxQuantity}
                              isSelected={selectedForSlot?.component.id === component.id}
                              quantity={selectedForSlot?.component.id === component.id ? selectedForSlot.quantity : 1}
                              onSelect={() => {
                                setSelectingKey(key);
                                handleSelect(product.id, slot.id, component);
                                setSelectingKey(null);
                              }}
                              onDeselect={() => handleDeselect(product.id, slot.id)}
                              onQuantityChange={(qty) => handleQuantityChange(product.id, slot.id, qty)}
                              selecting={selectingKey === key}
                            />
                          ))}
                        </div>
                      )}
                    </section>
                  );
                })}
              </div>
            </div>
            );
          })}

          {/* Add product */}
          <button
            type="button"
            onClick={addProduct}
            className="flex items-center gap-2 rounded-lg border border-dashed border-border px-4 py-2.5 text-sm text-muted-foreground hover:text-foreground hover:border-primary/40 transition-colors w-full justify-center"
          >
            <Plus className="w-4 h-4" />
            Add Another Product
          </button>
        </div>
      )}

      {/* Order summary */}
      {anySelection && (
        <div className="rounded-xl border border-border bg-card p-5 space-y-4">
          <h3 className="font-semibold text-sm">
            Order Summary
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {products.length} product{products.length !== 1 ? "s" : ""}
            </span>
          </h3>
          <div className="flex flex-col gap-4">
            {products.map((product, idx) => {
              const hasAny = Object.values(product.selections).some((v) => v !== null);
              if (!hasAny) return null;
              return (
                <div key={product.id}>
                  <p className="text-xs font-semibold text-muted-foreground mb-1.5">
                    Product {idx + 1}
                  </p>
                  <ul className="flex flex-col gap-1.5">
                    {bomSlots.map((slot) => {
                      const sel = product.selections[slot.id];
                      if (!sel) return null;
                      return (
                        <li key={slot.id} className="flex items-center gap-3 text-sm">
                          <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0" />
                          <span className="text-muted-foreground w-32 flex-shrink-0">{slot.label}</span>
                          <span className="font-medium flex-1">{componentSummary(sel.component)}</span>
                          <span className="text-xs text-muted-foreground">
                            {sel.quantity}× {typeLabel(sel.component)}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </div>
          {!requiredFilled && (
            <p className="text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1.5">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              All required components must be selected for every product.
            </p>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={!requiredFilled || ordering}
          onClick={handleOrder}
          className="flex items-center gap-2 rounded-lg bg-primary text-primary-foreground px-6 py-2.5 text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 transition-opacity"
        >
          {ordering ? <RefreshCw className="w-4 h-4 animate-spin" /> : <ShoppingCart className="w-4 h-4" />}
          {ordering ? "Placing Order..." : `Place Order (${products.length})`}
        </button>
        {anySelection && (
          <button
            type="button"
            onClick={handleCancelAll}
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="w-4 h-4" />
            Reset
          </button>
        )}
        <Link
          href="/aas-orders"
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          View Orders
        </Link>
        <a
          href="/inventory-management"
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors ml-auto"
        >
          <Server className="w-4 h-4" />
          Manage Inventory
        </a>
      </div>
    </div>
  );
}
