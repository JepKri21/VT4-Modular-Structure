"use client";

import { useEffect, useState } from "react";
import { Card, CardHeader, CardContent, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

type OEEData = {
  station: string;
  A: number;
  P: number;
  Q: number;
  OEE: number;
  totalParts: number;
};

const stations = ["Drilling_1", "Drilling_2"];

export default function ProductionMonitoringPage() {
  const [mode, setMode] = useState<"station" | "line">("station");
  const [hours, setHours] = useState<number>(24);
  const [data, setData] = useState<OEEData[]>([]);

  useEffect(() => {
    fetchOEE();
  }, [mode, hours]);

  async function fetchOEE() {
    if (mode === "station") {
      const results = await Promise.all(
        stations.map(async (station) => {
          const res = await fetch(`/api/oee?station=${station}&hours=${hours}`);
          return res.json();
        }),
      );
      setData(results);
    } else {
      // Line aggregation
      const res = await fetch(`/api/oee-line?hours=${hours}`);
      const result = await res.json();
      setData([result]);
    }
  }

  const percent = (val: number) => Math.round(val * 100);

  return (
    <main className="p-6 space-y-6">
      {/* FILTER BAR */}
      <div className="flex gap-4 items-center">
        <select
          className="bg-muted px-3 py-2 rounded-md"
          value={mode}
          onChange={(e) => setMode(e.target.value as "station" | "line")}
        >
          <option value="station">Station Specific</option>
          <option value="line">Line Specific</option>
        </select>

        <select
          className="bg-muted px-3 py-2 rounded-md"
          value={hours}
          onChange={(e) => setHours(Number(e.target.value))}
        >
          <option value={1}>Last 1 hour</option>
          <option value={8}>Last 8 hours</option>
          <option value={24}>Last 24 hours</option>
          <option value={168}>Last 7 days</option>
        </select>
      </div>

      {/* CARDS */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {data.map((item) => (
          <Card key={item.station} className="p-4 bg-muted border-background">
            <CardHeader>
              <CardTitle className="text-lg font-bold text-center">
                {item.station}
              </CardTitle>
            </CardHeader>

            <CardContent className="space-y-4">
              <div>
                <p className="font-bold text-xl">OEE: {percent(item.OEE)}%</p>
                <Progress value={percent(item.OEE)} />
              </div>

              <div>
                <p>Availability: {percent(item.A)}%</p>
                <Progress value={percent(item.A)} />
              </div>

              <div>
                <p>Performance: {percent(item.P)}%</p>
                <Progress value={percent(item.P)} />
              </div>

              <div>
                <p>Quality: {percent(item.Q)}%</p>
                <Progress value={percent(item.Q)} />
              </div>

              <div className="text-sm text-muted-foreground">
                Produced parts: {item.totalParts}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
