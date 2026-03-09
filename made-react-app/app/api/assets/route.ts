import { NextResponse } from "next/server";

const AAS_BASE_URL = "http://localhost:8081";

function encodeId(id: string) {
  return Buffer.from(id).toString("base64");
}

async function fetchSubmodel(id: string) {
  const encoded = encodeId(id);
  const res = await fetch(`${AAS_BASE_URL}/submodels/${encoded}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

function extractClassification(submodel: any) {
  if (!submodel?.submodelElements) return {};

  const map: any = {};

  for (const el of submodel.submodelElements) {
    map[el.idShort] = el.value;
  }

  return map;
}

export async function GET() {
  const res = await fetch(`${AAS_BASE_URL}/shells`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });

  const data = await res.json();
  const shells = data.result ?? [];

  const enriched = await Promise.all(
    shells.map(async (shell: any) => {
      const submodelIds = shell.submodels?.map((s: any) => s.keys[0].value);

      let classification = {};

      for (const id of submodelIds) {
        if (id.includes("AssetClassification")) {
          const sm = await fetchSubmodel(id);
          classification = extractClassification(sm);
        }
      }

      return {
        id: shell.id,
        idShort: shell.idShort,
        globalAssetId: shell.assetInformation?.globalAssetId,
        assetKind: shell.assetInformation?.assetKind,
        ...classification,
      };
    }),
  );

  return NextResponse.json(enriched);
}
