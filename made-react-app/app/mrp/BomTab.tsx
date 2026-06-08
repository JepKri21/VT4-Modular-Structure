"use client";

import { useEffect, useState } from "react";

// Read-only preset BOM view.
// BOM is authored in the AAS Configurator (the YAML presets); this page
// just surfaces the explosion so the MRP engineer can verify the tree
// the run will walk.

interface BomChild {
  iri: string;
  description: string;
  quantity: number;
  is_sub_assembly: boolean;
}

interface BomEntry {
  parent_iri: string;
  parent_full_iri: string;
  parent_name: string;
  parent_kind: "FINISHED" | "INTERMEDIATE" | "RAW";
  preset_file: string;
  children: BomChild[];
}

const KIND_TINT: Record<BomEntry["parent_kind"], string> = {
  FINISHED: "text-purple-700 bg-purple-50 border-purple-200",
  INTERMEDIATE: "text-blue-700 bg-blue-50 border-blue-200",
  RAW: "text-emerald-700 bg-emerald-50 border-emerald-200",
};

export default function BomTab() {
  const [entries, setEntries] = useState<BomEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/mrp/bom", { cache: "no-store" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
      setEntries(data.entries ?? []);
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  return (
    <div className="space-y-4">
      {error && (
        <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
          {error}
        </div>
      )}

      <section className="rounded-md border p-3 bg-muted/30">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-sm font-semibold uppercase text-muted-foreground">
            Source
          </h2>
          <span className="text-xs text-muted-foreground">
            BOM is read from <code>shell_presets/*.yaml</code>. Edit in the AAS
            Configurator; refresh here to pick up changes.
          </span>
          <button
            onClick={refresh}
            disabled={loading}
            className="ml-auto px-3 py-1 rounded-md bg-primary text-background text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "Reading…" : "Refresh from presets"}
          </button>
        </div>
      </section>

      {entries.length === 0 ? (
        <div className="rounded-md border p-6 text-center text-muted-foreground text-sm">
          No preset has a non-empty <code>BillOfMaterials.BOMEntries</code>{" "}
          section. Add one in the Configurator.
        </div>
      ) : (
        <div className="space-y-3">
          {entries.map((e) => (
            <section
              key={e.parent_full_iri}
              className="rounded-md border overflow-hidden"
            >
              <header className="bg-muted px-3 py-2 border-b flex flex-wrap items-baseline gap-3">
                <h3 className="text-sm font-semibold">{e.parent_name}</h3>
                <span
                  className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium ${KIND_TINT[e.parent_kind]}`}
                >
                  {e.parent_kind}
                </span>
                <span className="text-[10px] font-mono text-muted-foreground truncate flex-1">
                  {e.parent_full_iri}
                </span>
                <span className="text-[10px] text-muted-foreground">
                  {e.preset_file}
                </span>
              </header>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left p-2">Child component</th>
                    <th className="text-left p-2">Description</th>
                    <th className="text-right p-2">Qty / parent</th>
                  </tr>
                </thead>
                <tbody>
                  {e.children.map((c, i) => (
                    <tr key={`${c.iri}-${i}`} className="border-b last:border-b-0">
                      <td className="p-2">
                        <div className="text-[10px] font-mono text-muted-foreground truncate max-w-md">
                          {c.iri}
                        </div>
                      </td>
                      <td className="p-2 text-xs">{c.description}</td>
                      <td className="p-2 text-right tabular-nums">
                        {c.quantity}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
