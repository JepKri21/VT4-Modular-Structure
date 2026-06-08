"use client";

import { useEffect, useMemo, useState } from "react";

// MRP-3: actionable Purchase Orders.
//   PROPOSED  → Approve / Cancel
//   APPROVED  → Receive (publishes MQTT to deliver_to; station appends
//              fresh instances to its bin) / Cancel
//   RECEIVED  → read-only
//   CANCELLED → read-only

interface PoRow {
  id: number;
  component_type_iri: string;
  quantity: number;
  strategy: string | null;
  status: "PROPOSED" | "APPROVED" | "RECEIVED" | "CANCELLED";
  unit_cost: string | null;
  total_cost: string | null;
  needed_by: string | null;
  created_at: string;
  approved_at: string | null;
  received_at: string | null;
  deliver_to: string | null;
  notes: string | null;
  material_name: string | null;
  material_category: string | null;
}

const STATUS_TINT: Record<PoRow["status"], string> = {
  PROPOSED: "text-amber-700 bg-amber-50 border-amber-200",
  APPROVED: "text-blue-700 bg-blue-50 border-blue-200",
  RECEIVED: "text-green-700 bg-green-50 border-green-200",
  CANCELLED: "text-muted-foreground bg-muted border-border",
};

const POLL_MS = 5000;

// The dashboard doesn't yet know which stations exist as a topology — for
// the receive picker we read it off the orchestration snapshot too, but a
// short hard-coded fallback keeps the form usable when the snapshot isn't
// available. The dropdown is editable so any new station name works.
const DEFAULT_STATIONS = [
  "Storage_12345678",
  "BCPCBFuseAssembler_12345678",
];

export default function PurchaseOrdersTab() {
  const [rows, setRows] = useState<PoRow[]>([]);
  const [statusFilter, setStatusFilter] = useState<"" | PoRow["status"]>("");
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const url = statusFilter
        ? `/api/mrp/purchase-orders?status=${statusFilter}`
        : "/api/mrp/purchase-orders";
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setRows(data.rows ?? []);
      setError(null);
    } catch (err) {
      setError(String(err));
    }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [statusFilter]);

  const summary = useMemo(() => {
    const acc = { PROPOSED: 0, APPROVED: 0, RECEIVED: 0, CANCELLED: 0 } as Record<
      PoRow["status"],
      number
    >;
    for (const r of rows) acc[r.status] = (acc[r.status] ?? 0) + 1;
    return acc;
  }, [rows]);

  const approve = async (id: number) => {
    const res = await fetch(`/api/mrp/purchase-orders/${id}/approve`, {
      method: "POST",
    });
    if (!res.ok) alert((await res.json().catch(() => ({}))).error ?? "approve failed");
    refresh();
  };

  const cancel = async (id: number) => {
    if (!confirm("Cancel this PO?")) return;
    const res = await fetch(`/api/mrp/purchase-orders/${id}/cancel`, {
      method: "POST",
    });
    if (!res.ok) alert((await res.json().catch(() => ({}))).error ?? "cancel failed");
    refresh();
  };

  const receive = async (po: PoRow) => {
    const suggestion = po.deliver_to ?? DEFAULT_STATIONS[0];
    const deliverTo = prompt(
      `Receive ${po.quantity} × ${po.material_name ?? po.component_type_iri}.\nDeliver to station:`,
      suggestion,
    );
    if (!deliverTo) return;
    const res = await fetch(`/api/mrp/purchase-orders/${po.id}/receive`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ deliver_to: deliverTo.trim() }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      alert(body.error ?? body.warning ?? "receive failed");
    }
    refresh();
  };

  return (
    <div className="space-y-4">
      {error && (
        <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
          {error}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-xs text-muted-foreground flex items-center gap-2">
          Status
          <select
            value={statusFilter}
            onChange={(e) =>
              setStatusFilter(e.target.value as "" | PoRow["status"])
            }
            className="px-2 py-1 rounded border bg-background text-sm"
          >
            <option value="">All</option>
            <option value="PROPOSED">Proposed</option>
            <option value="APPROVED">Approved</option>
            <option value="RECEIVED">Received</option>
            <option value="CANCELLED">Cancelled</option>
          </select>
        </label>
        <span className="text-xs text-muted-foreground">
          {summary.PROPOSED} proposed · {summary.APPROVED} approved ·{" "}
          {summary.RECEIVED} received · {summary.CANCELLED} cancelled
        </span>
      </div>

      {rows.length === 0 ? (
        <div className="rounded-md border p-6 text-center text-muted-foreground text-sm">
          No purchase orders.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted">
              <tr className="border-b">
                <th className="text-left p-2">Material</th>
                <th className="text-right p-2">Quantity</th>
                <th className="text-left p-2">Strategy</th>
                <th className="text-left p-2">Status</th>
                <th className="text-right p-2">Unit cost</th>
                <th className="text-right p-2">Total</th>
                <th className="text-left p-2">Needed by</th>
                <th className="text-left p-2">Deliver to</th>
                <th className="text-left p-2">Notes</th>
                <th className="text-left p-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b">
                  <td className="p-2">
                    <div className="font-medium">
                      {r.material_name ?? r.component_type_iri}
                    </div>
                    <div className="text-[10px] font-mono text-muted-foreground truncate max-w-md">
                      {r.component_type_iri}
                    </div>
                  </td>
                  <td className="p-2 text-right tabular-nums font-semibold">
                    {r.quantity}
                  </td>
                  <td className="p-2 text-xs">{r.strategy ?? "—"}</td>
                  <td className="p-2">
                    <span
                      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium ${STATUS_TINT[r.status]}`}
                    >
                      {r.status}
                    </span>
                  </td>
                  <td className="p-2 text-right tabular-nums">
                    {r.unit_cost ?? "—"}
                  </td>
                  <td className="p-2 text-right tabular-nums">
                    {r.total_cost ?? "—"}
                  </td>
                  <td className="p-2 text-muted-foreground whitespace-nowrap">
                    {r.needed_by
                      ? new Date(r.needed_by).toLocaleDateString()
                      : "—"}
                  </td>
                  <td className="p-2 text-muted-foreground text-xs whitespace-nowrap">
                    {r.deliver_to ?? "—"}
                  </td>
                  <td className="p-2 text-xs text-muted-foreground max-w-xs">
                    {r.notes ?? "—"}
                  </td>
                  <td className="p-2 whitespace-nowrap space-x-2">
                    {r.status === "PROPOSED" && (
                      <>
                        <button
                          onClick={() => approve(r.id)}
                          className="text-blue-600 hover:underline text-xs"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => cancel(r.id)}
                          className="text-red-600 hover:underline text-xs"
                        >
                          Cancel
                        </button>
                      </>
                    )}
                    {r.status === "APPROVED" && (
                      <>
                        <button
                          onClick={() => receive(r)}
                          className="text-green-700 hover:underline text-xs"
                        >
                          Receive
                        </button>
                        <button
                          onClick={() => cancel(r.id)}
                          className="text-red-600 hover:underline text-xs"
                        >
                          Cancel
                        </button>
                      </>
                    )}
                    {(r.status === "RECEIVED" || r.status === "CANCELLED") && (
                      <span className="text-muted-foreground text-xs">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[11px] text-muted-foreground">
        Receive publishes a <code>ReceiveShipment</code> message to the
        chosen station, which appends fresh instances to its bin and
        republishes its <code>InventoryLevel</code>. AAS shell upload for
        received components is a follow-up.
      </p>
    </div>
  );
}
