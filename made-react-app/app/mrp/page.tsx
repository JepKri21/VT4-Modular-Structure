"use client";

import { useEffect, useState } from "react";
import InventoryTab from "./InventoryTab";
import BomTab from "./BomTab";
import PlanningTab from "./PlanningTab";
import PurchaseOrdersTab from "./PurchaseOrdersTab";

const TABS = [
  { id: "inventory", label: "Inventory" },
  { id: "bom", label: "BOM" },
  { id: "planning", label: "Planning" },
  { id: "purchase_orders", label: "Purchase Orders" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function MrpPage() {
  // Persist the active tab across reloads so a deep-link feel emerges
  // without proper routing.
  const [tab, setTab] = useState<TabId>("inventory");
  useEffect(() => {
    const saved = localStorage.getItem("mrp_tab") as TabId | null;
    if (saved && TABS.some((t) => t.id === saved)) setTab(saved);
  }, []);
  useEffect(() => {
    localStorage.setItem("mrp_tab", tab);
  }, [tab]);

  return (
    <div className="p-6 space-y-4">
      <header className="flex flex-wrap items-baseline gap-4">
        <h1 className="text-2xl font-bold uppercase">MRP</h1>
        <span className="text-sm text-muted-foreground">
          Material Requirements Planning
        </span>
      </header>

      <nav className="flex border-b">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
              tab === t.id
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {tab === "inventory" && <InventoryTab />}
      {tab === "bom" && <BomTab />}
      {tab === "planning" && <PlanningTab />}
      {tab === "purchase_orders" && <PurchaseOrdersTab />}
    </div>
  );
}
