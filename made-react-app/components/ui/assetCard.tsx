type Asset = {
  id: string;
  idShort: string;
  assetKind?: string;
  globalAssetId?: string;
  submodels?: string[];

  // Fra AssetClassification submodel
  AssetCategory?: string;
  Family?: string;
  Variant?: string;
};

export default function AssetCard({ asset }: { asset: Asset }) {
  return (
    <div className="border rounded-xl p-4 shadow-md bg-blue-400 text-white">
      {/* Title */}
      <h2 className="text-xl font-bold">{asset.idShort}</h2>

      {/* Category Badge */}
      {asset.AssetCategory && (
        <span className="inline-block mt-1 text-xs font-semibold px-2 py-1 bg-blue-200 text-blue-900 rounded">
          {asset.AssetCategory}
        </span>
      )}

      {/* Variant info */}
      {asset.Family && (
        <p className="text-sm mt-2">
          <strong>Family:</strong> {asset.Family}
        </p>
      )}

      {asset.Variant && (
        <p className="text-sm">
          <strong>Variant:</strong> {asset.Variant}
        </p>
      )}

      {/* Global ID */}
      {asset.globalAssetId && (
        <>
          <h4 className="text-sm font-semibold mt-3">Global Asset ID:</h4>
          <p className="text-xs break-all">{asset.globalAssetId}</p>
        </>
      )}

      {/* Submodels */}
      {Array.isArray(asset.submodels) && asset.submodels.length > 0 && (
        <div className="mt-3">
          <h4 className="text-sm font-semibold">Submodels:</h4>
          <ul className="text-xs">
            {asset.submodels.map((sm, index) => (
              <li key={index}>{sm}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
