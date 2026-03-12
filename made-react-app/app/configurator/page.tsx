"use client";

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

const selectClass =
  "border border-border rounded px-2 py-1 w-full bg-muted text-foreground hover:bg-accent focus:bg-accent disabled:opacity-40 disabled:cursor-not-allowed";

type Combo = { material: string; color: string; finish: string; qty: number };

export default function ConfiguratorPage() {
  const router = useRouter();
  const [options, setOptions] = useState<any>(null);

  const [config, setConfig] = useState({
    bottom_cover_material: "",
    bottom_cover_color: "",
    bottom_cover_finish: "",
    top_cover_material: "",
    top_cover_color: "",
    top_cover_finish: "",
    number_of_fuses: 1,
  });

  type OrderResult = {
    order_id: string;
    created_date: string;
    model_numbers_needed: Record<string, string>;
  };
  const [submitting, setSubmitting] = useState(false);
  const [orderResult, setOrderResult] = useState<OrderResult | null>(null);
  const [orderError, setOrderError] = useState<string | null>(null);

  const configComplete =
    !!config.bottom_cover_material &&
    !!config.bottom_cover_color &&
    !!config.bottom_cover_finish &&
    !!config.top_cover_material &&
    !!config.top_cover_color &&
    !!config.top_cover_finish;

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
          bottom_cover_material: "",
          bottom_cover_color: "",
          bottom_cover_finish: "",
          top_cover_material: "",
          top_cover_color: "",
          top_cover_finish: "",
          number_of_fuses: 1,
        });
      }
    } catch {
      setOrderError(
        "Could not reach the configurator API. Is the Flask server running?",
      );
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
    [options],
  );
  const bcMaterials = useMemo(() => {
    const base = bcCombos.filter(
      (c) =>
        (!config.bottom_cover_color || c.color === config.bottom_cover_color) &&
        (!config.bottom_cover_finish ||
          c.finish === config.bottom_cover_finish),
    );
    return [...new Set(base.map((c) => c.material))];
  }, [bcCombos, config.bottom_cover_color, config.bottom_cover_finish]);
  const bcColors = useMemo(() => {
    const base = bcCombos.filter(
      (c) =>
        (!config.bottom_cover_material ||
          c.material === config.bottom_cover_material) &&
        (!config.bottom_cover_finish ||
          c.finish === config.bottom_cover_finish),
    );
    return [...new Set(base.map((c) => c.color))];
  }, [bcCombos, config.bottom_cover_material, config.bottom_cover_finish]);
  const bcFinishes = useMemo(() => {
    const base = bcCombos.filter(
      (c) =>
        (!config.bottom_cover_material ||
          c.material === config.bottom_cover_material) &&
        (!config.bottom_cover_color || c.color === config.bottom_cover_color),
    );
    return [...new Set(base.map((c) => c.finish))];
  }, [bcCombos, config.bottom_cover_material, config.bottom_cover_color]);

  // ── Top Cover cascading options (any-order filtering) ───────────────────
  const tcCombos: Combo[] = useMemo(
    () => options?.top_cover_combos ?? [],
    [options],
  );
  const tcMaterials = useMemo(() => {
    const base = tcCombos.filter(
      (c) =>
        (!config.top_cover_color || c.color === config.top_cover_color) &&
        (!config.top_cover_finish || c.finish === config.top_cover_finish),
    );
    return [...new Set(base.map((c) => c.material))];
  }, [tcCombos, config.top_cover_color, config.top_cover_finish]);
  const tcColors = useMemo(() => {
    const base = tcCombos.filter(
      (c) =>
        (!config.top_cover_material ||
          c.material === config.top_cover_material) &&
        (!config.top_cover_finish || c.finish === config.top_cover_finish),
    );
    return [...new Set(base.map((c) => c.color))];
  }, [tcCombos, config.top_cover_material, config.top_cover_finish]);
  const tcFinishes = useMemo(() => {
    const base = tcCombos.filter(
      (c) =>
        (!config.top_cover_material ||
          c.material === config.top_cover_material) &&
        (!config.top_cover_color || c.color === config.top_cover_color),
    );
    return [...new Set(base.map((c) => c.finish))];
  }, [tcCombos, config.top_cover_material, config.top_cover_color]);

  // ── Smart field change: clear other fields only when pairwise incompatible ─
  const handleBcChange = (
    field:
      | "bottom_cover_material"
      | "bottom_cover_color"
      | "bottom_cover_finish",
    value: string,
  ) => {
    const keyMap = {
      bottom_cover_material: "material",
      bottom_cover_color: "color",
      bottom_cover_finish: "finish",
    } as const;
    const next = { ...config, [field]: value };
    const changedKey = keyMap[field];
    // For each OTHER selected field: clear only if no combo pairs it with the new value.
    // This is order-independent — your first choice is always respected.
    (
      [
        "bottom_cover_material",
        "bottom_cover_color",
        "bottom_cover_finish",
      ] as const
    )
      .filter((f) => f !== field)
      .forEach((f) => {
        const otherVal = next[f];
        if (!otherVal) return;
        const otherKey = keyMap[f];
        const ok = bcCombos.some(
          (c) => c[changedKey] === value && c[otherKey] === otherVal,
        );
        if (!ok) next[f] = "";
      });
    setConfig(next);
  };

  const handleTcChange = (
    field: "top_cover_material" | "top_cover_color" | "top_cover_finish",
    value: string,
  ) => {
    const keyMap = {
      top_cover_material: "material",
      top_cover_color: "color",
      top_cover_finish: "finish",
    } as const;
    const next = { ...config, [field]: value };
    const changedKey = keyMap[field];
    (["top_cover_material", "top_cover_color", "top_cover_finish"] as const)
      .filter((f) => f !== field)
      .forEach((f) => {
        const otherVal = next[f];
        if (!otherVal) return;
        const otherKey = keyMap[f];
        const ok = tcCombos.some(
          (c) => c[changedKey] === value && c[otherKey] === otherVal,
        );
        if (!ok) next[f] = "";
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
          {smoothFinishes
            .filter((f) => finishes.includes(f))
            .map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
        </optgroup>
      )}
      {texturedFinishes.some((f) => finishes.includes(f)) && (
        <optgroup label="Textured">
          {texturedFinishes
            .filter((f) => finishes.includes(f))
            .map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
        </optgroup>
      )}
    </>
  );

  return (
    <Card className="max-w-xl mx-auto bg-muted p-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl text-primary font-bold">
          Telefon Configurator
        </h1>
        <Button
          className="bg-background text-primary px-4 py-1 hover:bg-accent"
          onClick={() => router.push("/configurator/Inventory")}
          type="button"
        >
          View Inventory
        </Button>
      </div>

      {/* Bottom Cover */}
      <Card className="border border-border bg-background p-4">
        <h2 className="font-semibold text-primary">Bottom Cover</h2>
        <select
          className={selectClass}
          value={config.bottom_cover_material}
          onChange={(e) =>
            handleBcChange("bottom_cover_material", e.target.value)
          }
        >
          <option value="" disabled hidden>
            Select Material
          </option>
          {bcMaterials.map((m) => (
            <option key={m}>{m}</option>
          ))}
        </select>

        <select
          className={selectClass}
          value={config.bottom_cover_color}
          onChange={(e) => handleBcChange("bottom_cover_color", e.target.value)}
        >
          <option value="" disabled hidden>
            Select Color
          </option>
          {bcColors.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>

        <select
          className={selectClass}
          value={config.bottom_cover_finish}
          onChange={(e) =>
            handleBcChange("bottom_cover_finish", e.target.value)
          }
        >
          <option value="" disabled hidden>
            Select Finish
          </option>
          {renderFinishOptions(bcFinishes)}
        </select>
      </Card>

      {/* Top Cover */}
      <Card className="space-y-0.1 border border-border bg-background p-4">
        <h2 className="font-semibold text-primary">Top Cover</h2>
        <select
          className={selectClass}
          value={config.top_cover_material}
          onChange={(e) => handleTcChange("top_cover_material", e.target.value)}
        >
          <option value="" disabled hidden>
            Select Material
          </option>
          {tcMaterials.map((m) => (
            <option key={m}>{m}</option>
          ))}
        </select>

        <select
          className={selectClass}
          value={config.top_cover_color}
          onChange={(e) => handleTcChange("top_cover_color", e.target.value)}
        >
          <option value="" disabled hidden>
            Select Color
          </option>
          {tcColors.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>

        <select
          className={selectClass}
          value={config.top_cover_finish}
          onChange={(e) => handleTcChange("top_cover_finish", e.target.value)}
        >
          <option value="" disabled hidden>
            Select Finish
          </option>
          {renderFinishOptions(tcFinishes)}
        </select>
      </Card>

      {/* Fuse */}
      <Card className="border border-border bg-background p-4">
        <h2 className="font-semibold text-primary">Fuse</h2>
        <select
          className={selectClass}
          value={config.number_of_fuses}
          onChange={(e) =>
            setConfig({ ...config, number_of_fuses: Number(e.target.value) })
          }
        >
          {Object.keys(options.fuse_counts)
            .filter((n) => Number(n) <= 3)
            .map((n) => (
              <option key={n} value={n}>
                {n} {Number(n) === 1 ? "Fuse" : "Fuses"}
              </option>
            ))}
        </select>
      </Card>

      {/* Order result banner */}
      {orderResult && (
        <div className="border border-teal-400/30 bg-teal-400/10 rounded p-4 space-y-2">
          <p className="font-semibold text-teal-400">
            ✅ Order placed — {orderResult.order_id}
          </p>
          <p className="text-xs text-foreground">{orderResult.created_date}</p>
          <ul className="text-sm space-y-0.5">
            {Object.entries(orderResult.model_numbers_needed ?? {}).map(
              ([k, v]) => (
                <li key={k} className="flex justify-between">
                  <span className="text-foreground">{k}</span>
                  <span className="font-medium text-foreground">{v}</span>
                </li>
              ),
            )}
          </ul>
          <Button
            className="text-xs underline text-blue-200 mt-1"
            onClick={() => router.push("/configurator/Orders")}
            type="button"
          >
            View all orders →
          </Button>
        </div>
      )}

      {orderError && (
        <div className="border border-red-500/30 bg-red-500/10 rounded p-3 text-sm text-red-500">
          ❌ {orderError}
        </div>
      )}

      <div className="flex justify-between gap-2">
        <button
          className="bg-primary text-background px-4 py-2 rounded hover:bg-card disabled:bg-muted disabled:text-primary/60 disabled:cursor-not-allowed"
          type="button"
          disabled={!configComplete || submitting}
          onClick={placeOrder}
        >
          {submitting ? "Placing order…" : "Place Order"}
        </button>

        <div className="flex gap-2">
          <button
            className="bg-background text-primary px-4 py-2 rounded hover:bg-card"
            onClick={() => router.push("/configurator/Orders")}
            type="button"
          >
            Orders
          </button>
          <button
            className="bg-background text-primary px-4 py-2 rounded hover:bg-card"
            onClick={() => router.push("/configurator/Inventory")}
            type="button"
          >
            View Inventory
          </button>
          <button
            className="bg-background text-primary px-4 py-2 rounded hover:bg-card"
            onClick={() => router.push("/configurator/Released")}
            type="button"
          >
            Released
          </button>
        </div>
      </div>
    </Card>
  );
}
