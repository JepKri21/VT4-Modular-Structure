"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { X, AlertTriangle, AlertCircle, Info, Zap } from "lucide-react";

// Side panel triggered by the navbar bell. Lists the most recent alarms
// (active first), polls every 5s, and lets the user jump straight to the
// full Alarms page when they click a row.

interface Alarm {
  id: number;
  source: string;
  resource_id: string | null;
  actor_name: string | null;
  category: string;
  severity: string;
  order_id: string | null;
  message: string | null;
  triggered_at: string;
  cleared_at: string | null;
  acknowledged: boolean;
}

interface Props {
  open: boolean;
  onClose: () => void;
}

const POLL_INTERVAL_MS = 5000;

function severityIcon(severity: string) {
  switch (severity) {
    case "CRITICAL":
      return <Zap size={16} className="text-red-600 shrink-0" />;
    case "ERROR":
      return <AlertCircle size={16} className="text-red-500 shrink-0" />;
    case "WARNING":
      return (
        <AlertTriangle size={16} className="text-amber-500 shrink-0" />
      );
    default:
      return <Info size={16} className="text-muted-foreground shrink-0" />;
  }
}

export default function NotificationSidePanel({ open, onClose }: Props) {
  const router = useRouter();
  const [alarms, setAlarms] = useState<Alarm[]>([]);

  // Esc closes the panel.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Poll only while open.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const refresh = async () => {
      try {
        const res = await fetch("/api/alarms", { cache: "no-store" });
        const data = (await res.json()) as Alarm[];
        if (!cancelled) setAlarms(data);
      } catch {
        /* transient */
      }
    };
    refresh();
    const id = setInterval(refresh, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [open]);

  if (!open) return null;

  // Active first; otherwise keep the API's order (newest first).
  const sorted = [...alarms].sort((a, b) => {
    const aActive = a.cleared_at ? 1 : 0;
    const bActive = b.cleared_at ? 1 : 0;
    return aActive - bActive;
  });

  const activeCount = alarms.filter((a) => !a.cleared_at).length;

  const handleAlarmClick = () => {
    router.push("/alarms");
    onClose();
  };

  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-40" onClick={onClose} />
      <aside
        className="fixed top-0 right-0 h-full w-full max-w-md bg-background z-50 shadow-2xl flex flex-col"
        role="dialog"
      >
        <header className="flex items-center justify-between border-b p-4">
          <div>
            <p className="text-xs uppercase text-muted-foreground">
              Notifications
            </p>
            <h2 className="text-xl font-bold text-primary">
              {activeCount} active
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

        <div className="flex-1 overflow-y-auto">
          {sorted.length === 0 ? (
            <div className="p-6 text-center text-muted-foreground">
              No alarms.
            </div>
          ) : (
            <ul className="divide-y">
              {sorted.map((a) => (
                <li
                  key={a.id}
                  onClick={handleAlarmClick}
                  className={`p-4 cursor-pointer hover:bg-muted/60 ${
                    a.cleared_at ? "opacity-60" : ""
                  }`}
                >
                  <div className="flex items-start gap-3">
                    {severityIcon(a.severity)}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="text-sm font-semibold text-primary truncate">
                          {a.category}
                        </span>
                        <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                          {new Date(a.triggered_at).toLocaleTimeString()}
                        </span>
                      </div>
                      {a.resource_id && (
                        <div className="text-xs text-muted-foreground truncate">
                          {a.resource_id}
                          {a.actor_name ? ` / ${a.actor_name}` : ""}
                        </div>
                      )}
                      {a.message && (
                        <div className="text-xs mt-1 wrap-break-word">
                          {a.message}
                        </div>
                      )}
                      <div className="flex items-center gap-2 mt-1 text-[10px] uppercase tracking-wider">
                        <span className="text-muted-foreground">
                          {a.cleared_at ? "Cleared" : "Active"}
                        </span>
                        {a.acknowledged && (
                          <span className="text-muted-foreground">· Acked</span>
                        )}
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <footer className="border-t p-3">
          <button
            onClick={handleAlarmClick}
            className="w-full px-3 py-2 rounded-md bg-primary text-background text-sm font-medium hover:opacity-90"
          >
            Open Alarms page
          </button>
        </footer>
      </aside>
    </>
  );
}
