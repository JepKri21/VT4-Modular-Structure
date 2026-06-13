# System Overview — VT4 Modular Structure

A digital-twin–driven, plug-and-produce manufacturing line for the AAU
Smartlab. A customer order placed in the web storefront is turned into
AAS-described work orders, queued by the MES, dispatched over MQTT to a
**Line Controller**, executed by **PackML stations**, and observed live
(alarms, OEE, traceability) through a **Next.js dashboard**.

The architectural choices that shape the whole system:

| Layer | Tech | Source of truth for… |
|---|---|---|
| Describable things | **AAS (Asset Administration Shell)** on BaSyx | Products, resources, capabilities, line topology, BOMs |
| Things happening | **MQTT** | Commands, states, job results, inventory snapshots, occupancy, cargo, alarms |
| Cross-cutting state | **PostgreSQL** | Alarms, OEE source data, MES order queue, AAS inventory cache |
| Resource state model | **PackML** | Every actor exposes the canonical state machine |

ISA-95 placement: the React app sits at the **MES + dashboard** level, the
Line Controller is the **execution layer**, and stations are the **control
layer**.

---

## 1. Top-level layout

```
VT4-Modular-Structure/
├── Implementation2.0/       ← Python: AAS gen, MES, Line Controller, stations, bridge
│   └── OVERVIEW.md          ← detailed Python-side architecture + flows
├── made-react-app/          ← Next.js 16 app (UI + API routes + Postgres)
│   ├── OVERVIEW.md          ← React-side architecture
│   ├── CLAUDE.md            ← AAS Configurator quick reference
│   ├── CONFIGURATOR_DOCUMENTATION.md
│   └── docker-compose.yml   ← Postgres 16, seeded from MES/schema.sql
├── README.md                ← this folder's orientation + quick start
└── OVERVIEW.md              ← (this file)
```

External services the system expects:

| Service | Default | Provided by |
|---|---|---|
| MQTT broker | `localhost:1883` | Bring your own (Mosquitto, HiveMQ, …) |
| BaSyx AAS server | `http://localhost:8081` | Run separately |
| PostgreSQL 16 | `localhost:5432` | `docker compose up -d` in `made-react-app/` |

---

## 2. The end-to-end customer order flow

```
Customer            Next.js                MES (FastAPI)         Postgres        MQTT broker         Line Controller         Stations
   │                   │                       │                    │                │                    │                    │
   │ open /store       │                       │                    │                │                    │                    │
   │ pick config       │                       │                    │                │                    │                    │
   │ Place Order  ───▶ │ /api/inventory/order  │                    │                │                    │                    │
   │                   │ reserves rows in      │                    │                │                    │                    │
   │                   │ aas_inventory         │                    │                │                    │                    │
   │                   │     │                 │                    │                │                    │                    │
   │                   │ POST /api/v1/orders ──▶ order_processor    │                │                    │                    │
   │                   │                       │  explodes 1×phone  │                │                    │                    │
   │                   │                       │  into N rows in    │                │                    │                    │
   │                   │                       │  mes_orders        │                │                    │                    │
   │                   │                       │  (status=PENDING)  │                │                    │                    │
   │                   │                       │     │              │                │                    │                    │
   │                   │                       │ dispatcher ─ tick ─▶ peek ┐         │                    │                    │
   │                   │                       │                    │  ◀──┘          │                    │                    │
   │                   │                       │ publish WorkOrder ─────────────▶ AAUSmartLab/<line>/MES/WorkOrder              │
   │                   │                       │ set status=RELEASED│                │                    │                    │
   │                   │                       │                    │                │                    │ on_message:        │
   │                   │                       │                    │                │                    │  scheduler.run_order
   │                   │                       │                    │                │                    │       │            │
   │                   │                       │                    │                │                    │ matcher → planner   │
   │                   │                       │                    │                │                    │       │            │
   │                   │                       │                    │                │           publish CMD ─────────────────▶ │
   │                   │                       │                    │                │                    │   PackML run       │
   │                   │                       │                    │                │ ◀── State + JobResult ─────────────────  │
   │                   │                       │                    │                │                    │                    │
   │                   │                       │                    │ ◀── psql_bridge writes alarms, state_transitions,         │
   │                   │                       │                    │     job_results, order_completions                        │
   │                   │                       │                    │                │                    │                    │
   │                   │                       │                    │       publish OrderCompleted ◀──────                       │
   │                   │                       │ dispatcher marks COMPLETED, fills capacity with next PENDING                   │
   │                   │                       │                    │                │                    │                    │
   │ ◀── dashboard polls /api/metrics/* and /api/alarms/summary ──── │                │                                         │
```

Two parallel paths run alongside this:

- **AAS Configurator** (`/aas-configurator` in the React app) spawns Python
  (`form_to_aas.py`, `upload_templates.py`) to build AAS Environment JSON
  from YAML templates and upload to BaSyx. Uploaded shells are mirrored
  into the `aas_inventory` table so the storefront and Line Controller can
  see them.
- **Stations** boot independently with `Generic_Resource_Runner.py`, each
  pointed at its own resource shell. They publish State / JobResult /
  InventoryLevel on their own namespace and consume CMD from the Line
  Controller.

---

## 3. Where each subsystem lives

| Concern | Folder | Entry point |
|---|---|---|
| AAS generation (YAML → JSON, upload to BaSyx) | `Implementation2.0/ClassesAndBuilderMethods/BaSyx_AAS_Generator/` | `form_to_aas.py` (spawned by Next.js) |
| MQTT message schemas (Pydantic v2) | `Implementation2.0/ClassesAndBuilderMethods/InformationModels/MessageStructure.py` | (library) |
| Station MQTT base + PackML | `Implementation2.0/ClassesAndBuilderMethods/MQTT/`, `…/PackML/` | (library) |
| MES order intake + queue + dispatch + bridge | `Implementation2.0/ClassesAndBuilderMethods/MES/` | `mes_api.py` |
| Line Controller orchestration | `Implementation2.0/Line_Controller/` | `main.py` |
| Stations (data-driven runtime) | `Implementation2.0/ProductAndResourceImplementations/Generic_Resource_Runner/` | `Generic_Resource_Runner.py` |
| Web UI + REST API + Postgres | `made-react-app/` | `npm run dev` |
| Postgres schema | `Implementation2.0/ClassesAndBuilderMethods/MES/schema.sql` | seeded by `docker compose up -d` |

For Line-Controller-internal details see
[`Implementation2.0/OVERVIEW.md`](Implementation2.0/OVERVIEW.md) and
[`Implementation2.0/Line_Controller/ARCHITECTURE.md`](Implementation2.0/Line_Controller/ARCHITECTURE.md).
For React app details see
[`made-react-app/OVERVIEW.md`](made-react-app/OVERVIEW.md) and
[`made-react-app/CLAUDE.md`](made-react-app/CLAUDE.md).

---

## 4. Postgres tables (owned by the MES schema)

| Table | Owner | Purpose |
|---|---|---|
| `alarms` | `psql_bridge` | Station + controller alarms, auto-cleared when source goes OK |
| `state_transitions` | `psql_bridge` | Every PackML state change — source for OEE Availability |
| `job_results` | `psql_bridge` | Every JobResult — source for Performance + Quality |
| `mes_orders` | MES API + dispatcher | Order queue with priority + batch grouping + retry state |
| `order_completions` | `psql_bridge` | One row per order leaving the scheduler (COMPLETED or ABORTED) |
| `aas_inventory` | Next.js `lib/inventory.ts` | Cached index of shells uploaded to BaSyx |

---

## 5. Resilience features in code

- **Controller-level retry** (`OrderRecovery`, 3 attempts) — restarts an
  order on `CmdNoAckError` / `TimeoutError` / `RuntimeError`, excluding
  the failed resource on retry.
- **Dispatcher-level retry** (`MES_MAX_ATTEMPTS=2`, 60 s backoff) — requeues
  an `ABORTED` order back to `PENDING` with `next_attempt_at` in the future.
- **Watchdog** (`MQTTClientControllerV2._watch_last_seen_loop`) — flips a
  resource to `UNREACHABLE` if its retained State stops refreshing.
- **Persistent MQTT session** (`clean_session=False`, QoS 1) — work orders
  survive broker restarts.
- **Auto-clearing alarms** — closing the underlying condition closes the
  alarm row (`cleared_at` set).
- **Fault injection** (`/api/resilience/inject`, `TestInjectionMessage`)
  and stuck-row cleanup (`/api/resilience/clear-stuck`) for testing.

---

## 6. Quick start

1. **Postgres:** `cd made-react-app && docker compose up -d`
2. **MQTT broker + BaSyx server:** start your own (e.g. Mosquitto on 1883
   and BaSyx on 8081).
3. **Configure machine-local paths:** open
   [`made-react-app/aas-config.json`](made-react-app/aas-config.json) and
   adjust the four absolute paths (generator, resource runner, line
   controller, MES API) for your machine.
4. **MES API:** `cd Implementation2.0/ClassesAndBuilderMethods/MES &&
   uvicorn mes_api:app --host 0.0.0.0 --port 8000` (this also boots the
   dispatcher and PSQL bridge as daemon threads).
5. **Stations:** for each resource shell you want online, run
   `Generic_Resource_Runner.py` pointed at that shell.
6. **Line Controller:** `python Implementation2.0/Line_Controller/main.py`
7. **Web app:** `cd made-react-app && npm run dev` → http://localhost:3000

Place an order from `/store` to see the whole loop run.
