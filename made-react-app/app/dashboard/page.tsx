"use client";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { TrendingDown, TrendingUp } from "lucide-react";
import AlarmCard from "@/components/alarmCard";
import { useEffect, useState } from "react";

const Dashboard = () => {
  const targetValue = 80; // Example target value for OEE
  const currentOEE = 75;
  const previousOEE = 56;
  const diff = currentOEE - previousOEE;

  const [alarms, setAlarms] = useState({
    active: 0,
    warnings: 0,
    cleared: 0,
    recent: 0,
  });

  useEffect(() => {
    fetch("/api/alarms/summary")
      .then((res) => res.json())
      .then((data) => setAlarms(data));
  }, []);

  const handleClick = () => {
    alert("Kortet blev klikket!");
  };

  return (
    <main>
      <div className="flex">
        <Card
          className="relative cursor-pointer flex flex-col bg-muted p-10 min-w-100 justify-between"
          onClick={handleClick}
        >
          <div className="flex items-center">
            {/* LOGO and Name for metric e.g. OEE */}
            <div className="flex items-center gap-3">
              {/* <TrendingUp className="text-primary" size={24} /> */}
              {currentOEE >= targetValue ? (
                <TrendingUp className="text-primary mb-1" size={24} />
              ) : (
                <TrendingDown className="text-primary mb-1" size={24} />
              )}
              <h2 className="text-primary text-md font-md">OEE</h2>
            </div>
            <h1 className="absolute inset-x-0 flex text-primary justify-center pointer-events-none font-bold">
              DRILLING 1
            </h1>
          </div>
          {/* Progress sektion */}
          <div className="mt-2">
            <div className="flex justify-center items-end mb-2 gap-2">
              <h1 className="text-lg text-primary font-3xl font-bold">
                {currentOEE}
              </h1>
              {currentOEE >= targetValue ? (
                <TrendingUp className="text-green-500 mb-1" size={28} />
              ) : (
                <TrendingDown className="text-red-500 mb-1" size={28} />
              )}
            </div>

            {/* Container til Progress Bar og Target Marker */}
            <div className="relative w-full h-4 flex items-center">
              <Progress value={currentOEE} className="w-full h-2" />

              {/* Target Cirkel */}
              <div
                className="absolute w-3 h-3 border-2 border-primary bg-muted rounded-full shadow-sm z-10"
                style={{
                  left: `${targetValue}%`,
                  transform: "translateX(-50%)",
                }}
                title={`Target: ${targetValue}%`}
              />
            </div>
          </div>
          <div className="flex items-center gap-8">
            {/* LEFT SIDE */}
            <div className="flex-1 flex flex-col items-start justify-start">
              <p className="text-[10px] uppercase font-semibold text-muted-foreground">
                {/* Calculate % ahead / behind target */}
                {currentOEE > targetValue ? (
                  <span className="text-muted-foreground">
                    +{currentOEE - targetValue}% ahead of target
                  </span>
                ) : (
                  <span className="text-muted-foreground">
                    -{targetValue - currentOEE}% behind target
                  </span>
                )}
              </p>
              <p className="text-[10px] font-semibold text-muted-foreground mt-2">
                {/* Calculate Latest Activity */}
                <span className="text-muted-foreground uppercase">
                  Latest Activity: 2h ago
                </span>
              </p>
            </div>
            {/* VERTICAL LINE (Divider) */}
            <div className="w-0.5 rounded-full bg-muted-foreground self-stretch" />

            {/* HØJRE SIDE: Comparison */}
            <div className="flex-1">
              <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider mb-1">
                Compared to previous period
              </p>
              <div className="flex items-baseline gap-2">
                <span className="text-[12px] font-semibold text-primary">
                  {previousOEE}%
                </span>
                <span
                  className={`text-[8px] font-bold ${diff >= 0 ? "text-green-500" : "text-red-500"}`}
                >
                  {diff >= 0 ? `+${diff}` : diff}%
                </span>
              </div>
            </div>
          </div>
        </Card>
      </div>
      <div className="grid grid-cols-3 gap-4">
        <AlarmCard
          title="Active Alarms"
          count={alarms.active}
          color="text-red-500"
        />

        <AlarmCard
          title="Warnings"
          count={alarms.warnings}
          color="text-yellow-500"
        />

        <AlarmCard
          title="Cleared Alarms"
          count={alarms.cleared}
          color="text-green-500"
        />

        <AlarmCard
          title="Recent Alarms"
          count={alarms.recent}
          color="text-blue-500"
        />
      </div>
    </main>
  );
};

export default Dashboard;
