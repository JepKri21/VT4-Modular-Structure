import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import {
  CREATE_COMPONENT_TYPES_TABLE_SQL,
  CREATE_INVENTORY_TABLE_SQL,
  CREATE_ORDERS_TABLE_SQL,
  CREATE_ORDER_ITEMS_TABLE_SQL,
  MIGRATE_COMPONENT_TYPES_SQL,
} from "@/lib/inventory";
import { randomUUID } from "crypto";

type ParsedProperties = {
  material?: string;
  color?: string;
  finish?: string;
  currentRating?: string;
  voltageRating?: string;
  version?: string;
};

function getCollectionValue(
  submodelElements: unknown,
  collectionIdShort: string,
  propertyIdShort: string
): string | undefined {
  if (!Array.isArray(submodelElements)) return undefined;

  const collection = submodelElements.find((element) => {
    const candidate = element as Record<string, unknown>;
    return candidate.idShort === collectionIdShort;
  }) as Record<string, unknown> | undefined;

  if (!collection || !Array.isArray(collection.value)) return undefined;

  const property = collection.value.find((element) => {
    const candidate = element as Record<string, unknown>;
    return candidate.idShort === propertyIdShort;
  }) as Record<string, unknown> | undefined;

  const val = property?.value;
  if (typeof val === "string") return val;
  if (typeof val === "number") return String(val);
  return undefined;
}

function formatAmpere(raw: string | undefined): string | undefined {
  if (!raw) return undefined;
  const n = parseFloat(raw);
  if (isNaN(n)) return raw;
  return `${n % 1 === 0 ? n : n}A`;
}

function formatVolt(raw: string | undefined): string | undefined {
  if (!raw) return undefined;
  const n = parseFloat(raw);
  if (isNaN(n)) return raw;
  return `${n % 1 === 0 ? n : n}V`;
}

async function fetchComponentProperties(base: string, shellId: string): Promise<ParsedProperties> {
  try {
    const submodelId = `${shellId}/Submodel/Properties/0`;
    const encoded = Buffer.from(submodelId).toString("base64url");
    const response = await fetch(`${base}/submodels/${encoded}`);
    if (!response.ok) return {};

    const submodel = (await response.json()) as { submodelElements?: unknown[] };
    const elems = submodel.submodelElements;

    const material = getCollectionValue(elems, "MaterialProperties", "Material");
    const color = getCollectionValue(elems, "MaterialProperties", "Color");
    const finish = getCollectionValue(elems, "MaterialProperties", "Finish");
    const fuseType = getCollectionValue(elems, "ElectricalProperties", "Type");
    const currentRating = formatAmpere(getCollectionValue(elems, "ElectricalProperties", "Current_Rating"));
    const voltageRating = formatVolt(getCollectionValue(elems, "ElectricalProperties", "Voltage_Rating"));

    return {
      material,
      color,
      finish,
      currentRating,
      voltageRating,
      version: fuseType,
    };
  } catch {
    return {};
  }
}

export async function POST(req: NextRequest) {
  const { serverUrl } = (await req.json()) as { serverUrl: string };

  if (!serverUrl) {
    return NextResponse.json({ error: "serverUrl is required" }, { status: 400 });
  }

  const base = serverUrl.replace(/\/$/, "");

  try {
    const res = await fetch(`${base}/shells?limit=100`);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      return NextResponse.json(
        { error: `AAS Server returned ${res.status}: ${text}` },
        { status: 502 }
      );
    }

    const data = (await res.json()) as { result?: unknown[] };
    const rawShells = (data.result ?? (Array.isArray(data) ? data : [])) as Record<string, unknown>[];

    await pool.query(CREATE_COMPONENT_TYPES_TABLE_SQL);
    await pool.query(CREATE_INVENTORY_TABLE_SQL);
    await pool.query(CREATE_ORDERS_TABLE_SQL);
    await pool.query(CREATE_ORDER_ITEMS_TABLE_SQL);
    for (const sql of MIGRATE_COMPONENT_TYPES_SQL) {
      await pool.query(sql);
    }

    // Parse IRI and extract component type info
    const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

    // Count shells per component type
    const typeCounts: Record<string, { category: string; type: string; name: string; count: number; shellId: string }> = {};

    for (const shell of rawShells) {
      const id = (shell.id as string) ?? "";
      if (!id) continue;

      // Extract component type info from IRI
      // Pattern: https://aausmartlab.org/Shells/Component/{Category}/{Type}/{UUID}
      // where {Category} is what we use to group components (e.g., Bottom_Cover, Top_Cover, PCB, Fuse)
      const segments = id.replace("https://aausmartlab.org/Shells/", "").split("/").filter(Boolean);
      const meaningful = segments.filter((s) => !UUID_RE.test(s));
      const category = (meaningful[1] ?? "Unknown").replace(/_/g, " ");
      const type = meaningful[2] ?? "Unknown";
      const name = meaningful[2] ?? meaningful[meaningful.length - 1] ?? "Unknown";
      const componentTypeId = `${meaningful[1]}_${meaningful[2]}`.toLowerCase().replace(/\s+/g, "_");

      if (!typeCounts[componentTypeId]) {
        typeCounts[componentTypeId] = { category, type, name, count: 0, shellId: id };
      }
      typeCounts[componentTypeId].count++;
    }

    let created = 0;
    // For each component type found on the AAS server, ensure it exists and SET inventory to the count
    for (const [componentTypeId, info] of Object.entries(typeCounts)) {
      const properties = await fetchComponentProperties(base, info.shellId);

      // Store the full shell IRI (including UUID) — this is the actual BaSyx address
      // used for property lookups. The WorkOrder ComponentReference uses the type
      // portion (without UUID), derived at WorkOrder build time.
      const typeIri = info.shellId;

      // Ensure component type exists and keep the live properties in sync
      const typeRes = await pool.query(
        `INSERT INTO component_types (id, category, material, color, finish, current_rating, voltage_rating, version, aas_type_iri, name, description, created_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
         ON CONFLICT (id) DO UPDATE SET
           category = EXCLUDED.category,
           material = EXCLUDED.material,
           color = EXCLUDED.color,
           finish = EXCLUDED.finish,
           current_rating = EXCLUDED.current_rating,
           voltage_rating = EXCLUDED.voltage_rating,
           version = EXCLUDED.version,
           aas_type_iri = EXCLUDED.aas_type_iri,
           name = EXCLUDED.name,
           description = EXCLUDED.description
         RETURNING id`,
        [
          componentTypeId, info.category,
          properties.material ?? null, properties.color ?? null,
          properties.finish ?? null, properties.currentRating ?? null, properties.voltageRating ?? null,
          properties.version ?? null,
          typeIri,
          info.name, `Synced from ${base}`,
        ]
      );
      if (typeRes.rows.length > 0) created++;

      // SET inventory to the actual count from AAS server (not increment)
      const invRes = await pool.query(
        `UPDATE inventory SET quantity_available = $1, last_updated = NOW() WHERE component_type_id = $2`,
        [info.count, componentTypeId]
      );

      // If no row was updated, insert a new one
      if (invRes.rowCount === 0) {
        await pool.query(
          `INSERT INTO inventory (component_type_id, quantity_available, quantity_reserved, last_updated)
           VALUES ($1, $2, 0, NOW())`,
          [componentTypeId, info.count]
        );
      }
    }

    return NextResponse.json({
      synced: rawShells.length,
      created,
      updated: Object.keys(typeCounts).length - created,
      message: `Found ${rawShells.length} shell(s) on server, synchronized ${Object.keys(typeCounts).length} component type(s).`,
    });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
