"use client";
import React, { useState, useEffect } from "react";
import OEECard from "@/components/OEECard";

interface OEEItem {
  id: string;
  currentOEE: number;
  previousOEE: number;
  latestActivity: string;
}

// Dummy fetch-funktion, som du kan erstatte med PSQL fetch
const fetchStationOEE = async (
  filter: "line" | "station",
  hoursInterval: number,
): Promise<OEEItem[]> => {
  // TODO: Lav et API endpoint der returnerer OEE per station eller line
  return [
    {
      id: "Drilling_1",
      currentOEE: 75,
      previousOEE: 56,
      latestActivity: "2h ago",
    },
    {
      id: "Drilling_2",
      currentOEE: 82,
      previousOEE: 79,
      latestActivity: "1h ago",
    },
  ];
};

const ProductionMonitoring: React.FC = () => {
  const [filter, setFilter] = useState<"line" | "station">("station");
  const [interval, setInterval] = useState(24);
  const [stations, setStations] = useState<OEEItem[]>([]);

  useEffect(() => {
    const loadData = async () => {
      const res = await fetch(
        `/api/oee-new?filter=${filter}&hours=${interval}`,
      );
      const data = await res.json();
      setStations(data);
    };
    loadData();
  }, [filter, interval]);

  return (
    <div className="p-4">
      {/* Filter Controls */}
      <div className="flex gap-4 mb-4">
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value as "line" | "station")}
          className="border p-1 rounded"
        >
          <option value="station">Station Specific</option>
          <option value="line">Line Specific</option>
        </select>

        <select
          value={interval}
          onChange={(e) => setInterval(Number(e.target.value))}
          className="border p-1 rounded"
        >
          <option value={1}>Last 1 hour</option>
          <option value={8}>Last 8 hours</option>
          <option value={24}>Last 24 hours</option>
          <option value={72}>Last 3 days</option>
          <option value={168}>Last 7 days</option>
        </select>
      </div>

      {/* OEE Cards */}
      <div className="grid grid-cols-1 md:grid-cols-1 lg:grid-cols-2 gap-15">
        {stations.map((station) => (
          <OEECard
            key={station.id}
            stationId={station.id}
            currentOEE={station.currentOEE}
            previousOEE={station.previousOEE}
            latestActivity={station.latestActivity}
          />
        ))}
      </div>
    </div>
  );
};
export default ProductionMonitoring;
