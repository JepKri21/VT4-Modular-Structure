"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

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

  useEffect(() => {
    fetch("/api/configurator/options")
      .then((res) => res.json())
      .then(setOptions);
  }, []);

  if (!options) return <div>Loading options...</div>;

  return (
    <div className="max-w-xl mx-auto p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Telefon Configurator</h1>
        {/* Inventory Button */}
        <button
          className="bg-gray-700 text-white px-4 py-2 rounded hover:bg-gray-900"
          onClick={() => router.push("/configurator/Inventory")}
          type="button"
        >
          View Inventory
        </button>
      </div>

      {/* Bottom Cover */}
      <div className="space-y-2 border p-4 rounded">
        <h2 className="font-semibold">Bottom Cover</h2>

        <select
          className="border rounded px-2 py-1 w-full"
          value={config.bottom_cover_material}
          onChange={(e) =>
            setConfig({ ...config, bottom_cover_material: e.target.value })
          }
        >
          <option value="">Material</option>
          {Object.keys(options.bottom_cover_materials).map((m) => (
            <option key={m}>{m}</option>
          ))}
        </select>

        <select
          className="border rounded px-2 py-1 w-full"
          value={config.bottom_cover_color}
          onChange={(e) =>
            setConfig({ ...config, bottom_cover_color: e.target.value })
          }
        >
          <option value="">Color</option>
          {Object.keys(options.bottom_cover_colors).map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>

        <select
          className="border rounded px-2 py-1 w-full"
          value={config.bottom_cover_finish}
          onChange={(e) =>
            setConfig({ ...config, bottom_cover_finish: e.target.value })
          }
        >
          <option value="">Finish</option>
          {Object.keys(options.bottom_cover_finishes).map((f) => (
            <option key={f}>{f}</option>
          ))}
        </select>
      </div>

      {/* Top Cover */}
      <div className="space-y-2 border p-4 rounded">
        <h2 className="font-semibold">Top Cover</h2>

        <select
          className="border rounded px-2 py-1 w-full"
          value={config.top_cover_material}
          onChange={(e) =>
            setConfig({ ...config, top_cover_material: e.target.value })
          }
        >
          <option value="">Material</option>
          {Object.keys(options.top_cover_materials).map((m) => (
            <option key={m}>{m}</option>
          ))}
        </select>

        <select
          className="border rounded px-2 py-1 w-full"
          value={config.top_cover_color}
          onChange={(e) =>
            setConfig({ ...config, top_cover_color: e.target.value })
          }
        >
          <option value="">Color</option>
          {Object.keys(options.top_cover_colors).map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>

        <select
          className="border rounded px-2 py-1 w-full"
          value={config.top_cover_finish}
          onChange={(e) =>
            setConfig({ ...config, top_cover_finish: e.target.value })
          }
        >
          <option value="">Finish</option>
          {Object.keys(options.top_cover_finishes).map((f) => (
            <option key={f}>{f}</option>
          ))}
        </select>
      </div>

      {/* Fuse */}
      <div className="border p-4 rounded">
        <h2 className="font-semibold">Fuse</h2>

        <select
          className="border rounded px-2 py-1 w-full"
          value={config.number_of_fuses}
          onChange={(e) =>
            setConfig({ ...config, number_of_fuses: Number(e.target.value) })
          }
        >
          {Object.keys(options.fuse_counts).map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </div>

      <div className="flex justify-between">
        <button
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-800"
          type="button"
        >
          Create Configuration
        </button>

        <button
          className="bg-gray-700 text-white px-4 py-2 rounded hover:bg-gray-900"
          onClick={() => router.push("/configurator/Inventory")}
          type="button"
        >
          View Inventory
        </button>
      </div>
    </div>
  );
}