# CLAUDE.md — AAS Configurator

Full reference docs: `made-react-app/CONFIGURATOR_DOCUMENTATION.md`

---

## Keeping this file up to date

**When we add or change something non-obvious in the configurator, update this file before ending the session.** This includes: new submodel types, new field behaviours, changes to the generation pipeline, new YAML conventions, new API routes, or any design decision that would not be immediately clear from reading the code cold. Small additions here save a full re-discovery next session.

---

## Repo layout (two roots)

The configurator spans two directories. YAML lives in `Implementation2.0/`; the Next.js app lives in `made-react-app/`.

| What | Path |
|---|---|
| Shell templates | `Implementation2.0/ClassesAndBuilderMethods/BaSyx_AAS_Generator/shell_templates/*.yaml` |
| Submodel templates | `Implementation2.0/ClassesAndBuilderMethods/BaSyx_AAS_Generator/submodel_templates/*.yaml` |
| Shell presets | `Implementation2.0/ClassesAndBuilderMethods/BaSyx_AAS_Generator/shell_presets/*.yaml` |
| Form renderer | `made-react-app/components/aas-configurator/FieldRenderer.tsx` |
| Type definitions | `made-react-app/components/aas-configurator/types.ts` |
| Main page | `made-react-app/app/aas-configurator/page.tsx` |
| API routes | `made-react-app/app/api/aas-configurator/` |

---

## IRI scheme

```
https://aausmartlab.org/Shells/{Category}/{Type}/{Name}
```

Example: `https://aausmartlab.org/Shells/Component/Fuse/Fuse_16A_SB`

---

## Generation pipeline

Form data → `POST /api/aas-configurator/generate` → Python script `form_to_aas.py` → BaSyx-compatible AAS Environment JSON.

The Python script lives inside `BaSyx_AAS_Generator/`. Its **absolute path must be configured in the UI Settings panel** before generation works — it is stored server-side via `POST /api/aas-configurator/config` and will differ per machine. If generation fails with a spawn error, check this setting first.

---

## BOP capability extraction (non-obvious)

When a BOP process step uses a declared operation (from the template's `operations` map), capability parameters are rendered **inline** inside the BOP form. At generation time (`resolveBopForGeneration` in `page.tsx`), they are:

1. Stripped from the BOP step.
2. Written to a **separate capability submodel**.
3. Replaced in the step with a `RequiredCapabilityRef` pointing to that submodel.

Touching BOP or capability templates without knowing this will produce unexpected output. The capability template file is declared on the operation in the BOP submodel template's `operations` map.

---

## `extensible: true` collections

Collections with `extensible: true` in the submodel template show an "Add entry" button in the UI. The `entry_template` field on the collection controls the `id_short` naming pattern for each new entry (e.g. `{Description}_{N}`).

---

## BOM entry granularity rule

`Quantity` on a BOM entry is informational only. If individual components will each need a separate `ComponentInstanceRef` (tracked individually in production), they **must be separate entries** — one per physical item, each with `Quantity: 1`. A single entry with `Quantity: 2` cannot hold two distinct instance refs.

---

## `ProductFamilyRef` vs `ComponentInstanceRef`

- **`ProductFamilyRef`** — set at design time; points to the type/family shell (the "what kind of thing").
- **`ComponentInstanceRef`** — left empty at creation; filled during production when the specific physical instance is known.

---

## AAS Inventory (PostgreSQL)

Uploaded shells are tracked in a PostgreSQL table `aas_inventory` using the shared pool in `lib/db.ts`. The table is created automatically on first request (`CREATE TABLE IF NOT EXISTS`). The shared type and SQL live in `lib/inventory.ts`.

| Route | Method | Purpose |
|---|---|---|
| `/api/inventory` | GET | List all inventory items |
| `/api/inventory` | POST | Add one item (shell IRI as `id`) |
| `/api/inventory?id=<encoded>` | DELETE | Remove one item by IRI |
| `/api/inventory/sync` | POST | Fetch all shells from a BaSyx server → bulk insert |

**How a component enters inventory:** after a successful upload in the AAS Configurator (`uploadToBaSyx` in `app/aas-configurator/page.tsx`), a fire-and-forget `POST /api/inventory` is made with the shell ID, name, category, shell type name, and server URL.

**Sync from server:** `POST /api/inventory/sync` with `{ serverUrl }` fetches `GET /shells?limit=100` from the AAS server, parses category and name out of the IRI path segments, and inserts with `ON CONFLICT (id) DO NOTHING`.

## AAS Orders

`app/aas-orders/page.tsx` is the AAS-facing orders view. It reads from `GET /api/inventory/order`, which groups inventory rows by `order_id` and exposes `placedAt` from `reserved_at`.

When an order is placed through the virtual store, `POST /api/inventory/order` stores `reserved_at = NOW()` and clears `reserved_session` so the timestamp survives as the order placement time.

---

## Virtual Store

`app/virtual-store/page.tsx` — product configurator for the **AAU Mobile Phone**. The BOM slots are hardcoded from `final_product_example.yaml` (5 slots: Bottom Cover, Top Cover, PCB Assembly, Fuse 1, Fuse 2). On page load it fetches `GET /api/inventory` and filters items into each slot using a regex against the IRI path segment (e.g. `/\/Bottom_Cover\//i`). The "Place Order" button is enabled only when all required slots have a selection.

---

## Preset save direction

Presets are not only authored manually as YAML. They can also be **saved back to `shell_presets/`** directly from the Review step in the UI via `POST /api/aas-configurator/presets`. The filename is derived from the preset label (lowercased, spaces replaced with underscores).
