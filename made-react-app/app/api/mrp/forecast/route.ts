import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

// Moving-average demand forecast per finished product. Looks back at the
// last N weeks of COMPLETED orders, computes the mean weekly production,
// and projects it forward.
//
// Query params:
//   lookback_weeks: int  (default 4) — how many weeks of history feed the avg
//   horizon_weeks:  int  (default 4) — how many weeks ahead to project
//
// Response:
//   {
//     lookback_weeks, horizon_weeks,
//     by_product: [
//       {
//         product_iri, product_name,
//         history: [{week_start, units}, ...],
//         avg_weekly: number,
//         forecast: [{week_start, projected_units}, ...]
//       },
//       ...
//     ]
//   }

interface HistRow {
  product_iri: string;
  product_name: string | null;
  week_start: string;
  units: number;
}

function toMondayUTC(d: Date): Date {
  const m = new Date(
    Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()),
  );
  // 0 = Sunday in JS; ISO week starts Monday.
  const day = m.getUTCDay() || 7;
  if (day !== 1) m.setUTCDate(m.getUTCDate() - (day - 1));
  return m;
}

function addWeeks(d: Date, n: number): Date {
  const c = new Date(d);
  c.setUTCDate(c.getUTCDate() + 7 * n);
  return c;
}

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const lookback = Math.max(
    1,
    Math.min(52, Number(searchParams.get("lookback_weeks") ?? "4")),
  );
  const horizon = Math.max(
    0,
    Math.min(26, Number(searchParams.get("horizon_weeks") ?? "4")),
  );

  // History: weekly aggregate of completed orders bucketed by product.
  // `product_ref` on order_completions is the finished-product instance
  // IRI; we strip the UUID tail to get the type IRI.
  const sql = `
    WITH history AS (
      SELECT
        date_trunc('week', completed_at)::date AS week_start,
        regexp_replace(
          product_ref,
          '[-_][0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$',
          ''
        ) AS product_iri,
        COUNT(*)::int AS units
      FROM order_completions
      WHERE status = 'COMPLETED'
        AND product_ref IS NOT NULL
        AND completed_at >= NOW() - ($1::int * INTERVAL '7 days')
      GROUP BY 1, 2
    )
    SELECT
      h.product_iri,
      m.name AS product_name,
      h.week_start::text AS week_start,
      h.units
    FROM history h
    LEFT JOIN mrp_materials m ON m.component_type_iri = h.product_iri
    ORDER BY h.product_iri, h.week_start
  `;
  const res = await pool.query<HistRow>(sql, [lookback]);

  // Group by product.
  const byProduct = new Map<
    string,
    { product_name: string | null; history: HistRow[] }
  >();
  for (const row of res.rows) {
    if (!byProduct.has(row.product_iri)) {
      byProduct.set(row.product_iri, {
        product_name: row.product_name,
        history: [],
      });
    }
    byProduct.get(row.product_iri)!.history.push(row);
  }

  // Build forecast for each product.
  const today = toMondayUTC(new Date());
  const out = [];
  for (const [iri, { product_name, history }] of byProduct) {
    const total = history.reduce((s, r) => s + r.units, 0);
    const avg = lookback > 0 ? total / lookback : 0;
    const forecast = [];
    for (let i = 1; i <= horizon; i++) {
      forecast.push({
        week_start: iso(addWeeks(today, i)),
        projected_units: Math.round(avg),
      });
    }
    out.push({
      product_iri: iri,
      product_name,
      history,
      avg_weekly: +avg.toFixed(2),
      forecast,
    });
  }

  return NextResponse.json({
    lookback_weeks: lookback,
    horizon_weeks: horizon,
    by_product: out,
  });
}
