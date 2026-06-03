"use client";

import React from "react";
import { LineLane } from "@/lib/orchestration-snapshot";

type Props = {
  lanes: LineLane[];
};

// Short label for a long IRI: ".../Component/PCB/PCBFuseBoxA-abc..." -> "PCBFuseBoxA-abc..."
function shortIri(iri: string | null): string {
  if (!iri) return "";
  const segs = iri.split("/");
  return segs[segs.length - 1] || iri;
}

function packmlPillClass(state: string): string {
  switch (state.toUpperCase()) {
    case "IDLE":
      return "bg-green-100 text-green-800 border-green-200";
    case "EXECUTE":
    case "STARTING":
    case "COMPLETING":
    case "RESETTING":
      return "bg-blue-100 text-blue-800 border-blue-200";
    case "STOPPED":
    case "ABORTED":
    case "STOPPING":
    case "ABORTING":
      return "bg-red-100 text-red-800 border-red-200";
    case "HELD":
    case "HOLDING":
    case "SUSPENDED":
    case "SUSPENDING":
      return "bg-amber-100 text-amber-800 border-amber-200";
    default:
      return "bg-gray-100 text-gray-800 border-gray-200";
  }
}

export default function ResourceAllocationView({ lanes }: Props) {
  if (lanes.length === 0) {
    return (
      <div className="text-sm text-gray-500 italic p-4 border border-dashed rounded">
        No actors have reported state yet. Make sure the Line Controller is
        running and at least one resource has published a PackML state.
      </div>
    );
  }

  // Sort: stuck first (most attention needed), then occupied, then idle.
  const sorted = [...lanes].sort((a, b) => {
    const pri = (l: LineLane) => (l.stuck ? 0 : l.owner_order ? 1 : 2);
    if (pri(a) !== pri(b)) return pri(a) - pri(b);
    return a.resource_id.localeCompare(b.resource_id);
  });

  return (
    <div className="overflow-x-auto border rounded">
      <table className="min-w-full text-sm">
        <thead className="bg-gray-50 text-left text-xs uppercase text-gray-600">
          <tr>
            <th className="px-3 py-2">Resource</th>
            <th className="px-3 py-2">Actor</th>
            <th className="px-3 py-2">PackML</th>
            <th className="px-3 py-2">Owner Order</th>
            <th className="px-3 py-2">Cargo</th>
            <th className="px-3 py-2">Flags</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((l) => {
            const key = `${l.resource_id}/${l.actor_name}`;
            const rowClass = l.stuck
              ? "bg-red-50"
              : l.owner_order
                ? "bg-blue-50/40"
                : "";
            return (
              <tr key={key} className={`border-t ${rowClass}`}>
                <td className="px-3 py-2 font-mono text-gray-800">
                  {l.resource_id}
                </td>
                <td className="px-3 py-2 font-mono text-gray-800">
                  {l.actor_name}
                </td>
                <td className="px-3 py-2">
                  <span
                    className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${packmlPillClass(
                      l.packml_state,
                    )}`}
                  >
                    {l.packml_state}
                  </span>
                </td>
                <td className="px-3 py-2 font-mono text-xs text-gray-700">
                  {l.owner_order ?? <span className="text-gray-400">—</span>}
                </td>
                <td
                  className="px-3 py-2 font-mono text-xs text-gray-700 truncate max-w-xs"
                  title={l.cargo ?? ""}
                >
                  {l.cargo ? shortIri(l.cargo) : <span className="text-gray-400">empty</span>}
                </td>
                <td className="px-3 py-2">
                  {l.stuck && (
                    <span className="inline-flex items-center rounded-full border border-red-300 bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
                      STUCK
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
