"use client";

import React from "react";
import { LineOrder } from "@/lib/orchestration-snapshot";

type Props = {
  orders: LineOrder[];
};

function shortIri(iri: string | null): string {
  if (!iri) return "";
  const segs = iri.split("/");
  return segs[segs.length - 1] || iri;
}

function stepPillClass(state: string): string {
  switch (state.toUpperCase()) {
    case "COMPLETED":
      return "bg-green-100 text-green-800 border-green-200";
    case "IN_PROGRESS":
      return "bg-blue-100 text-blue-800 border-blue-200";
    case "ASSIGNED":
      return "bg-indigo-100 text-indigo-800 border-indigo-200";
    case "PENDING":
      return "bg-gray-100 text-gray-700 border-gray-200";
    case "PLANNED":
      return "bg-amber-100 text-amber-800 border-amber-200";
    default:
      return "bg-gray-100 text-gray-700 border-gray-200";
  }
}

function progress(order: LineOrder): { done: number; total: number } {
  const total = order.steps.length;
  const done = order.steps.filter((s) => s.state === "COMPLETED").length;
  return { done, total };
}

export default function DispatchQueueView({ orders }: Props) {
  if (orders.length === 0) {
    return (
      <div className="text-sm text-gray-500 italic p-4 border border-dashed rounded">
        No active orders. Publish a WorkOrder to{" "}
        <code className="mx-1 px-1 bg-gray-100 rounded text-xs">
          AAUSmartLab/ProductionLine1/MES/WorkOrder
        </code>{" "}
        to see one here.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {orders.map((o) => {
        const { done, total } = progress(o);
        const pct = total === 0 ? 0 : Math.round((done / total) * 100);
        const current = o.steps.find((s) => s.step_id === o.current_step);
        return (
          <div key={o.order_id} className="border rounded p-3 bg-white">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <div className="font-mono font-semibold text-sm">
                  {o.order_id}
                </div>
                <div
                  className="text-xs text-gray-500 truncate max-w-md"
                  title={o.product_reference ?? ""}
                >
                  {shortIri(o.product_reference)}
                </div>
              </div>
              <div className="text-xs text-gray-600">
                {done} / {total} steps · {pct}%
              </div>
            </div>

            {/* Progress bar */}
            <div className="mt-2 h-1.5 w-full bg-gray-100 rounded overflow-hidden">
              <div
                className="h-full bg-blue-500 transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>

            {/* Current step callout */}
            {current && (
              <div className="mt-2 text-xs text-gray-700">
                <span className="text-gray-500">Now:</span>{" "}
                <span className="font-mono">{current.step_id}</span>{" "}
                <span className="text-gray-500">on</span>{" "}
                <span className="font-mono">
                  {shortIri(current.assigned_resource) || "—"}
                </span>
              </div>
            )}

            {/* Step chips */}
            <div className="mt-2 flex flex-wrap gap-1">
              {o.steps.map((s) => (
                <span
                  key={s.step_id}
                  title={`${s.name} — ${s.ingredient}\nstate: ${s.state}\nassigned: ${
                    shortIri(s.assigned_resource) || "—"
                  }`}
                  className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-mono ${stepPillClass(
                    s.state,
                  )}`}
                >
                  {s.step_id}
                </span>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
