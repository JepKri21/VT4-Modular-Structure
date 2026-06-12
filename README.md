# VT4-Modular-Structure

A digital-twin–driven (using AAS), plug-and-produce manufacturing line for the AAU
Smartlab. A customer order placed in the web storefront is turned into
**AAS-described work orders**, queued by the **MES**, dispatched over
**MQTT** to a **Line Controller**, executed by **PackML stations**, and
observed live (alarms, OEE, traceability) through a **Next.js dashboard**.

> AAS describes everything **describable**. MQTT carries everything **happening**.
> PostgreSQL holds the queue + metrics. BaSyx is the AAS server.

---

## Where to read next

| For…                                                                         | Read                                                                                                                                                    |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The big picture — modules, dataflow, ISA-95 placement                        | [`OVERVIEW.md`](OVERVIEW.md)                                                                                                                            |
| Python side — MES, Line Controller (step-by-step flows), Generator, Stations | [`Implementation2.0/OVERVIEW.md`](Implementation2.0/OVERVIEW.md)                                                                                        |
| Line Controller — canonical sequence diagram                                 | [`Implementation2.0/Line_Controller/ARCHITECTURE.md`](Implementation2.0/Line_Controller/ARCHITECTURE.md)                                                |
| React side — pages, API routes, Postgres tables                              | [`made-react-app/OVERVIEW.md`](made-react-app/OVERVIEW.md)                                                                                              |
| AAS Configurator — form-based shell builder                                  | [`made-react-app/CLAUDE.md`](made-react-app/CLAUDE.md) + [`made-react-app/CONFIGURATOR_DOCUMENTATION.md`](made-react-app/CONFIGURATOR_DOCUMENTATION.md) |

---

## Layout

```
VT4-Modular-Structure/
├── Implementation2.0/       Python: AAS generation, MES, Line Controller, stations, bridge
├── made-react-app/          Next.js 16: dashboard, storefront, AAS Configurator, REST API
└── OVERVIEW.md              System overview
```

---

## Prerequisites

| Tool                                            | Why                                           |
| ----------------------------------------------- | --------------------------------------------- |
| **Python ≥ 3.11**                               | Line Controller, MES, AAS generator, stations |
| **Node ≥ 20** + npm                             | Next.js app                                   |
| **Docker**                                      | Postgres 16 (via the included compose file)   |
| **MQTT broker** at `localhost:1883`             | Mosquitto / HiveMQ / etc.                     |
| **BaSyx AAS server** at `http://localhost:8081` | run separately                                |

The Python entrypoints are launched from a shared virtual env (`.venv/`
in the repo root). Activate it before running any Python script:

```bash
source .venv/bin/activate
```

---

## Quick start

```bash
# 1. Postgres (seeded from MES/schema.sql on first boot)
cd made-react-app
docker compose up -d
cd ..

# 2. Start your MQTT broker and BaSyx server (separately)

# 3. Adjust machine-local paths
$EDITOR made-react-app/aas-config.json
#   generatorPath, resourceRunnerPath, lineControllerPath, mesApiPath
#   must all be absolute paths on YOUR machine.

# 4. MES (FastAPI + dispatcher + Postgres bridge in one process)
cd Implementation2.0/ClassesAndBuilderMethods/MES
uvicorn mes_api:app --host 0.0.0.0 --port 8000
# leave running

# 5. Stations — one runner per resource shell
cd Implementation2.0/ProductAndResourceImplementations/Generic_Resource_Runner
python Generic_Resource_Runner.py <shell_iri>
# repeat for each resource on the line

# 6. Line Controller
cd Implementation2.0/Line_Controller
python main.py

# 7. Web app
cd made-react-app
npm install
npm run dev
# → http://localhost:3000
```

Open `/store`, place an order, watch the dashboard update.

---

## What runs where

| Process                 | Default port         | Started by                          |
| ----------------------- | -------------------- | ----------------------------------- |
| Next.js dev server      | 3000 (3001 fallback) | `npm run dev`                       |
| MES FastAPI             | 8000                 | `uvicorn mes_api:app`               |
| MES dispatcher thread   | —                    | inside `mes_api`                    |
| MES psql bridge thread  | —                    | inside `mes_api`                    |
| Line Controller         | —                    | `python main.py`                    |
| Generic Resource Runner | — (one per resource) | `python Generic_Resource_Runner.py` |
| PostgreSQL              | 5432                 | `docker compose up -d`              |
| MQTT broker             | 1883                 | external                            |
| BaSyx AAS server        | 8081                 | external                            |

---

## Common issues

| Symptom                                            | Fix                                                                                                     |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `/api/*` returns empty 500                         | restart `npm run dev` (HMR doesn't rebuild the pg pool); check terminal for `[api]` / `[pg pool]` lines |
| `spawn python ENOENT` from AAS Configurator        | wrong `pythonExecutable` / `generatorPath` in `aas-config.json`                                         |
| Order stuck in RELEASED                            | controller died before publishing OrderCompleted — `POST /api/resilience/clear-stuck`                   |
| Resource UNREACHABLE in the dashboard              | station isn't publishing PackML State; check the Resource Runner log                                    |
| Postgres tables missing                            | first boot didn't see `schema.sql` — `docker compose down -v && docker compose up -d`                   |
| BaSyx 404 on shells the configurator just uploaded | `aas-config.json` points at a different BaSyx server than the dashboard does                            |

---

## License

Course / thesis project — see the AAU Smartlab repository for licensing.
