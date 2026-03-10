"use client";

import { useEffect, useState } from "react";

type InventoryItem = {
  model_number: string;
  component_type: string;
  material: string;
  color: string;
  qty_available: number;
};

const Configurator = () => {
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/configurator")
      .then((res) => res.json())
      .then((data) => {
        setInventory(data);
        setLoading(false);
      })
      .catch(() => setInventory([]));
  }, []);

  const grouped = Array.isArray(inventory)
    ? inventory.reduce((acc, item) => {
        acc[item.component_type] = acc[item.component_type] || [];
        acc[item.component_type].push(item);
        return acc;
      }, {} as Record<string, InventoryItem[]>)
    : {};

  const qtyColor = (qty: number) => {
    if (qty === 0) return "text-red-500";
    if (qty < 10) return "text-yellow-500";
    return "text-green-600";
  };

  return (
    <div className="max-w-7xl mx-auto px-8 py-10 space-y-12">
      <h2 className="text-3xl font-bold tracking-tight">Inventory</h2>

      {loading ? (
        <div className="text-gray-500">Loading inventory...</div>
      ) : (
        Object.entries(grouped).map(([type, items]) => (
          <section key={type} className="space-y-6">
            <h3 className="text-xl font-semibold border-b pb-2">{type}</h3>

            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {items.map((item) => (
                <div
                  key={item.model_number}
                  className="bg-white rounded-xl shadow-sm border p-5 hover:shadow-md transition"
                >
                  <div className="flex justify-between items-start mb-3">
                    <span className="font-mono text-sm text-gray-500">
                      {item.model_number}
                    </span>

                    <span
                      className={`text-sm font-semibold ${qtyColor(
                        item.qty_available
                      )}`}
                    >
                      {item.qty_available}
                    </span>
                  </div>

                  <div className="space-y-1 text-sm">
                    <div>
                      <span className="text-gray-500">Material:</span>{" "}
                      {item.material}
                    </div>

                    <div>
                      <span className="text-gray-500">Color:</span>{" "}
                      {item.color}
                    </div>
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