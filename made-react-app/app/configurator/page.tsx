"use client";

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";

const selectClass =
  "border border-border rounded px-2 py-1 w-full bg-muted text-foreground hover:bg-accent focus:bg-accent disabled:opacity-40 disabled:cursor-not-allowed";

type Combo = { material: string; color: string; finish: string; qty: number };

export default function ConfiguratorPage() {
  const router = useRouter();
  const [options, setOptions] = useState<any>(null);

  const [config, setConfig] = useState({
    Bottom_Cover: { material: "", color: "", finish: "" },
    Top_Cover:    { material: "", color: "", finish: "" },
    number_of_fuses: 1,
  });

  type OrderResult = { order_id: string; created_date: string; model_numbers_needed: Record<string, string> };
  const [submitting, setSubmitting] = useState(false);
  const [orderResult, setOrderResult] = useState<OrderResult | null>(null);
  const [orderError, setOrderError] = useState<string | null>(null);

  const configComplete =
    !!config.Bottom_Cover.material && !!config.Bottom_Cover.color && !!config.Bottom_Cover.finish &&
    !!config.Top_Cover.material   && !!config.Top_Cover.color   && !!config.Top_Cover.finish;

  const placeOrder = async () => {
    setSubmitting(true);
    setOrderResult(null);
    setOrderError(null);
    try {
      const res = await fetch("/api/configurator/order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      const data = await res.json();
      if (!res.ok) {
        setOrderError(data.error ?? "Order failed");
      } else {
        setOrderResult(data);
        // Reset dropdowns after successful order
        setConfig({
          Bottom_Cover: { material: "", color: "", finish: "" },
          Top_Cover:    { material: "", color: "", finish: "" },
          number_of_fuses: 1,
        });
      }
    } catch {
      setOrderError("Could not reach the configurator API. Is the Flask server running?");
    } finally {
      setSubmitting(false);
    }
  };

  useEffect(() => {
    fetch("/api/configurator/options")
      .then((res) => res.json())
      .then(setOptions);
  }, []);

  // ── Bottom Cover cascading options (any-order filtering) ─────────────────
  const bcCombos: Combo[] = useMemo(
    () => options?.bottom_cover_combos ?? [],
    [options]
  );
  const bcMaterials = useMemo(() => {
    const base = bcCombos.filter(
      (c) =>
        (!config.Bottom_Cover.color  || c.color  === config.Bottom_Cover.color) &&
        (!config.Bottom_Cover.finish || c.finish === config.Bottom_Cover.finish)
    );
    return [...new Set(base.map((c) => c.material))];
  }, [bcCombos, config.Bottom_Cover.color, config.Bottom_Cover.finish]);
  const bcColors = useMemo(() => {
    const base = bcCombos.filter(
      (c) =>
        (!config.Bottom_Cover.material || c.material === config.Bottom_Cover.material) &&
        (!config.Bottom_Cover.finish   || c.finish   === config.Bottom_Cover.finish)
    );
    return [...new Set(base.map((c) => c.color))];
  }, [bcCombos, config.Bottom_Cover.material, config.Bottom_Cover.finish]);
  const bcFinishes = useMemo(() => {
    const base = bcCombos.filter(
      (c) =>
        (!config.Bottom_Cover.material || c.material === config.Bottom_Cover.material) &&
        (!config.Bottom_Cover.color    || c.color    === config.Bottom_Cover.color)
    );
    return [...new Set(base.map((c) => c.finish))];
  }, [bcCombos, config.Bottom_Cover.material, config.Bottom_Cover.color]);

  // ── Top Cover cascading options (any-order filtering) ───────────────────
  const tcCombos: Combo[] = useMemo(
    () => options?.top_cover_combos ?? [],
    [options]
  );
  const tcMaterials = useMemo(() => {
    const base = tcCombos.filter(
      (c) =>
        (!config.Top_Cover.color  || c.color  === config.Top_Cover.color) &&
        (!config.Top_Cover.finish || c.finish === config.Top_Cover.finish)
    );
    return [...new Set(base.map((c) => c.material))];
  }, [tcCombos, config.Top_Cover.color, config.Top_Cover.finish]);
  const tcColors = useMemo(() => {
    const base = tcCombos.filter(
      (c) =>
        (!config.Top_Cover.material || c.material === config.Top_Cover.material) &&
        (!config.Top_Cover.finish   || c.finish   === config.Top_Cover.finish)
    );
    return [...new Set(base.map((c) => c.color))];
  }, [tcCombos, config.Top_Cover.material, config.Top_Cover.finish]);
  const tcFinishes = useMemo(() => {
    const base = tcCombos.filter(
      (c) =>
        (!config.Top_Cover.material || c.material === config.Top_Cover.material) &&
        (!config.Top_Cover.color    || c.color    === config.Top_Cover.color)
    );
    return [...new Set(base.map((c) => c.finish))];
  }, [tcCombos, config.Top_Cover.material, config.Top_Cover.color]);

  // ── Smart field change: clear other fields only when pairwise incompatible ─
  const handleBcChange = (
    field: "material" | "color" | "finish",
    value: string
  ) => {
    const next = { ...config, Bottom_Cover: { ...config.Bottom_Cover, [field]: value } };
    (["material", "color", "finish"] as const)
      .filter((f) => f !== field)
      .forEach((f) => {
        const otherVal = next.Bottom_Cover[f];
        if (!otherVal) return;
        const ok = bcCombos.some((c) => c[field] === value && c[f] === otherVal);
        if (!ok) next.Bottom_Cover = { ...next.Bottom_Cover, [f]: "" };
      });
    setConfig(next);
  };

  const handleTcChange = (
    field: "material" | "color" | "finish",
    value: string
  ) => {
    const next = { ...config, Top_Cover: { ...config.Top_Cover, [field]: value } };
    (["material", "color", "finish"] as const)
      .filter((f) => f !== field)
      .forEach((f) => {
        const otherVal = next.Top_Cover[f];
        if (!otherVal) return;
        const ok = tcCombos.some((c) => c[field] === value && c[f] === otherVal);
        if (!ok) next.Top_Cover = { ...next.Top_Cover, [f]: "" };
      });
    setConfig(next);
  };

  if (!options) return <div>Loading options...</div>;

  const smoothFinishes = ["Matte", "Glossy"];
  const texturedFinishes = ["Textured"];

  const renderFinishOptions = (finishes: string[]) => (
    <>
      {smoothFinishes.some((f) => finishes.includes(f)) && (
        <optgroup label="Smooth">
          {smoothFinishes.filter((f) => finishes.includes(f)).map((f) => (
            <option key={f} value={f}>{f}</option>
          ))}
        </optgroup>
      )}
      {texturedFinishes.some((f) => finishes.includes(f)) && (
        <optgroup label="Textured">
          {texturedFinishes.filter((f) => finishes.includes(f)).map((f) => (
            <option key={f} value={f}>{f}</option>
          ))}
        </optgroup>
      )}
    </>
  );

  return (
    <div className="max-w-xl mx-auto p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Telefon Configurator</h1>
        <button
          className="bg-muted text-muted-foreground px-4 py-2 rounded hover:bg-accent"
          onClick={() => router.push("/configurator/Inventory")}
          type="button"
        >
          View Inventory
        </button>
      </div>

      {/* Bottom Cover */}
      <div className="space-y-2 border border-border bg-card p-4 rounded">
        <h2 className="font-semibold text-foreground">Bottom Cover</h2>

        <select
          className={selectClass}
          value={config.Bottom_Cover.material}
          onChange={(e) => handleBcChange("material", e.target.value)}
        >
          <option value="" disabled hidden>Select Material</option>
          {bcMaterials.map((m) => <option key={m}>{m}</option>)}
        </select>

        <select
          className={selectClass}
          value={config.Bottom_Cover.color}
          onChange={(e) => handleBcChange("color", e.target.value)}
        >
          <option value="" disabled hidden>Select Color</option>
          {bcColors.map((c) => <option key={c}>{c}</option>)}
        </select>

        <select
          className={selectClass}
          value={config.Bottom_Cover.finish}
          onChange={(e) => handleBcChange("finish", e.target.value)}
        >
          <option value="" disabled hidden>Select Finish</option>
          {renderFinishOptions(bcFinishes)}
        </select>
      </div>

      {/* Top Cover */}
      <div className="space-y-2 border border-border bg-card p-4 rounded">
        <h2 className="font-semibold text-foreground">Top Cover</h2>

        <select
          className={selectClass}
          value={config.Top_Cover.material}
          onChange={(e) => handleTcChange("material", e.target.value)}
        >
          <option value="" disabled hidden>Select Material</option>
          {tcMaterials.map((m) => <option key={m}>{m}</option>)}
        </select>

        <select
          className={selectClass}
          value={config.Top_Cover.color}
          onChange={(e) => handleTcChange("color", e.target.value)}
        >
          <option value="" disabled hidden>Select Color</option>
          {tcColors.map((c) => <option key={c}>{c}</option>)}
        </select>

        <select
          className={selectClass}
          value={config.Top_Cover.finish}
          onChange={(e) => handleTcChange("finish", e.target.value)}
        >
          <option value="" disabled hidden>Select Finish</option>
          {renderFinishOptions(tcFinishes)}
        </select>
      </div>

      {/* Fuse */}
      <div className="border border-border bg-card p-4 rounded">
        <h2 className="font-semibold text-foreground">Fuse</h2>
        <select
          className={selectClass}
          value={config.number_of_fuses}
          onChange={(e) =>
            setConfig({ ...config, number_of_fuses: Number(e.target.value) })
          }
        >
          {options.fuse_counts && Object.keys(options.fuse_counts)
            .filter((n) => Number(n) <= 3)
            .map((n) => (
              <option key={n} value={n}>
                {n} {Number(n) === 1 ? "Fuse" : "Fuses"}
              </option>
            ))}
        </select>
      </div>

      {/* Order result banner */}
      {orderResult && (
        <div className="border border-teal-400/30 bg-teal-400/10 rounded p-4 space-y-2">
          <p className="font-semibold text-teal-400">✅ Order placed — {orderResult.order_id}</p>
          <p className="text-xs text-foreground">{orderResult.created_date}</p>
          <ul className="text-sm space-y-0.5">
            {Object.entries(orderResult.model_numbers_needed ?? {}).map(([k, v]) => (
              <li key={k} className="flex justify-between">
                <span className="text-foreground">{k}</span>
                <span className="font-medium text-foreground">{v}</span>
              </li>
            ))}
          </ul>
          <button
            className="text-xs underline text-blue-200 mt-1"
            onClick={() => router.push("/configurator/Orders")}
            type="button"
          >
            View all orders →
          </button>
        </div>
      )}

      {orderError && (
        <div className="border border-red-500/30 bg-red-500/10 rounded p-3 text-sm text-red-500">
          ❌ {orderError}
        </div>
      )}

      <div className="flex justify-between">
        <button
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
          type="button"
          disabled={!configComplete || submitting}
          onClick={placeOrder}
        >
          {submitting ? "Placing order…" : "Place Order"}
        </button>

        <div className="flex gap-2">
          <button
            className="bg-primary text-primary-foreground px-4 py-2 rounded hover:bg-accent"
            onClick={() => router.push("/configurator/Orders")}
            type="button"
          >
            Orders
          </button>
          <button
            className="bg-primary text-primary-foreground px-4 py-2 rounded hover:bg-accent"
            onClick={() => router.push("/configurator/Inventory")}
            type="button"
          >
            View Inventory
          </button>
          <button
            className="bg-primary text-primary-foreground px-4 py-2 rounded hover:bg-accent"
            onClick={() => router.push("/configurator/Released")}
            type="button"
          >
            Released
          </button>
        </div>
      </div>
    </div>
  );
}