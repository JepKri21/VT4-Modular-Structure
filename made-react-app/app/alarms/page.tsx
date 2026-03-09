"use client";

import { Button } from "@/components/ui/button";
import { useEffect, useState } from "react";

interface Alarm {
  id: number;
  station_id: string;
  alarm_id: number;
  severity: string;
  triggered_at: string;
  cleared_at: string | null;
  acknowledged: boolean;
}

export default function AlarmsPage() {
  const [alarms, setAlarms] = useState<Alarm[]>([]);

  useEffect(() => {
    fetch("/api/alarms")
      .then((res) => res.json())
      .then((data) => setAlarms(data));
  }, []);

  const acknowledgeAlarm = async (id: number) => {
    await fetch("/api/alarms/acknowledge", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ id }),
    });

    // opdater UI bagefter
    setAlarms((prev) =>
      prev.map((alarm) =>
        alarm.id === id ? { ...alarm, acknowledged: true } : alarm,
      ),
    );
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold uppercase mb-6">Alarms</h1>

      <table className="w-full border">
        <thead>
          <tr className="border-b">
            <th className="text-left p-2">Station</th>
            <th className="text-left p-2">Alarm</th>
            <th className="text-left p-2">Severity</th>
            <th className="text-left p-2">Time</th>
            <th className="text-left p-2">Status</th>
            <th className="text-left p-2">Action</th>
          </tr>
        </thead>

        <tbody>
          {alarms.map((alarm) => (
            <tr key={alarm.id} className="border-b">
              <td className="p-2">{alarm.station_id}</td>
              <td className="p-2">{alarm.alarm_id}</td>

              <td className="p-2">{alarm.severity}</td>

              <td className="p-2">
                {new Date(alarm.triggered_at).toLocaleString()}
              </td>

              <td className="p-2">{alarm.cleared_at ? "Cleared" : "Active"}</td>

              <td className="p-2">
                {alarm.acknowledged ? (
                  <span className="text-card">Acknowledged</span>
                ) : (
                  <button
                    onClick={() => acknowledgeAlarm(alarm.id)}
                    className="text-primary hover:underline"
                  >
                    Acknowledge
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
