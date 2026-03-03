"use client";
import { calculateOEE } from "@/lib/oee";
import { Card, CardHeader, CardContent, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useEffect, useState } from "react";

export default function DrillingCard() {
  const [oeeData, setOeeData] = useState({ A: 0, P: 0, Q: 0, OEE: 0 });

  useEffect(() => {
    async function fetchLogs() {
      // Hent logs fra din API
      const res = await fetch("/api/execution-log?asset=Drill_Station_1");
      const logs = await res.json();

      // Antag ideal cycle 5 sekunder pr. operation
      const result = calculateOEE(logs, 5);
      setOeeData(result);
    }

    fetchLogs();
  }, []);

  const percent = (val) => Math.round(val * 100);

  return (
    <main className="grid justify-start items-start grid-cols-2 md:grid-cols-3  min-h-screen gap-4 mt-10">
      <Card className="p-4 bg-muted border-background text-primary">
        <CardHeader>
          <CardTitle className="text-center text-lg font-bold">
            Drilling 1
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="font-bold">OEE: {percent(oeeData.OEE)}%</p>
            <Progress value={percent(oeeData.OEE)} />
          </div>
          <div>
            <p>Availability (A): {percent(oeeData.A)}%</p>
            <Progress value={percent(oeeData.A)} />
          </div>
          <div>
            <p>Performance (P): {percent(oeeData.P)}%</p>
            <Progress value={percent(oeeData.P)} />
          </div>
          <div>
            <p>Quality (Q): {percent(oeeData.Q)}%</p>
            <Progress value={percent(oeeData.Q)} />
          </div>
        </CardContent>
      </Card>
      <Card className="p-4 bg-muted border-background text-primary">
        <CardHeader>
          <CardTitle className="text-center text-lg font-bold">
            Drilling 2
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="font-bold">OEE: {percent(oeeData.OEE)}%</p>
            <Progress value={percent(oeeData.OEE)} />
          </div>
          <div>
            <p>Availability (A): {percent(oeeData.A)}%</p>
            <Progress value={percent(oeeData.A)} />
          </div>
          <div>
            <p>Performance (P): {percent(oeeData.P)}%</p>
            <Progress value={percent(oeeData.P)} />
          </div>
          <div>
            <p>Quality (Q): {percent(oeeData.Q)}%</p>
            <Progress value={percent(oeeData.Q)} />
          </div>
        </CardContent>
      </Card>
      <Card className="p-4 bg-muted border-background text-primary">
        <CardHeader>
          <CardTitle className="text-center text-lg font-bold">
            Drilling 2
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="font-bold">OEE: {percent(oeeData.OEE)}%</p>
            <Progress value={percent(oeeData.OEE)} />
          </div>
          <div>
            <p>Availability (A): {percent(oeeData.A)}%</p>
            <Progress value={percent(oeeData.A)} />
          </div>
          <div>
            <p>Performance (P): {percent(oeeData.P)}%</p>
            <Progress value={percent(oeeData.P)} />
          </div>
          <div>
            <p>Quality (Q): {percent(oeeData.Q)}%</p>
            <Progress value={percent(oeeData.Q)} />
          </div>
        </CardContent>
      </Card>
      <Card className="p-4 bg-muted border-background text-primary">
        <CardHeader>
          <CardTitle className="text-center text-lg font-bold">
            Drilling 2
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="font-bold">OEE: {percent(oeeData.OEE)}%</p>
            <Progress value={percent(oeeData.OEE)} />
          </div>
          <div>
            <p>Availability (A): {percent(oeeData.A)}%</p>
            <Progress value={percent(oeeData.A)} />
          </div>
          <div>
            <p>Performance (P): {percent(oeeData.P)}%</p>
            <Progress value={percent(oeeData.P)} />
          </div>
          <div>
            <p>Quality (Q): {percent(oeeData.Q)}%</p>
            <Progress value={percent(oeeData.Q)} />
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
