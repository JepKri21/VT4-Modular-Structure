"use client";

import { useEffect, useMemo, useState } from "react";

interface Alarm {
  id: number;
  source: string;
  resource_id: string | null;
  category: string;
  severity: string;
  order_id: string | null;
  message: string | null;
  triggered_at: string;
  cleared_at: string | null;
  acknowledged: boolean;
}

const POLL_INTERVAL_MS = 3000;

export default function AlarmsPage() {
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [showCleared, setShowCleared] = useState(false);
  const [query, setQuery] = useState("");

  const refresh = async () => {
    const res = await fetch("/api/alarms", { cache: "no-store" });
    const data = await res.json();
    setAlarms(data);
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  const acknowledgeAlarm = async (id: number) => {
    await fetch("/api/alarms/acknowledge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    setAlarms((prev) =>
      prev.map((alarm) =>
        alarm.id === id ? { ...alarm, acknowledged: true } : alarm,
      ),
    );
  };

  const resolveAlarm = async (id: number) => {
    await fetch("/api/alarms/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    setAlarms((prev) =>
      prev.map((alarm) =>
        alarm.id === id
          ? { ...alarm, cleared_at: new Date().toISOString() }
          : alarm,
      ),
    );
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return alarms.filter((a) => {
      if (!showCleared && a.cleared_at) return false;
      if (!q) return true;
      const hay = [
        a.source,
        a.resource_id ?? "",
        a.category,
        a.severity,
        a.order_id ?? "",
        a.message ?? "",
      ]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [alarms, showCleared, query]);

  const activeCount = useMemo(
    () => alarms.filter((a) => !a.cleared_at).length,
    [alarms],
  );
  const clearedCount = alarms.length - activeCount;

  return (
    <div className="p-6 space-y-4">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="text-2xl font-bold uppercase">Alarms</h1>
        <span className="text-sm text-muted-foreground">
          {activeCount} active · {clearedCount} cleared
        </span>
        <div className="ml-auto flex items-center gap-3">
          <input
            type="text"
            placeholder="Search…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="px-3 py-1.5 rounded-md bg-muted text-sm focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showCleared}
              onChange={(e) => setShowCleared(e.target.checked)}
            />
            Show cleared
          </label>
        </div>
      </div>

      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted">
            <tr className="border-b">
              <th className="text-left p-2 whitespace-nowrap">Source</th>
              <th className="text-left p-2 whitespace-nowrap">Resource</th>
              <th className="text-left p-2 whitespace-nowrap">Category</th>
              <th className="text-left p-2 whitespace-nowrap">Severity</th>
              <th className="text-left p-2 whitespace-nowrap">Order</th>
              <th className="text-left p-2">Message</th>
              <th className="text-left p-2 whitespace-nowrap">Time</th>
              <th className="text-left p-2 whitespace-nowrap">Status</th>
              <th className="text-left p-2 whitespace-nowrap">Ack</th>
              <th className="text-left p-2 whitespace-nowrap">Resolve</th>
            </tr>
          </thead>

          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td
                  colSpan={10}
                  className="p-4 text-center text-muted-foreground"
                >
                  No alarms{query ? " match the search" : ""}.
                </td>
              </tr>
            )}
            {filtered.map((alarm) => (
              <tr
                key={alarm.id}
                className={`border-b ${
                  alarm.cleared_at ? "opacity-60" : ""
                }`}
              >
                <td className="p-2 whitespace-nowrap">{alarm.source}</td>
                <td className="p-2 whitespace-nowrap">
                  {alarm.resource_id ?? "—"}
                </td>
                <td className="p-2 whitespace-nowrap">{alarm.category}</td>
                <td className="p-2 whitespace-nowrap">{alarm.severity}</td>
                <td className="p-2 whitespace-nowrap">
                  {alarm.order_id ?? "—"}
                </td>
                <td className="p-2 max-w-md break-words whitespace-normal">
                  {alarm.message ?? ""}
                </td>
                <td className="p-2 whitespace-nowrap">
                  {new Date(alarm.triggered_at).toLocaleString()}
                </td>
                <td className="p-2 whitespace-nowrap">
                  {alarm.cleared_at ? "Cleared" : "Active"}
                </td>
                <td className="p-2 whitespace-nowrap">
                  {alarm.acknowledged ? (
                    <span className="text-muted-foreground">Acked</span>
                  ) : (
                    <button
                      onClick={() => acknowledgeAlarm(alarm.id)}
                      className="text-primary hover:underline"
                    >
                      Acknowledge
                    </button>
                  )}
                </td>
                <td className="p-2 whitespace-nowrap">
                  {alarm.cleared_at ? (
                    <span className="text-muted-foreground">—</span>
                  ) : (
                    <button
                      onClick={() => resolveAlarm(alarm.id)}
                      className="text-primary hover:underline"
                    >
                      Resolve
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
