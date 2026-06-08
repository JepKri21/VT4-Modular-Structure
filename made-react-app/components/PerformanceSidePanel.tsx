"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";

// Drill-down panel for a resource or a line. Slides in from the right and
// can be dismissed by the close button, clicking the backdrop, or hitting
// Escape. Data is fetched lazily when `target` is set; closing clears it
// to avoid stale content flashing on next open.

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

interface ResourceCardSummary {
  resource_id: string;
  line_id: string | null;
  availability: number;
  performance: number;
  quality: number;
  oee: number;
  jobs_total: number;
  jobs_good: number;
  actor_count: number;
  actors: ActorBreakdown[];
}

interface LineCardSummary {
  line_id: string;
  availability: number;
  performance: number;
  quality: number;
  oee: number;
  jobs_total: number;
  jobs_good: number;
  resource_count: number;
}

interface ResourceDetail {
  jobs: Array<{
    actor_name: string;
    order_id: string | null;
    job_id: string | null;
    ideal_cycle_time_ms: number | null;
    actual_cycle_time_ms: number | null;
    result: string | null;
    quality: string | null;
    completed_at: string;
  }>;
  current_states: Array<{
    actor_name: string;
    state: string;
    since: string;
  }>;
}

interface LineDetail {
  orders: { completed: number; aborted: number; throughput_per_hour: number };
  lead_time_ms: { avg: number | null; p50: number | null; p95: number | null };
  attempt_distribution: Array<{ attempt_count: number; n: number }>;
  recent_orders: Array<{
    order_id: string;
    product_ref: string | null;
    started_at: string;
    completed_at: string;
    status: string;
    attempt_count: number;
  }>;
}

export type PanelTarget =
  | { kind: "resource"; summary: ResourceCardSummary }
  | { kind: "line"; summary: LineCardSummary };

interface Props {
  target: PanelTarget | null;
  windowKey: Window;
  onClose: () => void;
}

export default function PerformanceSidePanel({
  target,
  windowKey,
  onClose,
}: Props) {
  const [resourceDetail, setResourceDetail] = useState<ResourceDetail | null>(
    null,
  );
  const [lineDetail, setLineDetail] = useState<LineDetail | null>(null);

  // Esc to close.
  useEffect(() => {
    if (!target) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [target, onClose]);

  // Fetch detail when target changes.
  useEffect(() => {
    if (!target) {
      setResourceDetail(null);
      setLineDetail(null);
      return;
    }
    let cancelled = false;

    const url =
      target.kind === "resource"
        ? `/api/metrics/resources/${encodeURIComponent(
            target.summary.resource_id,
          )}?window=${windowKey}`
        : `/api/metrics/lines/${encodeURIComponent(
            target.summary.line_id,
          )}?window=${windowKey}`;

    fetch(url, { cache: "no-store" })
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        if (target.kind === "resource") setResourceDetail(data);
        else setLineDetail(data);
      })
      .catch(() => {
        /* swallow */
      });

    return () => {
      cancelled = true;
    };
  }, [target, windowKey]);

  if (!target) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 z-40"
        onClick={onClose}
      />
      {/* Panel */}
      <aside
        className="fixed top-0 right-0 h-full w-full max-w-2xl bg-background z-50 shadow-2xl flex flex-col"
        role="dialog"
      >
        <header className="flex items-center justify-between border-b p-4">
          <div className="min-w-0">
            <p className="text-xs uppercase text-muted-foreground">
              {target.kind === "resource" ? "Resource" : "Production Line"}
            </p>
            <h2 className="text-xl font-bold text-primary truncate">
              {target.kind === "resource"
                ? target.summary.resource_id
                : target.summary.line_id}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-md hover:bg-muted"
            aria-label="Close"
          >
            <X size={20} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {target.kind === "resource" ? (
            <ResourceBody
              summary={target.summary}
              detail={resourceDetail}
            />
          ) : (
            <LineBody summary={target.summary} detail={lineDetail} />
          )}
        </div>
      </aside>
    </>
  );
}

function MetricGrid({
  rows,
}: {
  rows: Array<[string, string | number]>;
}) {
  return (
    <div className="grid grid-cols-2 gap-3">
      {rows.map(([k, v]) => (
        <div key={k} className="rounded-md border p-3 bg-muted">
          <div className="text-[10px] uppercase text-muted-foreground tracking-wider">
            {k}
          </div>
          <div className="text-lg font-semibold text-primary mt-1">{v}</div>
        </div>
      ))}
    </div>
  );
}

function ResourceBody({
  summary,
  detail,
}: {
  summary: ResourceCardSummary;
  detail: ResourceDetail | null;
}) {
  return (
    <>
      <section>
        <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-2">
          OEE Breakdown
        </h3>
        <MetricGrid
          rows={[
            ["Availability", `${summary.availability}%`],
            ["Performance", `${summary.performance}%`],
            ["Quality", `${summary.quality}%`],
            ["OEE", `${summary.oee}%`],
            ["Jobs", `${summary.jobs_good} / ${summary.jobs_total} good`],
            ["Actors", `${summary.actor_count}`],
          ]}
        />
      </section>

      {summary.actors.length > 1 && (
        <section>
          <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-2">
            Per actor
          </h3>
          <table className="w-full text-sm border rounded-md overflow-hidden">
            <thead className="bg-muted">
              <tr className="border-b">
                <th className="text-left p-2">Actor</th>
                <th className="text-right p-2">A</th>
                <th className="text-right p-2">P</th>
                <th className="text-right p-2">Q</th>
                <th className="text-right p-2">OEE</th>
                <th className="text-right p-2">Jobs</th>
              </tr>
            </thead>
            <tbody>
              {summary.actors.map((a) => (
                <tr key={a.actor_name} className="border-b last:border-b-0">
                  <td className="p-2 font-medium">{a.actor_name}</td>
                  <td className="p-2 text-right">{a.availability}%</td>
                  <td className="p-2 text-right">{a.performance}%</td>
                  <td className="p-2 text-right">{a.quality}%</td>
                  <td className="p-2 text-right font-semibold">{a.oee}%</td>
                  <td className="p-2 text-right">
                    {a.jobs_good}/{a.jobs_total}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section>
        <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-2">
          Current state
        </h3>
        {detail && detail.current_states.length > 0 ? (
          <table className="w-full text-sm border rounded-md overflow-hidden">
            <thead className="bg-muted">
              <tr className="border-b">
                <th className="text-left p-2">Actor</th>
                <th className="text-left p-2">State</th>
                <th className="text-left p-2">Since</th>
              </tr>
            </thead>
            <tbody>
              {detail.current_states.map((s) => (
                <tr key={s.actor_name} className="border-b last:border-b-0">
                  <td className="p-2 font-medium">{s.actor_name}</td>
                  <td className="p-2">{s.state}</td>
                  <td className="p-2 text-muted-foreground">
                    {new Date(s.since).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-sm text-muted-foreground italic">
            {detail ? "no state reported" : "loading…"}
          </div>
        )}
      </section>

      <section>
        <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-2">
          Cycle time (last {detail?.jobs.length ?? 0} jobs)
        </h3>
        <CycleTimeChart jobs={detail?.jobs ?? []} />
      </section>

      <section>
        <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-2">
          Recent jobs
        </h3>
        {detail && detail.jobs.length > 0 ? (
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted">
                <tr className="border-b">
                  <th className="text-left p-2">When</th>
                  <th className="text-left p-2">Actor</th>
                  <th className="text-left p-2">Job</th>
                  <th className="text-right p-2">Ideal (ms)</th>
                  <th className="text-right p-2">Actual (ms)</th>
                  <th className="text-left p-2">Result</th>
                  <th className="text-left p-2">Quality</th>
                </tr>
              </thead>
              <tbody>
                {detail.jobs.map((j, i) => (
                  <tr key={i} className="border-b last:border-b-0">
                    <td className="p-2 text-muted-foreground whitespace-nowrap">
                      {new Date(j.completed_at).toLocaleTimeString()}
                    </td>
                    <td className="p-2 whitespace-nowrap">{j.actor_name}</td>
                    <td className="p-2 whitespace-nowrap font-mono text-xs">
                      {j.job_id ?? "—"}
                    </td>
                    <td className="p-2 text-right">
                      {j.ideal_cycle_time_ms ?? "—"}
                    </td>
                    <td className="p-2 text-right">
                      {j.actual_cycle_time_ms ?? "—"}
                    </td>
                    <td className="p-2">{j.result ?? "—"}</td>
                    <td className="p-2">{j.quality ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-sm text-muted-foreground italic">
            {detail ? "no jobs in this window" : "loading…"}
          </div>
        )}
      </section>
    </>
  );
}

function CycleTimeChart({
  jobs,
}: {
  jobs: Array<{
    actual_cycle_time_ms: number | null;
    ideal_cycle_time_ms: number | null;
    completed_at: string;
  }>;
}) {
  if (jobs.length === 0) {
    return (
      <div className="text-sm text-muted-foreground italic">
        no jobs in this window
      </div>
    );
  }

  // Chronological for a left-to-right reading.
  const ordered = [...jobs].reverse();
  const maxMs = Math.max(
    ...ordered.flatMap((j) => [
      j.actual_cycle_time_ms ?? 0,
      j.ideal_cycle_time_ms ?? 0,
    ]),
    1,
  );

  const W = 600;
  const H = 140;
  const xStep = ordered.length > 1 ? W / (ordered.length - 1) : 0;
  const y = (ms: number) => H - (ms / maxMs) * H;

  const actualPath = ordered
    .map((j, i) =>
      j.actual_cycle_time_ms == null
        ? ""
        : `${i === 0 ? "M" : "L"} ${i * xStep} ${y(j.actual_cycle_time_ms)}`,
    )
    .filter(Boolean)
    .join(" ");

  const idealPath = ordered
    .map((j, i) =>
      j.ideal_cycle_time_ms == null
        ? ""
        : `${i === 0 ? "M" : "L"} ${i * xStep} ${y(j.ideal_cycle_time_ms)}`,
    )
    .filter(Boolean)
    .join(" ");

  return (
    <div className="rounded-md border p-3 bg-muted">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        preserveAspectRatio="none"
      >
        <path
          d={idealPath}
          fill="none"
          stroke="currentColor"
          className="text-muted-foreground"
          strokeDasharray="4 3"
          strokeWidth={1.5}
        />
        <path
          d={actualPath}
          fill="none"
          stroke="currentColor"
          className="text-primary"
          strokeWidth={2}
        />
      </svg>
      <div className="flex gap-4 text-xs text-muted-foreground mt-2">
        <span>
          <span className="inline-block w-3 border-t-2 border-primary mr-1 align-middle" />
          actual
        </span>
        <span>
          <span className="inline-block w-3 border-t border-dashed border-muted-foreground mr-1 align-middle" />
          ideal
        </span>
        <span className="ml-auto">max {maxMs} ms</span>
      </div>
    </div>
  );
}

function LineBody({
  summary,
  detail,
}: {
  summary: LineCardSummary;
  detail: LineDetail | null;
}) {
  const fmtMs = (ms: number | null) => {
    if (ms == null) return "—";
    if (ms < 1000) return `${ms} ms`;
    if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
    return `${(ms / 60_000).toFixed(1)} min`;
  };

  return (
    <>
      <section>
        <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-2">
          OEE Breakdown
        </h3>
        <MetricGrid
          rows={[
            ["Availability", `${summary.availability}%`],
            ["Performance", `${summary.performance}%`],
            ["Quality", `${summary.quality}%`],
            ["OEE", `${summary.oee}%`],
            ["Resources", `${summary.resource_count}`],
            ["Jobs", `${summary.jobs_good} / ${summary.jobs_total} good`],
          ]}
        />
      </section>

      <section>
        <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-2">
          Orders
        </h3>
        {detail ? (
          <MetricGrid
            rows={[
              ["Completed", detail.orders.completed],
              ["Aborted", detail.orders.aborted],
              ["Throughput / h", detail.orders.throughput_per_hour],
              ["Avg lead time", fmtMs(detail.lead_time_ms.avg)],
              ["p50 lead time", fmtMs(detail.lead_time_ms.p50)],
              ["p95 lead time", fmtMs(detail.lead_time_ms.p95)],
            ]}
          />
        ) : (
          <div className="text-sm text-muted-foreground italic">loading…</div>
        )}
      </section>

      <section>
        <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-2">
          Attempt distribution
        </h3>
        {detail && detail.attempt_distribution.length > 0 ? (
          <table className="w-full text-sm border rounded-md overflow-hidden">
            <thead className="bg-muted">
              <tr className="border-b">
                <th className="text-left p-2">Attempts</th>
                <th className="text-right p-2">Orders</th>
              </tr>
            </thead>
            <tbody>
              {detail.attempt_distribution.map((b) => (
                <tr key={b.attempt_count} className="border-b last:border-b-0">
                  <td className="p-2">{b.attempt_count}</td>
                  <td className="p-2 text-right">{b.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-sm text-muted-foreground italic">
            {detail ? "no orders in this window" : "loading…"}
          </div>
        )}
      </section>

      <section>
        <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-2">
          Recent orders
        </h3>
        {detail && detail.recent_orders.length > 0 ? (
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted">
                <tr className="border-b">
                  <th className="text-left p-2">Order</th>
                  <th className="text-left p-2">Status</th>
                  <th className="text-right p-2">Attempts</th>
                  <th className="text-left p-2">Completed</th>
                </tr>
              </thead>
              <tbody>
                {detail.recent_orders.map((o) => (
                  // order_id alone isn't unique — an order that goes
                  // through OrderRecovery emits one OrderCompleted per
                  // attempt, so the same order_id can appear multiple
                  // times. completed_at disambiguates.
                  <tr
                    key={`${o.order_id}-${o.completed_at}`}
                    className="border-b last:border-b-0"
                  >
                    <td className="p-2 font-mono text-xs">{o.order_id}</td>
                    <td className="p-2">{o.status}</td>
                    <td className="p-2 text-right">{o.attempt_count}</td>
                    <td className="p-2 text-muted-foreground whitespace-nowrap">
                      {new Date(o.completed_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-sm text-muted-foreground italic">
            {detail ? "no orders in this window" : "loading…"}
          </div>
        )}
      </section>
    </>
  );
}
