"use client";

// Manual fault-injection controls for RR1 / RR2 / RR3 demos. Publishes a
// TestInjectionMessage to a chosen resource's TestInjection topic. The
// station must have opted in by calling `mqtt_client.enable_fault_injection()`
// in its implementation script — otherwise messages are silently dropped.

import { useMemo, useState } from "react";
import type { LineLane } from "@/lib/orchestration-snapshot";

interface Props {
  lanes: LineLane[];
}

type Command = "DROP_ACKS" | "NEXT_INCOMPLETE" | "GO_SILENT";

interface Feedback {
  ok: boolean;
  text: string;
}

export default function ResilienceTestingPanel({ lanes }: Props) {
  // De-duplicate to one entry per resource (lanes are per-actor).
  const resources = useMemo(() => {
    const set = new Set<string>();
    for (const lane of lanes) set.add(lane.resource_id);
    return Array.from(set).sort();
  }, [lanes]);

  const [target, setTarget] = useState<string>("");
  const [dropCount, setDropCount] = useState<number>(2);
  const [silentSeconds, setSilentSeconds] = useState<number>(90);
  const [busy, setBusy] = useState<Command | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  const selected = target || resources[0] || "";

  const fire = async (
    command: Command,
    extra: Partial<{ count: number; duration_s: number }> = {},
  ) => {
    if (!selected) {
      setFeedback({ ok: false, text: "Pick a resource first." });
      return;
    }
    setBusy(command);
    setFeedback(null);
    try {
      const res = await fetch("/api/resilience/inject", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resource_id: selected,
          command,
          ...extra,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setFeedback({
          ok: false,
          text: data.error ?? `injection failed (${res.status})`,
        });
      } else {
        setFeedback({ ok: true, text: describe(command, extra) });
      }
    } catch (err) {
      setFeedback({ ok: false, text: String(err) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="rounded-md border p-4 space-y-3 bg-muted/30">
      <header className="flex items-baseline justify-between">
        <h2 className="text-base font-medium">Resilience Testing</h2>
        <span className="text-xs text-muted-foreground">
          Manual fault injection · RR1 / RR2 / RR3
        </span>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-muted-foreground flex flex-col gap-1">
          Target resource
          <select
            value={selected}
            onChange={(e) => setTarget(e.target.value)}
            className="px-3 py-1.5 rounded-md bg-background border text-sm min-w-64"
            disabled={resources.length === 0}
          >
            {resources.length === 0 && (
              <option value="">no resources in snapshot yet</option>
            )}
            {resources.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>

        <label className="text-xs text-muted-foreground flex flex-col gap-1">
          Drop count
          <input
            type="number"
            min={1}
            value={dropCount}
            onChange={(e) =>
              setDropCount(Math.max(1, Number(e.target.value) || 1))
            }
            className="px-3 py-1.5 rounded-md bg-background border text-sm w-24"
          />
        </label>

        <label className="text-xs text-muted-foreground flex flex-col gap-1">
          Silent for (s)
          <input
            type="number"
            min={1}
            value={silentSeconds}
            onChange={(e) =>
              setSilentSeconds(Math.max(1, Number(e.target.value) || 1))
            }
            className="px-3 py-1.5 rounded-md bg-background border text-sm w-24"
          />
        </label>
      </div>

      <div className="flex flex-wrap gap-2">
        <ActionButton
          label={`Drop next ${dropCount} ACK${dropCount === 1 ? "" : "s"}`}
          tag="RR3"
          busy={busy === "DROP_ACKS"}
          onClick={() => fire("DROP_ACKS", { count: dropCount })}
        />
        <ActionButton
          label="Force next JobResult INCOMPLETE"
          tag="RR2"
          busy={busy === "NEXT_INCOMPLETE"}
          onClick={() => fire("NEXT_INCOMPLETE")}
        />
        <ActionButton
          label={`Take offline (${silentSeconds}s)`}
          tag="RR1"
          busy={busy === "GO_SILENT"}
          onClick={() => fire("GO_SILENT", { duration_s: silentSeconds })}
        />
      </div>

      {feedback && (
        <div
          className={`text-xs rounded p-2 ${
            feedback.ok
              ? "bg-green-50 text-green-800 border border-green-200"
              : "bg-red-50 text-red-800 border border-red-200"
          }`}
        >
          {feedback.text}
        </div>
      )}

      <p className="text-[11px] text-muted-foreground">
        Stations must opt in with{" "}
        <code>mqtt_client.enable_fault_injection()</code>. Dashboard
        publishes to{" "}
        <code>AAUSmartLab/&lt;line&gt;/&lt;resource&gt;/TestInjection</code>;
        the controller then sees the failure through its normal
        detection paths (watchdog probe, CMD ACK timeout, JobResult
        INCOMPLETE), and order recovery kicks in.
      </p>
    </section>
  );
}

function ActionButton({
  label,
  tag,
  busy,
  onClick,
}: {
  label: string;
  tag: string;
  busy: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className="px-3 py-2 rounded-md border bg-background hover:bg-muted text-sm font-medium disabled:opacity-50 flex items-center gap-2"
    >
      <span className="text-[10px] font-bold uppercase text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
        {tag}
      </span>
      {busy ? "Sending…" : label}
    </button>
  );
}

function describe(
  command: Command,
  extra: Partial<{ count: number; duration_s: number }>,
): string {
  switch (command) {
    case "DROP_ACKS":
      return `Will drop next ${extra.count} ACK(s). Controller should retransmit; CMD_NO_ACK alarm if exhausted.`;
    case "NEXT_INCOMPLETE":
      return "Next JobResult will return INCOMPLETE. Order recovery should restart.";
    case "GO_SILENT":
      return `Resource is muted for ${extra.duration_s}s. Watchdog should fire RESOURCE_OFFLINE after the probe window.`;
  }
}
