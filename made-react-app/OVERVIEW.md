# made-react-app — Architecture Overview

Next.js 16 App Router app. Acts as both **dashboard** and **MES gateway**:

- **Dashboard** for the manufacturing line — alarms, OEE, scheduling,
  performance, orders, inventory, line topology.
- **Storefront** (`/store`, `/virtual-store`) where customer orders enter
  the system.
- **AAS Configurator** (`/aas-configurator`) — form-based builder for
  AAS shells; spawns Python (`form_to_aas.py`) to do the actual
  generation and upload to BaSyx.
- **API gateway** for everything the React side needs — Postgres queries,
  BaSyx HTTP proxies, MES intake, station fault injection.

For background on the AAS Configurator specifically, see
[`CLAUDE.md`](CLAUDE.md) and [`CONFIGURATOR_DOCUMENTATION.md`](CONFIGURATOR_DOCUMENTATION.md).

---

## 1. Folder map

```
made-react-app/
├── app/                            # App Router pages + API routes
│   ├── (root)/                     # landing
│   ├── dashboard/                  # KPIs + OEE summary
│   ├── alarms/                     # active + history
│   ├── performance/                # per-resource OEE drill-down, recent orders
│   ├── production-monitoring/      # live process view
│   ├── scheduling/                 # dispatch queue + capacity
│   ├── orders/                     # MES order queue
│   ├── store/                      # consumer storefront (Telefon / Pro / Pro Max)
│   ├── virtual-store/              # legacy slot-based storefront
│   ├── inventory-management/       # aas_inventory CRUD + allocate
│   ├── maintainance/               # planned maintenance
│   ├── expenses/                   # spend dashboard
│   ├── line-configuration/         # line topology editor
│   ├── aas-configurator/           # AAS shell form-builder
│   ├── configurator/               # legacy configurator
│   ├── aas-server/                 # raw BaSyx browser
│   ├── aas-orders/                 # AAS-facing orders view
│   ├── resource-control/           # send CMD to stations
│   └── api/                        # see §3
├── components/
│   ├── navbar.tsx                  # top bar + notification bell
│   ├── sidebar.tsx                 # left nav (drives the route list above)
│   ├── header.tsx
│   ├── OEECard.tsx                 # OEE tile, used on /dashboard + /performance
│   ├── PerformanceSidePanel.tsx    # drill-down per resource
│   ├── NotificationSidePanel.tsx   # alarm feed
│   ├── DispatchQueueView.tsx       # /scheduling component
│   ├── ResourceAllocationView.tsx  # /inventory-management component
│   ├── ResilienceTestingPanel.tsx  # fault-injection UI
│   ├── PhoneConfigurator.tsx       # canvas-based product preview for /store
│   ├── alarmCard.tsx
│   ├── aas-configurator/           # form renderer subtree
│   └── ui/                         # radix-based primitives (Button, Dialog, …)
├── lib/
│   ├── db.ts                       # shared pg Pool (the ONE Postgres entry point)
│   ├── inventory.ts                # aas_inventory schema + types (shared with API routes)
│   ├── presetBom.ts                # reads shell_presets/*.yaml at request time (BOM single source of truth)
│   ├── orchestration-snapshot.ts   # types + helpers for the live snapshot the controller publishes
│   ├── useOrchestrationSnapshot.ts # client hook that subscribes to the snapshot
│   ├── mqttPublisher.ts            # server-side MQTT publish (used by /api/resilience/inject)
│   ├── shell-type-utils.ts         # IRI ↔ Category/Type/Name helpers
│   ├── oee.js                      # OEE math
│   ├── process-registry.ts         # capability semanticId → human label
│   ├── aas-config.ts               # reads aas-config.json (machine-local paths)
│   ├── fuseBounds.ts               # storefront price/fuse rules
│   └── resource-inventory.ts       # per-resource inventory helpers
├── public/
│   ├── ProductCardImages/          # canvas layer PNGs for /store (TC*, BC*, PCBF*, ProductCardOriginal)
│   ├── FMSLogo.{png,svg}
│   └── …
├── docker-compose.yml              # Postgres 16, seeded from MES/schema.sql
├── aas-config.json                 # machine-local absolute paths (generator, runner, controller, MES API)
├── CLAUDE.md                       # AAS Configurator quick reference
└── CONFIGURATOR_DOCUMENTATION.md   # AAS Configurator full reference
```

---

## 2. How the app connects to the rest of the system

| External | How | From |
|---|---|---|
| Postgres | `pg.Pool` in `lib/db.ts` | every API route that reads dashboard data |
| BaSyx | `fetch(`${serverUrl}/shells`)` etc. | `app/api/aas/*`, `app/api/inventory/sync`, `lib/presetBom.ts` |
| MES API | `fetch('http://localhost:8000/api/v1/orders')` | server route called from `/store` checkout |
| Python generator | `child_process.spawn(pythonExecutable, ['form_to_aas.py', …])` | `app/api/aas-configurator/generate/route.ts` |
| MQTT broker | `lib/mqttPublisher.ts` | `/api/resilience/inject` (fault injection) |

All four absolute paths used by the spawn routes live in
[`aas-config.json`](aas-config.json) and can be edited from the AAS
Configurator's Settings panel (via `POST /api/aas-configurator/config`).

---

## 3. API routes (`app/api/*`)

| Route | Method | Backed by | Purpose |
|---|---|---|---|
| `/api/aas/shells` | GET | BaSyx | List shells (proxied) |
| `/api/aas-configurator/generate` | POST | spawn Python | Form data → AAS Environment JSON |
| `/api/aas-configurator/upload` | POST | BaSyx | Upload the generated JSON |
| `/api/aas-configurator/upload-templates` | POST | spawn Python | Push submodel templates |
| `/api/aas-configurator/delete-from-server` | DELETE | BaSyx | Remove a shell |
| `/api/aas-configurator/shell-types` | GET | YAML | Lists shell template files |
| `/api/aas-configurator/templates` | GET | YAML | Lists submodel template files |
| `/api/aas-configurator/presets` | GET / POST | YAML | List + save back to `shell_presets/` |
| `/api/aas-configurator/config` | GET / POST | `aas-config.json` | Read/write machine-local paths |
| `/api/inventory` | GET / POST / DELETE | `aas_inventory` | Cached index of uploaded shells |
| `/api/inventory/sync` | POST | BaSyx | Bulk-import shells from a BaSyx server |
| `/api/inventory/order` | GET / POST | `aas_inventory` | Reserve rows for an order |
| `/api/inventory/reserve` | POST | `aas_inventory` | Per-component reservation |
| `/api/inventory/bom-slots` | GET | `lib/presetBom.ts` | Slot list for the storefront |
| `/api/inventory/allocations` | GET | `aas_inventory` | Who's holding what |
| `/api/inventory/resources` | GET | `aas_inventory` | Resources holding inventory |
| `/api/mes/orders` | GET / POST | `mes_orders` + MES API | List queue + accept new orders |
| `/api/mes/stats` | GET | `mes_orders` | Counts per status |
| `/api/metrics/lines` | GET | `state_transitions`, `job_results` | Line-level OEE |
| `/api/metrics/resources` | GET | `state_transitions`, `job_results` | Per-resource + per-actor OEE |
| `/api/alarms` | GET / POST | `alarms` | List + manual create |
| `/api/alarms/summary` | GET | `alarms` | Counts for the navbar badge |
| `/api/resilience/inject` | POST | MQTT publish | Publish `TestInjectionMessage` for fault testing |
| `/api/resilience/clear-stuck` | POST | `mes_orders` | Flip stuck RELEASED rows back to PENDING |
| `/api/oee*` | GET | `state_transitions`, `job_results` | Older OEE endpoints |
| `/api/execution-log` | GET | `order_completions`, `job_results` | Execution history |
| `/api/resource-control` | POST | MQTT publish | Direct CMD to a station from the UI |
| `/api/line-controller` | GET | snapshot subscription | Live orchestration snapshot |
| `/api/line-configurator` | GET / POST | BaSyx | Read/write the Line Controller shell's `LineConfiguration` submodel |
| `/api/configurator` | GET | YAML | Legacy configurator |
| `/api/mes-controller` | POST | MES API | Forward to the MES |
| `/api/assets` | GET | BaSyx | Asset listing |

Every Postgres-touching route goes through the pool in `lib/db.ts`. There
is no second `new Pool(...)` anywhere; if there were, HMR would leak
connections.

---

## 4. Postgres tables the React app reads

The schema itself is owned by
[`Implementation2.0/ClassesAndBuilderMethods/MES/schema.sql`](../Implementation2.0/ClassesAndBuilderMethods/MES/schema.sql)
and is seeded by `docker-compose.yml` on first container start. The
React side only reads + (for `aas_inventory`) writes.

| Table | Read by | Written by |
|---|---|---|
| `alarms` | `/api/alarms`, `/api/alarms/summary` | `psql_bridge` |
| `state_transitions` | `/api/metrics/*`, `/api/oee*` | `psql_bridge` |
| `job_results` | `/api/metrics/*`, `/api/execution-log` | `psql_bridge` |
| `mes_orders` | `/api/mes/*`, `/api/resilience/clear-stuck` | `mes_api`, dispatcher, `/api/resilience/clear-stuck` |
| `order_completions` | `/api/execution-log`, performance panel | `psql_bridge` |
| `aas_inventory` | `/api/inventory*` | `/api/inventory*` (the React app owns this table) |

---

## 5. Live snapshot (`useOrchestrationSnapshot`)

The Line Controller continuously publishes an **orchestration snapshot**
(occupancy + cargo + active orders) to the broker. The React app does
**not** subscribe to MQTT from the browser — instead a server route
maintains a subscription and exposes the latest snapshot to clients. The
`useOrchestrationSnapshot` hook polls that route. This keeps a single
MQTT consumer per snapshot regardless of how many browser tabs are open.

---

## 6. The `/store` flow

1. `app/store/page.tsx` renders three SKUs (1/2/3 fuse) on the page.
2. The product card uses `PhoneConfigurator` to composite layered PNGs
   (`BC{color}.png`, `PCBF{n}.png`, `TC{color}.png`) on a `<canvas>`.
3. On checkout, the page posts to `POST /api/inventory/order` with the
   selected `componentTypeId`s.
4. The route reserves rows in `aas_inventory` (so two concurrent
   shoppers can't claim the same physical instance) and then forwards
   the order to the MES API.
5. The MES API explodes the order into per-product rows in `mes_orders`,
   and from there the dispatcher takes over (see
   [`Implementation2.0/OVERVIEW.md`](../Implementation2.0/OVERVIEW.md)).

Reservation accounting in the storefront is **client-side as well**:
`kitsAvailable()` in `app/store/page.tsx` subtracts what's already in
the cart from `aas_inventory.quantityAvailable`, so the user can't add
two of the same config when only one is in stock.

---

## 7. Development notes

- **Bring up Postgres first** — `docker compose up -d`. The schema is
  loaded only on a fresh volume; to re-apply, `docker compose down -v`
  and bring it up again.
- **Restart `npm run dev` after editing `lib/db.ts`** — HMR doesn't
  reliably rebuild the pool, and stale connections cause silent 500s.
- **Error wrapper:** API routes are wrapped in `withErrorHandling` so a
  thrown error returns JSON `{ error, detail }` rather than an empty
  500. The `detail` line also appears in the dev terminal as `[api]`.
- **Type safety:** the only handwritten schema mirrors are in
  `lib/inventory.ts` and `lib/orchestration-snapshot.ts`. Keep them in
  sync with `MessageStructure.py` when the wire format changes.
- **Path config:** if `npm run dev` fails to spawn the generator, check
  [`aas-config.json`](aas-config.json) — the absolute paths there must
  match your machine.
