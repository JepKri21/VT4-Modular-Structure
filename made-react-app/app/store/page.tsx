"use client";

// AAU Smartlab Store — product-card storefront.
//
// Three SKUs on the homepage, one per fuse count (1/2/3). Each SKU opens
// a customisation panel where the shopper picks colour + material for
// the bottom cover and (independently) for the top cover. The fuse
// count is locked to the SKU. Multiple distinct configurations of the
// same SKU can sit in the cart at once; Place Order posts everything
// to /api/inventory/order using the same payload shape as the legacy
// /virtual-store storefront.
//
// Visual preview is rendered as two stacked CSS rectangles — bottom and
// top covers tinted to the picked colours. To swap in Blender renders
// later, drop PNGs into /public/store/ and replace `<ColouredPanel/>`
// with an <Image> that points at `/store/bottom-${color}-${material}.png`
// + `/store/top-${color}-${material}.png` (or a single composite).

import { useEffect, useMemo, useRef, useState } from "react";
import { ShoppingCart, X, Plus, Minus, Star } from "lucide-react";
import type { ComponentWithInventory } from "@/lib/inventory";
import PhoneConfigurator from "@/components/PhoneConfigurator";

interface CartItem {
  id: string;
  skuId: string;
  fuseCount: number;
  bottomColor: string;
  bottomMaterial: string;
  topColor: string;
  topMaterial: string;
  quantity: number;
  bottomCoverId: string;
  topCoverId: string;
  fuseId: string;
  pcbId: string;
}

interface Sku {
  id: string;
  fuseCount: number;
  name: string;
  tagline: string;
  basePrice: number;
}

const SKUS: Sku[] = [
  {
    id: "phone-1f",
    fuseCount: 1,
    name: "AAU Mobile Phone",
    tagline: "Telefon",
    basePrice: 1399,
  },
  {
    id: "phone-2f",
    fuseCount: 2,
    name: "AAU Mobile Phone",
    tagline: "Telefon Pro",
    basePrice: 1599,
  },
  {
    id: "phone-3f",
    fuseCount: 3,
    name: "AAU Mobile Phone",
    tagline: "Telefon Pro Max",
    basePrice: 1799,
  },
];

const COLOR_HEX: Record<string, string> = {
  Black: "#1a1a1a",
  White: "#f5f5f5",
  Blue: "#1e3a8a",
  Green: "#16a34a",
  Red: "#dc2626",
  Gray: "#6b7280",
  Grey: "#6b7280",
  Purple: "#6b21a8",
  Yellow: "#f59e0b",
};

function formatPrice(amount: number): string {
  return `${amount.toLocaleString("da-DK")},00 kr.`;
}

function useSessionId(): string {
  const [id] = useState(() => {
    if (typeof window === "undefined") return "ssr";
    let s = sessionStorage.getItem("store_session");
    if (!s) {
      s = crypto.randomUUID();
      sessionStorage.setItem("store_session", s);
    }
    return s;
  });
  return id;
}

function makeCartId(): string {
  return `cart_${Math.random().toString(36).slice(2, 10)}`;
}

// Reservation accounting — cart items hold a virtual claim on inventory
// so a shopper can't add the same configuration twice when only one kit
// is in stock, nor over-fill the quantity past availability. Fuses scale
// by the kit's fuseCount (a "3-fuse" kit reserves three fuses per unit).
function reservedFor(
  componentId: string,
  cart: CartItem[],
  excludeCartId?: string,
): number {
  let n = 0;
  for (const it of cart) {
    if (excludeCartId && it.id === excludeCartId) continue;
    if (it.bottomCoverId === componentId) n += it.quantity;
    if (it.topCoverId === componentId) n += it.quantity;
    if (it.pcbId === componentId) n += it.quantity;
    if (it.fuseId === componentId) n += it.quantity * it.fuseCount;
  }
  return n;
}

interface ConfigIds {
  bottomCoverId: string;
  topCoverId: string;
  pcbId: string;
  fuseId: string;
  fuseCount: number;
}

function kitsAvailable(
  ids: ConfigIds,
  components: ComponentWithInventory[],
  cart: CartItem[],
  excludeCartId?: string,
): number {
  const qty = (id: string) =>
    components.find((c) => c.id === id)?.quantityAvailable ?? 0;
  const free = (id: string, perKit: number) =>
    Math.floor(
      Math.max(0, qty(id) - reservedFor(id, cart, excludeCartId)) / perKit,
    );
  return Math.min(
    free(ids.bottomCoverId, 1),
    free(ids.topCoverId, 1),
    free(ids.pcbId, 1),
    free(ids.fuseId, ids.fuseCount),
  );
}

export default function StorePage() {
  const [components, setComponents] = useState<ComponentWithInventory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openSku, setOpenSku] = useState<Sku | null>(null);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [cartOpen, setCartOpen] = useState(false);
  const [ordering, setOrdering] = useState(false);
  const [orderToast, setOrderToast] = useState<string | null>(null);

  const sessionId = useSessionId();

  // Cart persistence.
  useEffect(() => {
    const saved = localStorage.getItem("store_cart");
    if (saved) {
      try {
        setCart(JSON.parse(saved));
      } catch {
        /* ignore */
      }
    }
  }, []);
  useEffect(() => {
    localStorage.setItem("store_cart", JSON.stringify(cart));
  }, [cart]);

  const fetchInventory = async () => {
    try {
      const res = await fetch("/api/inventory", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as ComponentWithInventory[];
      setComponents(data);
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    fetchInventory();
  }, []);

  const cartCount = useMemo(
    () => cart.reduce((s, it) => s + it.quantity, 0),
    [cart],
  );
  const cartTotal = useMemo(
    () =>
      cart.reduce((s, it) => s + it.quantity * skuById(it.skuId).basePrice, 0),
    [cart],
  );

  const addToCart = (item: CartItem) => {
    setCart((prev) => {
      const idx = prev.findIndex(
        (c) =>
          c.skuId === item.skuId &&
          c.bottomColor === item.bottomColor &&
          c.bottomMaterial === item.bottomMaterial &&
          c.topColor === item.topColor &&
          c.topMaterial === item.topMaterial,
      );
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = {
          ...next[idx],
          quantity: next[idx].quantity + item.quantity,
        };
        return next;
      }
      return [...prev, item];
    });
    setOpenSku(null);
    setCartOpen(true);
  };

  const updateCartQty = (id: string, delta: number) => {
    setCart((prev) =>
      prev
        .map((c) =>
          c.id === id ? { ...c, quantity: Math.max(1, c.quantity + delta) } : c,
        )
        .filter((c) => c.quantity > 0),
    );
  };

  const removeFromCart = (id: string) =>
    setCart((prev) => prev.filter((c) => c.id !== id));

  const placeOrder = async () => {
    if (cart.length === 0) return;
    setOrdering(true);
    try {
      const merged = new Map<string, number>();
      const productConfigs: {
        items: {
          slotLabel: string;
          componentTypeId: string;
          quantity: number;
        }[];
      }[] = [];
      for (const item of cart) {
        for (let i = 0; i < item.quantity; i++) {
          productConfigs.push({
            items: [
              {
                slotLabel: "BottomCover",
                componentTypeId: item.bottomCoverId,
                quantity: 1,
              },
              { slotLabel: "PCB", componentTypeId: item.pcbId, quantity: 1 },
              {
                slotLabel: "Fuse",
                componentTypeId: item.fuseId,
                quantity: item.fuseCount,
              },
              {
                slotLabel: "TopCover",
                componentTypeId: item.topCoverId,
                quantity: 1,
              },
            ],
          });
          merged.set(
            item.bottomCoverId,
            (merged.get(item.bottomCoverId) ?? 0) + 1,
          );
          merged.set(item.pcbId, (merged.get(item.pcbId) ?? 0) + 1);
          merged.set(
            item.fuseId,
            (merged.get(item.fuseId) ?? 0) + item.fuseCount,
          );
          merged.set(item.topCoverId, (merged.get(item.topCoverId) ?? 0) + 1);
        }
      }

      const items = Array.from(merged.entries()).map(
        ([componentTypeId, quantity]) => ({ componentTypeId, quantity }),
      );

      const res = await fetch("/api/inventory/order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          items,
          session: sessionId,
          totalProducts: productConfigs.length,
          productConfigs,
        }),
      });
      const data = (await res.json()) as { error?: string; orderId?: string };
      if (!res.ok) throw new Error(data.error ?? "Order failed");
      setCart([]);
      setCartOpen(false);
      setOrderToast(`Order ${data.orderId} placed`);
      fetchInventory();
    } catch (err) {
      setOrderToast(String(err));
    } finally {
      setOrdering(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold uppercase">AAU Smartlab Store</h1>
          <p className="text-sm text-muted-foreground">
            Custom AAU Mobile Phones · built to order
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCartOpen(true)}
          className="relative flex items-center gap-2 px-4 py-2 rounded-full bg-muted hover:bg-muted/70 text-sm font-medium"
        >
          <ShoppingCart size={18} />
          Cart
          {cartCount > 0 && (
            <span className="ml-1 inline-flex items-center justify-center min-w-5 h-5 px-1.5 text-[10px] font-semibold bg-primary text-background rounded-full">
              {cartCount}
            </span>
          )}
        </button>
      </header>

      {error && (
        <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
          {error}
        </div>
      )}

      {orderToast && (
        <div className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded p-2 flex items-center justify-between">
          <span>{orderToast}</span>
          <button onClick={() => setOrderToast(null)} className="text-xs">
            dismiss
          </button>
        </div>
      )}

      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {SKUS.map((sku) => (
          <ProductCard
            key={sku.id}
            sku={sku}
            disabled={loading}
            onClick={() => setOpenSku(sku)}
          />
        ))}
      </section>

      {openSku && (
        <ProductPanel
          sku={openSku}
          components={components}
          cart={cart}
          onClose={() => setOpenSku(null)}
          onAdd={addToCart}
        />
      )}

      {cartOpen && (
        <CartPanel
          items={cart}
          components={components}
          total={cartTotal}
          ordering={ordering}
          onClose={() => setCartOpen(false)}
          onUpdateQty={updateCartQty}
          onRemove={removeFromCart}
          onPlaceOrder={placeOrder}
        />
      )}
    </div>
  );
}

function skuById(id: string): Sku {
  return SKUS.find((s) => s.id === id) ?? SKUS[0];
}

/* ── Product card ───────────────────────────────────────────────────── */

// 3D-tilt product card. The tilt math runs on the un-rotated bounding
// box: `getBoundingClientRect()` already reflects the rendered transform,
// so reading it while a transform is applied would feed back into itself
// and make the angle jitter. Instead we capture the rect on pointer-enter
// and reuse it for the duration of the hover.
function ProductCard({
  sku,
  disabled,
  onClick,
}: {
  sku: Sku;
  disabled: boolean;
  onClick: () => void;
}) {
  const innerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const rectRef = useRef<DOMRect | null>(null);

  const onPointerEnter = (e: React.PointerEvent<HTMLButtonElement>) => {
    rectRef.current = e.currentTarget.getBoundingClientRect();
  };

  const onPointerMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    const el = innerRef.current;
    const img = imgRef.current;
    const rect = rectRef.current;
    if (!el || !rect) return;
    const x = (e.clientX - rect.left) / rect.width; // 0..1
    const y = (e.clientY - rect.top) / rect.height; // 0..1
    const tiltY = (x - 0.5) * 12; // left/right rotation
    const tiltX = (0.5 - y) * 12; // up/down rotation
    el.style.transform = `perspective(900px) rotateX(${tiltX}deg) rotateY(${tiltY}deg) scale(1.02)`;
    el.style.setProperty("--glare-x", `${x * 100}%`);
    el.style.setProperty("--glare-y", `${y * 100}%`);
    // Image is a sibling of the rotating card, so it never inherits the
    // tilt. It only "jumps up" with the same scale + a small lift to
    // sell the floating-above-the-card illusion.
    if (img) {
      img.style.transform = "translateY(-5px) scale(1.04)";
    }
  };

  const onPointerLeave = () => {
    const el = innerRef.current;
    const img = imgRef.current;
    if (el)
      el.style.transform =
        "perspective(900px) rotateX(0deg) rotateY(0deg) scale(1)";
    if (img) img.style.transform = "translateY(0) scale(1)";
    rectRef.current = null;
  };

  return (
    <button
      type="button"
      onClick={onClick}
      onPointerEnter={onPointerEnter}
      onPointerMove={onPointerMove}
      onPointerLeave={onPointerLeave}
      disabled={disabled}
      className="group text-left disabled:opacity-50 relative"
      style={{ perspective: "900px" }}
    >
      <div
        ref={innerRef}
        className="rounded-2xl border bg-background shadow-md hover:shadow-2xl p-3 transition-[box-shadow,transform] duration-200 ease-out will-change-transform"
        style={{
          transform: "perspective(900px) rotateX(0deg) rotateY(0deg) scale(1)",
          transformStyle: "preserve-3d",
        }}
      >
        <div
          className="relative aspect-square rounded-xl overflow-hidden mb-3"
          style={{
            backgroundImage:
              "linear-gradient(135deg, #211955 0%, #0E063E 100%)",
          }}
        >
          <RepeatedTextBg />
          <span className="absolute top-2 right-2 inline-flex items-center rounded-full bg-white/90 text-[#211955] text-[10px] font-semibold px-2 py-0.5 z-10">
            {sku.fuseCount} × FUSE
          </span>
          {/* Glare highlight tracking the cursor. Pointer-events-none so
              it never blocks the underlying button. */}
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-200"
            style={{
              background:
                "radial-gradient(circle at var(--glare-x,50%) var(--glare-y,50%), rgba(255,255,255,0.05), transparent 100%)",
            }}
          />
        </div>
        <div className="flex items-end justify-between px-1">
          <div>
            <div className="text-lg font-bold text-primary">
              {formatPrice(sku.basePrice)}
            </div>
            <div className="text-xs text-muted-foreground">{sku.tagline}</div>
          </div>
          <div className="flex items-center gap-1 text-sm text-muted-foreground">
            <Star size={16} className="fill-amber-400 text-amber-400" />
            <span className="tabular-nums">4,7</span>
          </div>
        </div>
      </div>
      {/* Phone image — sibling of the rotating card so it never inherits
          the tilt. It mirrors the image-well box (inner has p-3, image
          well is aspect-square at the top), and on hover takes only the
          shared scale + a small Y-lift to read as "floating above" the
          tilting card. */}
      <img
        ref={imgRef}
        src="/ProductCardImages/ProductCardOriginal.png"
        alt={sku.name}
        aria-hidden
        className="pointer-events-none absolute top-3 left-3 right-3 aspect-square object-contain will-change-transform transition-transform duration-200 ease-out drop-shadow-xl"
        style={{ transform: "translateY(0) scale(1)" }}
      />
    </button>
  );
}

// Repeating "AAU MOBILE PHONE" wordmark behind the product image. The
// text is colored #211955 — slightly darker than the gradient — so it
// reads as a watermark rather than a label.
function RepeatedTextBg() {
  const rows = Array.from({ length: 14 });
  return (
    <div
      aria-hidden
      className="absolute inset-0 overflow-hidden select-none pointer-events-none text-primary"
      style={{ color: "text-primary" }}
    >
      {rows.map((_, i) => (
        <div
          key={i}
          className="text-[22px] md:text-[26px] font-extrabold uppercase whitespace-nowrap leading-[1.1] tracking-tight"
          style={{ transform: `translateX(${(i % 2) * -32}px)` }}
        >
          AAU MOBILE PHONE AAU MOBILE PHONE AAU MOBILE PHONE
        </div>
      ))}
    </div>
  );
}

/* ── Product customisation panel ────────────────────────────────────── */

function ProductPanel({
  sku,
  components,
  cart,
  onClose,
  onAdd,
}: {
  sku: Sku;
  components: ComponentWithInventory[];
  cart: CartItem[];
  onClose: () => void;
  onAdd: (item: CartItem) => void;
}) {
  // Component buckets — case-insensitive match against the inventory's
  // `category` column.
  const byCat = useMemo(() => {
    const m = new Map<string, ComponentWithInventory[]>();
    for (const c of components) {
      const k = c.category.toLowerCase().replace(/\s+/g, "");
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(c);
    }
    return m;
  }, [components]);
  const bottomCovers = byCat.get("bottomcover") ?? [];
  const topCovers = byCat.get("topcover") ?? [];
  const fuses = byCat.get("fuse") ?? [];
  const pcbs = byCat.get("pcb") ?? [];

  // The user picks colour + material independently for each cover, so
  // we surface the union of values from each pool — and disable a swatch
  // when no matching SKU exists for the current material.
  const bottomMaterials = uniqueSorted(bottomCovers.map((c) => c.material));
  const topMaterials = uniqueSorted(topCovers.map((c) => c.material));
  const bottomColors = uniqueSorted(bottomCovers.map((c) => c.color));
  const topColors = uniqueSorted(topCovers.map((c) => c.color));

  const [bottomMaterial, setBottomMaterial] = useState(
    bottomMaterials[0] ?? "",
  );
  const [bottomColor, setBottomColor] = useState(bottomColors[0] ?? "");
  const [topMaterial, setTopMaterial] = useState(topMaterials[0] ?? "");
  const [topColor, setTopColor] = useState(topColors[0] ?? "");
  const [quantity, setQuantity] = useState(1);

  // Seed defaults once data lands.
  useEffect(() => {
    if (!bottomMaterial && bottomMaterials.length)
      setBottomMaterial(bottomMaterials[0]);
    if (!bottomColor && bottomColors.length) setBottomColor(bottomColors[0]);
    if (!topMaterial && topMaterials.length) setTopMaterial(topMaterials[0]);
    if (!topColor && topColors.length) setTopColor(topColors[0]);
  }, [
    bottomMaterial,
    bottomMaterials,
    bottomColor,
    bottomColors,
    topMaterial,
    topMaterials,
    topColor,
    topColors,
  ]);

  const pickByMaterialColor = (
    pool: ComponentWithInventory[],
    mat: string,
    col: string,
  ): ComponentWithInventory | null =>
    pool.find(
      (c) =>
        (c.material ?? "").toLowerCase() === mat.toLowerCase() &&
        (c.color ?? "").toLowerCase() === col.toLowerCase(),
    ) ?? null;

  const bottom = pickByMaterialColor(bottomCovers, bottomMaterial, bottomColor);
  const top = pickByMaterialColor(topCovers, topMaterial, topColor);
  const fuse = fuses[0] ?? null;
  const pcb = pcbs[0] ?? null;

  // Per-material availability: highlight colors that exist in the current
  // material, but allow the swatch to be picked anyway so the user can
  // explore. The stock message reflects the actual selected combination.
  const colorAvailableFor = (
    pool: ComponentWithInventory[],
    mat: string,
    col: string,
  ) =>
    !!pool.find(
      (c) =>
        (c.material ?? "").toLowerCase() === mat.toLowerCase() &&
        (c.color ?? "").toLowerCase() === col.toLowerCase() &&
        c.quantityAvailable > 0,
    );

  const hasParts = !!bottom && !!top && !!fuse && !!pcb;

  // Maximum quantity we can still add. Reservation excludes nothing —
  // an exact match already in the cart counts against the available
  // pool, so re-opening the same configuration shows the remaining
  // headroom (zero if the cart already holds the last unit).
  const maxAddable = hasParts
    ? kitsAvailable(
        {
          bottomCoverId: bottom!.id,
          topCoverId: top!.id,
          pcbId: pcb!.id,
          fuseId: fuse!.id,
          fuseCount: sku.fuseCount,
        },
        components,
        cart,
      )
    : 0;

  // Re-clamp the chosen quantity whenever the selection (and therefore
  // maxAddable) changes — otherwise switching from a high-stock config
  // to a low-stock one would leave the spinner above the cap.
  useEffect(() => {
    if (quantity > maxAddable) setQuantity(Math.max(1, maxAddable));
  }, [maxAddable, quantity]);

  const canAdd = hasParts && maxAddable >= quantity && quantity > 0;

  const stockMessage = !hasParts
    ? "This combination isn't currently in stock"
    : maxAddable === 0
      ? "No more of this configuration available — adjust your selection or remove from cart"
      : `${maxAddable} matching kit${maxAddable === 1 ? "" : "s"} available`;

  const submit = () => {
    if (!canAdd) return;
    onAdd({
      id: makeCartId(),
      skuId: sku.id,
      fuseCount: sku.fuseCount,
      bottomColor,
      bottomMaterial,
      topColor,
      topMaterial,
      quantity,
      bottomCoverId: bottom!.id,
      topCoverId: top!.id,
      fuseId: fuse!.id,
      pcbId: pcb!.id,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40">
      <div className="bg-background rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto">
        <header className="flex items-center justify-between p-4 border-b sticky top-0 bg-background">
          <div>
            <h2 className="font-bold text-primary uppercase">Customise</h2>
            <p className="text-xs text-muted-foreground">
              {sku.tagline} · {sku.fuseCount} × Fuse
            </p>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-muted rounded-md">
            <X size={18} />
          </button>
        </header>
        <div className="grid md:grid-cols-2">
          <div className="relative aspect-square bg-muted">
            <PhoneConfigurator
              topColor={topColor || "Black"}
              bottomColor={bottomColor || "Black"}
              fuseCount={sku.fuseCount}
              className="absolute inset-0 w-full h-full object-contain"
            />
          </div>
          <div className="p-5 space-y-5">
            <div className="flex items-baseline justify-between">
              <div>
                <div className="text-xl font-bold text-primary">{sku.name}</div>
                <div className="text-xs text-muted-foreground">
                  {sku.tagline}
                </div>
              </div>
              <div className="text-lg font-bold text-primary">
                {formatPrice(sku.basePrice)}
              </div>
            </div>

            <CoverSection
              label="Top Cover"
              colors={topColors}
              materials={topMaterials}
              color={topColor}
              material={topMaterial}
              onColor={setTopColor}
              onMaterial={setTopMaterial}
              colorAvailable={(col) =>
                colorAvailableFor(topCovers, topMaterial, col)
              }
            />

            <CoverSection
              label="Bottom Cover"
              colors={bottomColors}
              materials={bottomMaterials}
              color={bottomColor}
              material={bottomMaterial}
              onColor={setBottomColor}
              onMaterial={setBottomMaterial}
              colorAvailable={(col) =>
                colorAvailableFor(bottomCovers, bottomMaterial, col)
              }
            />

            <div className="text-xs text-muted-foreground">{stockMessage}</div>

            <Section title="Quantity">
              <div className="inline-flex items-center gap-2">
                <button
                  onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                  disabled={quantity <= 1}
                  className="p-1 rounded-md border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Minus size={14} />
                </button>
                <span className="w-8 text-center text-sm tabular-nums">
                  {quantity}
                </span>
                <button
                  onClick={() =>
                    setQuantity((q) => Math.min(maxAddable, q + 1))
                  }
                  disabled={quantity >= maxAddable}
                  className="p-1 rounded-md border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Plus size={14} />
                </button>
              </div>
            </Section>

            <button
              onClick={submit}
              disabled={!canAdd}
              className="w-full py-3 rounded-full bg-primary text-background font-bold uppercase tracking-wider disabled:opacity-50"
            >
              {maxAddable === 0
                ? "Out of stock"
                : `Add to cart · ${formatPrice(sku.basePrice * quantity)}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function CoverSection({
  label,
  colors,
  materials,
  color,
  material,
  onColor,
  onMaterial,
  colorAvailable,
}: {
  label: string;
  colors: string[];
  materials: string[];
  color: string;
  material: string;
  onColor: (c: string) => void;
  onMaterial: (m: string) => void;
  colorAvailable: (color: string) => boolean;
}) {
  return (
    <div className="space-y-2">
      <div className="text-sm font-semibold text-primary">{label}</div>
      <div>
        <div className="text-[10px] uppercase text-muted-foreground mb-1">
          Color
        </div>
        <div className="flex gap-2 flex-wrap">
          {colors.map((c) => {
            const active = c === color;
            const inStock = colorAvailable(c);
            return (
              <button
                key={c}
                onClick={() => onColor(c)}
                title={`${c}${inStock ? "" : " (out of stock)"}`}
                className={`w-7 h-7 rounded-full border-2 ${
                  active ? "border-amber-500" : "border-transparent"
                } ${inStock ? "" : "opacity-40"}`}
                style={{ backgroundColor: COLOR_HEX[c] ?? "#888" }}
              />
            );
          })}
        </div>
      </div>
      <div>
        <div className="text-[10px] uppercase text-muted-foreground mb-1">
          Material
        </div>
        <div className="flex gap-2 flex-wrap">
          {materials.map((m) => {
            const active = m === material;
            return (
              <button
                key={m}
                onClick={() => onMaterial(m)}
                className={`px-3 py-1 rounded-full text-xs font-semibold ${
                  active
                    ? "bg-primary text-background"
                    : "bg-muted text-muted-foreground hover:bg-muted/70"
                }`}
              >
                {m}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-sm font-semibold text-primary mb-2">{title}</div>
      {children}
    </div>
  );
}

function uniqueSorted(arr: (string | undefined)[]): string[] {
  const set = new Set<string>();
  for (const v of arr) if (v) set.add(v);
  return Array.from(set).sort();
}

/* ── Cart panel ─────────────────────────────────────────────────────── */

function CartPanel({
  items,
  components,
  total,
  ordering,
  onClose,
  onUpdateQty,
  onRemove,
  onPlaceOrder,
}: {
  items: CartItem[];
  components: ComponentWithInventory[];
  total: number;
  ordering: boolean;
  onClose: () => void;
  onUpdateQty: (id: string, delta: number) => void;
  onRemove: (id: string) => void;
  onPlaceOrder: () => void;
}) {
  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} />
      <aside className="fixed top-0 right-0 h-full w-full max-w-md bg-background z-50 shadow-2xl flex flex-col">
        <header className="flex items-center justify-between p-4 border-b">
          <h2 className="font-bold text-primary uppercase">Your Cart</h2>
          <button onClick={onClose} className="p-1 hover:bg-muted rounded-md">
            <X size={18} />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {items.length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-8">
              Cart is empty.
            </div>
          ) : (
            items.map((it) => {
              const sku = skuById(it.skuId);
              // Headroom for this row: total available minus what every
              // OTHER cart row already reserves for the same components.
              // The row's own quantity is excluded so the user can still
              // see and decrement what they already added.
              const headroom = kitsAvailable(
                {
                  bottomCoverId: it.bottomCoverId,
                  topCoverId: it.topCoverId,
                  pcbId: it.pcbId,
                  fuseId: it.fuseId,
                  fuseCount: it.fuseCount,
                },
                components,
                items,
                it.id,
              );
              const canIncrement = it.quantity < headroom;
              return (
                <div
                  key={it.id}
                  className="flex gap-3 rounded-xl border p-3 bg-muted/30"
                >
                  <div
                    className="w-14 h-20 shrink-0 rounded-md overflow-hidden flex items-center justify-center"
                    style={{
                      backgroundImage:
                        "linear-gradient(135deg, #211955 0%, #0E063E 100%)",
                    }}
                  >
                    <img
                      src="/ProductCardImages/ProductCardOriginal.png"
                      alt={sku.name}
                      className="w-full h-full object-contain"
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-primary">
                      {sku.name}
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      {sku.tagline} · {it.fuseCount}×Fuse
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-1">
                      Top: {it.topColor} / {it.topMaterial} · Bottom:{" "}
                      {it.bottomColor} / {it.bottomMaterial}
                    </div>
                    <div className="mt-2 flex items-center justify-between">
                      <div className="inline-flex items-center gap-1">
                        <button
                          onClick={() => onUpdateQty(it.id, -1)}
                          className="p-1 rounded-md border hover:bg-muted"
                        >
                          <Minus size={12} />
                        </button>
                        <span className="w-6 text-center text-xs tabular-nums">
                          {it.quantity}
                        </span>
                        <button
                          onClick={() => onUpdateQty(it.id, +1)}
                          disabled={!canIncrement}
                          title={
                            canIncrement
                              ? undefined
                              : "No more of this configuration in stock"
                          }
                          className="p-1 rounded-md border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          <Plus size={12} />
                        </button>
                      </div>
                      <div className="text-sm font-semibold tabular-nums">
                        {formatPrice(sku.basePrice * it.quantity)}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => onRemove(it.id)}
                    className="self-start text-xs text-muted-foreground hover:text-red-600"
                    title="Remove"
                  >
                    <X size={14} />
                  </button>
                </div>
              );
            })
          )}
        </div>
        <footer className="border-t p-4 space-y-3">
          <div className="flex items-baseline justify-between text-sm">
            <span className="text-muted-foreground">Total</span>
            <span className="text-lg font-bold text-primary">
              {formatPrice(total)}
            </span>
          </div>
          <button
            onClick={onPlaceOrder}
            disabled={items.length === 0 || ordering}
            className="w-full py-3 rounded-full bg-primary text-background font-bold uppercase tracking-wider disabled:opacity-50"
          >
            {ordering ? "Placing order…" : "Place Order"}
          </button>
        </footer>
      </aside>
    </>
  );
}

