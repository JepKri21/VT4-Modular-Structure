"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type Asset = {
  id: string;
  idShort: string;
  AssetCategory?: string;
  Family?: string;
  Variant?: string;
};

export default function Dashboard() {
  const [assets, setAssets] = useState<Asset[]>([]);

  useEffect(() => {
    fetch("/api/assets")
      .then((res) => res.json())
      .then((data) => setAssets(data));
  }, []);

  const grouped = groupAssets(assets);

  return (
    <div className=" flex p-10 space-y-12 gap-10 h-screen">
      {["Product", "Resource", "Component"].map((category) => (
        <div key={category}>
          <h1 className="text-2xl font-bold mb-4">{category}</h1>

          <div className="grid grid-cols-3 gap-6">
            {Object.entries(grouped[category] || {}).map(
              ([family, variants]: any) => (
                <FamilyCard
                  key={family}
                  category={category}
                  family={family}
                  variants={variants}
                />
              ),
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function groupAssets(assets: Asset[]) {
  const grouped: any = {};

  for (const asset of assets) {
    const category = asset.AssetCategory || "Uncategorized";
    const family = asset.Family || "No Family";
    const variant = asset.Variant || "No Variant";

    if (!grouped[category]) grouped[category] = {};
    if (!grouped[category][family]) grouped[category][family] = {};
    if (!grouped[category][family][variant])
      grouped[category][family][variant] = [];

    grouped[category][family][variant].push(asset);
  }

  return grouped;
}

function FamilyCard({
  category,
  family,
  variants,
}: {
  category: string;
  family: string;
  variants: any;
}) {
  return (
    <div className="bg-white shadow-md rounded-xl p-6">
      <h2 className="text-lg font-bold mb-4">{family}</h2>

      <div className="space-y-2">
        {Object.keys(variants).map((variant) => (
          <Link
            key={variant}
            href={`/dashboard/${category}/${family}/${variant}`}
            className="block bg-gray-100 rounded p-2 hover:bg-gray-200"
          >
            {variant}
          </Link>
        ))}
      </div>
    </div>
  );
}
