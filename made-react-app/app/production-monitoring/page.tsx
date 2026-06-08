"use client";

import { useOrchestrationSnapshot } from "@/lib/useOrchestrationSnapshot";
import ResourceAllocationView from "@/components/ResourceAllocationView";
import DispatchQueueView from "@/components/DispatchQueueView";
import ResilienceTestingPanel from "@/components/ResilienceTestingPanel";

export default function ProductionMonitoringPage() {
  const { snapshot, status, error } = useOrchestrationSnapshot();

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Live Production Monitoring</h1>
        <ConnectionBadge status={status} />
      </div>

      {error && (
        <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
          {error}
        </div>
      )}

      <section>
        <div className="flex items-baseline justify-between mb-2">
          <h2 className="text-base font-medium">Dispatch Queue</h2>
          <span className="text-xs text-gray-500">
            {snapshot?.orders.length ?? 0} active
          </span>
        </div>
        <DispatchQueueView orders={snapshot?.orders ?? []} />
      </section>

      <section>
        <div className="flex items-baseline justify-between mb-2">
          <h2 className="text-base font-medium">Resource Allocation</h2>
          {snapshot && (
            <span className="text-xs text-gray-500">
              snapshot {new Date(snapshot.timestamp).toLocaleTimeString()}
            </span>
          )}
        </div>
        <ResourceAllocationView lanes={snapshot?.lanes ?? []} />
      </section>

      <ResilienceTestingPanel lanes={snapshot?.lanes ?? []} />
    </div>
  );
}

function ConnectionBadge({ status }: { status: string }) {
  const cls =
    status === "connected"
      ? "bg-green-100 text-green-800 border-green-200"
      : status === "error"
        ? "bg-red-100 text-red-800 border-red-200"
        : "bg-amber-100 text-amber-800 border-amber-200";
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      MQTT: {status}
    </span>
  );
}
