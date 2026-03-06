"use client";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { TrendingDown, TrendingUp } from "lucide-react";

interface OEECardProps {
  stationId: string;
  currentOEE: number;
  previousOEE: number;
  targetValue?: number;
  latestActivity: string;
}

const OEECard: React.FC<OEECardProps> = ({
  stationId,
  currentOEE,
  previousOEE,
  targetValue = 80,
  latestActivity,
}) => {
  const diff = currentOEE - previousOEE;
  const handleClick = () => {
    alert(`Kortet for ${stationId} blev klikket!`);
  };

  return (
    <Card
      className="relative cursor-pointer flex flex-col bg-muted p-10 min-w-100 justify-between"
      onClick={handleClick}
    >
      {/* Header */}
      <div className="flex items-center">
        <div className="flex items-center gap-3">
          {currentOEE >= targetValue ? (
            <TrendingUp className="text-primary mb-1" size={24} />
          ) : (
            <TrendingDown className="text-primary mb-1" size={24} />
          )}
          <h2 className="text-primary text-md font-md">OEE</h2>
        </div>
        <h1 className="absolute inset-x-0 flex text-primary justify-center pointer-events-none font-bold">
          {stationId.toUpperCase()}
        </h1>
      </div>

      {/* Progress */}
      <div className="mt-2">
        <div className="flex justify-center items-end mb-2 gap-2">
          <h1 className="text-lg text-primary font-3xl font-bold">
            {currentOEE}%
          </h1>
          {currentOEE >= targetValue ? (
            <TrendingUp className="text-green-500 mb-1" size={28} />
          ) : (
            <TrendingDown className="text-red-500 mb-1" size={28} />
          )}
        </div>

        <div className="relative w-full h-4 flex items-center">
          <Progress value={currentOEE} className="w-full h-2" />

          <div
            className="absolute w-3 h-3 border-2 border-primary bg-muted rounded-full shadow-sm z-10"
            style={{ left: `${targetValue}%`, transform: "translateX(-50%)" }}
            title={`Target: ${targetValue}%`}
          />
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center gap-8 mt-4">
        <div className="flex-1 flex flex-col items-start justify-start">
          <p className="text-[10px] uppercase font-semibold text-muted-foreground">
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
            <span className="text-muted-foreground uppercase">
              Latest Activity: {latestActivity}
            </span>
          </p>
        </div>

        <div className="w-0.5 rounded-full bg-muted-foreground self-stretch" />

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
  );
};
export default OEECard;
