"use client";

import { useEffect, useMemo, useState } from "react";
import OEECard from "@/components/OEECard";
import PerformanceSidePanel, {
  PanelTarget,
} from "@/components/PerformanceSidePanel";

type Window = "1h" | "24h" | "7d";

interface ActorBreakdown {
  actor_name: string;
  availability: number;
  performance: number;
  quality: number;
  oee: number;
  jobs_total: number;
  jobs_good: number;
  latest_activity: string | null;
}

interface ResourceOee {
  line_id: string | null;
  resource_id: string;
  availability: number;
  performance: number;
  quality: number;
  oee: number;
  prev_oee: number;
  jobs_total: number;
  jobs_good: number;
  actor_count: number;
  latest_activity: string | null;
  actors: ActorBreakdown[];
}

interface LineOee {
  line_id: string;
  availability: number;
  performance: number;
  quality: number;
  oee: number;
  prev_oee: number;
  jobs_total: number;
  jobs_good: number;
  resource_count: number;
  latest_activity: string | null;
}

const POLL_INTERVAL_MS = 5000;

const WINDOW_LABEL: Record<Window, string> = {
  "1h": "Last hour",
  "24h": "Last 24 hours",
  "7d": "Last 7 days",
};

// Drilling_12345678 → Drilling
function prettifyResourceId(id: string): string {
  return id.replace(/_\d+$/, "");
}

export default function PerformancePage() {
  const [windowKey, setWindowKey] = useState<Window>("1h");
  const [view, setView] = useState<"line" | "station">("station");
  const [resources, setResources] = useState<ResourceOee[]>([]);
  const [lines, setLines] = useState<LineOee[]>([]);
  const [panelTarget, setPanelTarget] = useState<PanelTarget | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchAll = async () => {
      try {
        const [resRes, lineRes] = await Promise.all([
          fetch(`/api/metrics/resources?window=${windowKey}`, {
            cache: "no-store",
          }),
          fetch(`/api/metrics/lines?window=${windowKey}`, {
            cache: "no-store",
          }),
        ]);
        const resJson = await resRes.json();
        const lineJson = await lineRes.json();
        if (cancelled) return;
        setResources(resJson.resources ?? []);
        setLines(lineJson.lines ?? []);
      } catch {
        /* transient */
      }
    };
    fetchAll();
    const id = setInterval(fetchAll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [windowKey]);

  const resourcesByLine = useMemo(() => {
    const m = new Map<string, ResourceOee[]>();
    for (const r of resources) {
      const key = r.line_id ?? "(unassigned)";
      if (!m.has(key)) m.set(key, []);
      m.get(key)!.push(r);
    }
    return Array.from(m.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [resources]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="text-2xl font-bold uppercase">Performance</h1>

        <div className="inline-flex rounded-md border overflow-hidden">
          {(["1h", "24h", "7d"] as Window[]).map((w) => (
            <button
              key={w}
              onClick={() => setWindowKey(w)}
              className={`px-3 py-1.5 text-sm ${
                w === windowKey
                  ? "bg-primary text-background"
                  : "bg-muted hover:bg-muted/60"
              }`}
            >
              {w}
            </button>
          ))}
        </div>

        <div className="inline-flex rounded-md border overflow-hidden">
          {(["line", "station"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-3 py-1.5 text-sm capitalize ${
                v === view
                  ? "bg-primary text-background"
                  : "bg-muted hover:bg-muted/60"
              }`}
            >
              {v}-specific
            </button>
          ))}
        </div>

        <span className="ml-auto text-sm text-muted-foreground">
          {WINDOW_LABEL[windowKey]} · {lines.length} line(s) ·{" "}
          {resources.length} resource(s)
        </span>
      </div>

      {view === "line" && (
        <>
          {lines.length === 0 ? (
            <EmptyState hint="No metrics yet for this window. Run an order and check back." />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {lines.map((line) => (
                <OEECard
                  key={line.line_id}
                  stationId={line.line_id}
                  currentOEE={line.oee}
                  previousOEE={line.prev_oee}
                  latestActivity={
                    line.latest_activity
                      ? new Date(line.latest_activity).toLocaleString()
                      : "—"
                  }
                  onClick={() =>
                    setPanelTarget({ kind: "line", summary: line })
                  }
                />
              ))}
            </div>
          )}
        </>
      )}

      {view === "station" && (
        <>
          {resources.length === 0 ? (
            <EmptyState hint="No metrics yet for this window. Run an order and check back." />
          ) : (
            <div className="space-y-6">
              {resourcesByLine.map(([lineName, lineResources]) => (
                <section key={lineName} className="space-y-3">
                  <h2 className="text-lg font-semibold text-primary uppercase">
                    {lineName}
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                    {lineResources.map((r) => (
                      <OEECard
                        key={`${r.line_id}|${r.resource_id}`}
                        stationId={prettifyResourceId(r.resource_id)}
                        currentOEE={r.oee}
                        previousOEE={r.prev_oee}
                        latestActivity={
                          r.latest_activity
                            ? new Date(r.latest_activity).toLocaleString()
                            : "—"
                        }
                        onClick={() =>
                          setPanelTarget({ kind: "resource", summary: r })
                        }
                      />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </>
      )}

      <PerformanceSidePanel
        target={panelTarget}
        windowKey={windowKey}
        onClose={() => setPanelTarget(null)}
      />
    </div>
  );
}

function EmptyState({ hint }: { hint: string }) {
  return (
    <div className="rounded-md border p-6 text-center text-muted-foreground">
      {hint}
    </div>
  );
}
