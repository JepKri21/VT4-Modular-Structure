# Uncommitted Changes — Summary

**Branch:** `NextJSAppV2`
**Generated:** 2026-06-16

This document describes all work currently uncommitted in the working tree. The changes fall into **five themes**:

1. **Parameter-aware line selection (Phase 2)** — the MES now validates that a line can actually *run* a work order's parameters, not just that it offers the right capability *types*, backed by an identity-`semanticId` migration of the AAS data model.
2. **Live shuttle scaling** — add/retire transport shuttles from the UI at runtime, with a cargo-safe drain protocol so a part is never stranded on a shuttle that is leaving.
3. **Webshop batch resolution fixes** — a multi-product order no longer has its siblings disrupted when one unit is cancelled, fails, or completes.
4. **Robustness fixes** — Postgres connection resilience, a scheduler commit-retry deadlock fix, instance re-resolution on retry, and a PackML command-queuing fix for an intermittent transport stall.
5. **Environment/config** — local `aas-config.json` paths, removed a stray laptop-specific file.

---

## 1. Parameter-Aware Line Selection (Phase 2)

Previously the MES selected a production line purely by matching **capability types** (e.g. "this line offers Drilling"). Now it also checks that the line's offered capability **accepts the step's parameters** — value ranges, supported components, allowed materials, and the input→output transformation. A line whose drill exists but cannot reach the requested hole diameter is now rejected at selection time in the MES, instead of failing later in the Line Controller.

### Data-model migration: identity `semanticId`s

The core enabler is giving each parameter a **distinct identity `semanticId`** instead of sharing a *unit* semanticId.

- **Before:** `Length`, `Width`, `Height` all carried `…/Semantics/mm`; `HoleDiameter`, `DrillDepth`, `XPos`, `YPos` also shared `…/Semantics/mm`. The shared unit semanticId could not identify a parameter.
- **After:** each parameter carries `…/Semantics/Parameter/<idShort>` (e.g. `…/Semantics/Parameter/HoleDiameter`), and the unit (`mm`, `gram`) moves to a `unit` ConceptQualifier on the element.

**Template/data files updated:**
- `submodel_templates/drilling_capability_offered.yaml`, `drilling_capability_required.yaml` — `HoleDiameter`, `DrillDepth`, `XPos`, `YPos` get identity semanticIds + `unit` qualifiers.
- `submodel_templates/product_properties.yaml` — `Length`/`Width`/`Height`/`Weight` get identity semanticIds.
- `submodel_templates/assemble_capability_offered.yaml`, `assemble_capability_required.yaml`, `handoff_capability_offered.yaml`, `transport_capability_offered.yaml` — same treatment.
- `shell_templates/*` and `shell_presets/*` — `AllowedMaterials` extended (e.g. PETG added), and the `CapabilityReference` link renamed (see below).

### Rename: `CapabilityReference` → `CapabilitySubmodelReference`

In the `ServiceOffered` submodel, the link to a resource's detailed `OfferedCapability` submodel was named `CapabilityReference` — the same name the work-order ProcessStep uses for its capability *type*. It is renamed to **`CapabilitySubmodelReference`** to match the resource's `Skills` submodel and remove the overload.

- `submodel_templates/service_offered.yaml` — element renamed (semanticId too).
- `shell_presets/production_line_1.yaml` and others — every `CapabilityReference` key renamed.
- `made-react-app/components/configurator/lib/aasExport.ts` — the configurator now exports `CapabilitySubmodelReference`.
- Readers fall back to the legacy `CapabilityReference` name so un-regenerated data still resolves.

### New: in-place migration script

- **`ClassesAndBuilderMethods/MES/migrate_capability_semantics.py`** (new) — brings already-uploaded AAS submodels in line with the Phase 2 templates *without changing their IRIs* (so UUID'd resource shells keep working). Adds identity semanticIds + `unit` qualifiers to capability parameter leaves and renames `CapabilityReference` → `CapabilitySubmodelReference` in `ServiceOffered`. **Idempotent** and **dry-run by default** (`--apply` to write).
- **`ClassesAndBuilderMethods/MES/migration_backup_20260614T075151Z.json`** (new) — a backup snapshot produced by a migration run.

### New: MES-side parameter matcher

- **`ClassesAndBuilderMethods/MES/capability_param_matcher.py`** (new) — a dict-based mirror of the Line Controller's `capability_matcher`, operating on the plain AAS JSON returned by `basyx_client`. Matching is **collision-aware**: a work-order leaf matches an offered leaf by identity `semanticId` when exactly one offered leaf carries it, otherwise by `idShort` (+ `PARAMETER_ALIASES`). This makes the migration **incremental** — it works on both pre- and post-migration data. Matching is **permissive** (a missing range / unreadable detail submodel / unconstrained dimension = "no constraint"), and every check records which path it took; a `strict` flag turns permissive fallbacks into hard failures for tests.

### `line_selector.py` rewrite

`ClassesAndBuilderMethods/MES/line_selector.py` is rewritten from type-only matching to **two-level** selection:
1. **Capability type** — line must offer all required types.
2. **Parameters** — delegated to `capability_param_matcher.match_step`; the detail `OfferedCapability` submodel is fetched lazily (and cached per line). Transformation Input/OutputTypes (ingredient IDs) are resolved to component *type* IRIs via the work order's ingredient map before comparison.

Failure messages now report per-line, per-dimension reasons. A `strict=True` flag is threaded through for tests.

### Line Controller matcher updates

- **`Line_Controller/capability_matcher.py`** — `_check_parameters` now matches each leaf by unique identity `semanticId` first, falling back to `idShort`. `_flatten_step_params` returns `(value, semanticId)` tuples; new `_unique_semantic_index` excludes shared semanticIds (so pre-migration `…/mm` data still falls back to name).
- **`Line_Controller/product_property_matcher.py`** — same identity-`semanticId`-with-name-fallback logic for product/component property matching. Adds **material basename comparison** so a work order carrying the canonical IRI (`…/Materials/ABS`) matches a component storing the bare name (`ABS`). Semantic-mismatch check now only fires on the name-fallback path.
- **`Line_Controller/resource_manager.py`** — `parse_*` now promotes a Property carrying `range_min`/`range_max` qualifiers into a `RangeElement` (e.g. `HoleDiameter min=1 max=20`), so the matcher's range check applies instead of the value silently passing as unconstrained.
- **`ClassesAndBuilderMethods/MES/workorder_builder.py`** — emits the canonical material IRI (`…/Materials/<name>`) and per-dimension identity semanticIds (`…/Semantics/Parameter/<dim>`) instead of the shared unit semanticId.

### Tests (new)

- `ClassesAndBuilderMethods/MES/tests/test_capability_param_matcher.py`
- `ClassesAndBuilderMethods/MES/tests/test_line_selector.py`
- `Line_Controller/tests/test_capability_matcher_semantic.py`
- `Line_Controller/tests/test_product_property_matcher.py`

---

## 2. Live Shuttle Scaling (add / cargo-safe retire)

A new end-to-end feature to change the number of transport shuttles on a transport resource **at runtime**, from the UI, without restarting anything.

### UI

- **`made-react-app/components/ShuttleStepper.tsx`** (new) — shared `+ / −` control for shuttle count. `add` writes the AAS and pings `ReloadConfig`; `retire` asks the Line Controller to drain a shuttle cargo-safely.
- **`made-react-app/app/api/resource-control/shuttles/route.ts`** (new) — backend for the stepper (add/retire/count).
- **`made-react-app/app/api/resource-control/route.ts`** — transport resources now report `isTransport` + `shuttleCount` (read from the `Transport` skill's `Actors` list).
- **`made-react-app/app/resource-control/page.tsx`** — renders the stepper on transport cards; also adds **stick-to-bottom** log scrolling for the MES log modal (only follow new output while the user is parked at the bottom).
- **`made-react-app/components/configurator/Inspector.tsx`** — shows the stepper on transport shells in the line configurator.

### Cargo-safe retire protocol (backend)

The hard part is removing a shuttle **without stranding a part on it**. A new draining protocol handles this:

- **`InformationModels/MessageStructure.py`** — new `RetireShuttleMessage` (resource IRI + actor name).
- **`Line_Controller/main.py`** — subscribes to `…/Controller/RetireShuttle`; bounces the request onto the asyncio loop via `request_retire`.
- **`Line_Controller/config_reload.py`** — the coordinator:
  - `request_retire` picks a **victim** shuttle: prefers an idle+empty, highest-numbered actor (matching the UI's "remove the last shuttle" intent) so removal usually completes immediately; falls back to draining the requested (busy) shuttle only if the whole fleet is occupied.
  - The victim is excluded from new picks at once and dropped from published capacity, but stays routable for any in-flight order holding it.
  - `finalize_drained` deletes the actor from the AAS **only once it is idle + empty**, then re-pings `ReloadConfig`.
- **`Line_Controller/resource_manager.py`** — new `_draining_actors` set + `mark_actor_draining` / `is_actor_draining` / `discard_actor_drain`.
- **`Line_Controller/occupancy_manager.py`** — new `actor_busy()` (inverse of `is_available`) for the per-shuttle drain gate.
- **`Line_Controller/aas_writer.py`** — new `remove_actor_from_skills()`: read-modify-PUT of the whole `Skills` submodel to drop an actor from every skill's `Actors` list (index-agnostic, atomic, never raises).
- **`Line_Controller/scheduler.py`** — actor-picking skips any draining shuttle (no new cargo, not even a reuse fallback).
- **`Line_Controller/orchestration_snapshot.py`** — exposes `draining` per actor so the UI can badge a "retiring" shuttle.
- **`Line_Controller/capacity` publishing (`config_reload.py`)** — excludes draining actors from the published transport ceiling so the MES stops over-releasing.

### Live re-spawn on the resource side

- **`MQTT/ResourceMQTT.py`** — new `register_absolute_subscriber()` for cross-namespace topics (e.g. line-level `Controller/ReloadConfig`), re-subscribed on every reconnect.
- **`Generic_Resource_Runner/Generic_Resource_Runner.py`** — on a `ReloadConfig` ping, `reconcile_actors()` re-reads the `Skills` submodel and **spawns new shuttles / drops retired ones without restarting**. A removed actor is only torn down once its own state machine is IDLE (safety net).

### Test (new)

- `Line_Controller/tests/test_shuttle_scaling.py`

---

## 3. Webshop Batch Resolution Fixes

A multi-product webshop order fans out into several MES units sharing one `webshop_id`. The old logic could disrupt siblings when one unit changed state.

- **`ClassesAndBuilderMethods/MES/dispatcher.py`** — `_notify_webshop_if_batch_complete` + `_cancel_webshop_on_final_abort` are replaced by a single `_resolve_batch_if_terminal(order_id, unit_terminal)`. It resolves the **whole** webshop order only once **every** unit of the batch is terminal:
  - all COMPLETED → fulfil the order;
  - mixed (some done, some failed) → close it; produced units stay consumed, the unproduced units' reservation is released;
  - all failed → close it; full reservation released.
  - Idempotent and safe for lone (no-batch) orders.
- **`ClassesAndBuilderMethods/MES/queue_manager.py`** — new `batch_has_active_siblings(order_id)` (any sibling still PENDING/RELEASED).
- **`made-react-app/app/api/mes/orders/[order_id]/route.ts`** — cancelling one unit now cancels **only that unit**; the webshop order / reservation / shell cleanup only happens once **no** sibling is still active. Lone orders cancel immediately as before.

---

## 4. Robustness Fixes

### Postgres connection resilience
- **`ClassesAndBuilderMethods/MES/psql_bridge.py`** — new `connect_and_init()` retries connect+schema with capped exponential backoff (`DB_RETRY_MAX_S`, default 30s) instead of letting one `OperationalError` kill the daemon thread.
- **`ClassesAndBuilderMethods/MES/queue_manager.py`** — `init()` retries with backoff; `_connect()` now **validates a cached connection** with a cheap `SELECT 1` (+ rollback) and rebuilds it on failure, fixing the "dead socket but `.closed == 0`" case after a Postgres restart/idle-timeout.

### Scheduler commit-retry deadlock
- **`Line_Controller/scheduler.py`** — `try_commit` is all-or-nothing, so a shuttle picked at plan time could be stolen before commit, pinning the order to it forever (a circular-wait deadlock when also holding a scarce assembler). Fix: on a blocked commit, roll the step back to `PENDING` and re-plan (re-pick a free shuttle), bounded by `PLAN_RETRY_BUDGET` via a new `_commit_retry_counts`. New test `Line_Controller/tests/test_commit_retry_deadlock.py`.

### Instance re-resolution on retry
- **`Line_Controller/scheduler.py`** — `_resolve_input_instance` now validates that a bound instance still physically exists before reusing it (a Retrieve on a prior failed attempt empties the storage slot). New `_has_available_instance` distinguishes a consumed raw storage part (other stock exists → switch to a fresh instance) from an in-flight sub-assembly (no replacement → keep the binding). The storage-fallback path now re-resolves by the ingredient's declared **type** rather than a possibly-instance IRI.

### PackML command queuing (intermittent transport stall)
- **`Generic_Resource_Runner/Generic_Resource_Runner.py`** — a START arriving while an actor is still COMPLETING/RESETTING is invalid in PackML and was silently dropped, making the controller wait out its full 60s job timeout (the Retrieve→Handoff stall). New `dispatch_or_queue()` runs a START now if IDLE, or buffers it in `_pending_commands`; `idle()` drains it on return to IDLE. STOP/ABORT clear the buffer.

---

## 5. Environment / Config

- **`made-react-app/aas-config.json`** — local generator/runner/controller/MES paths switched from a macOS path to this Windows machine's paths.
- **`ClassesAndBuilderMethods/MES/orders.json`** — local order data (test orders).
- **Deleted:** `made-react-app/lib/shell-type-utils-Jeppes_Bærbar.ts` — a stray laptop-specific duplicate file removed.

---

## File Change Index

### New files
| File | Purpose |
|------|---------|
| `ClassesAndBuilderMethods/MES/capability_param_matcher.py` | MES-side dict parameter matcher |
| `ClassesAndBuilderMethods/MES/migrate_capability_semantics.py` | In-place AAS Phase-2 migration script |
| `ClassesAndBuilderMethods/MES/migration_backup_20260614T075151Z.json` | Migration backup snapshot |
| `ClassesAndBuilderMethods/MES/tests/test_capability_param_matcher.py` | Tests |
| `ClassesAndBuilderMethods/MES/tests/test_line_selector.py` | Tests |
| `Line_Controller/tests/test_capability_matcher_semantic.py` | Tests |
| `Line_Controller/tests/test_commit_retry_deadlock.py` | Tests |
| `Line_Controller/tests/test_product_property_matcher.py` | Tests |
| `Line_Controller/tests/test_shuttle_scaling.py` | Tests |
| `made-react-app/components/ShuttleStepper.tsx` | Shuttle +/- UI control |
| `made-react-app/app/api/resource-control/shuttles/route.ts` | Shuttle add/retire/count API |

### Modified — backend (Python)
`InformationModels/MessageStructure.py`, `MES/dispatcher.py`, `MES/line_selector.py`, `MES/orders.json`, `MES/psql_bridge.py`, `MES/queue_manager.py`, `MES/workorder_builder.py`, `MQTT/ResourceMQTT.py`, `Line_Controller/aas_writer.py`, `capability_matcher.py`, `config_reload.py`, `main.py`, `occupancy_manager.py`, `orchestration_snapshot.py`, `product_property_matcher.py`, `resource_manager.py`, `scheduler.py`, `Generic_Resource_Runner/Generic_Resource_Runner.py`

### Modified — AAS templates/presets (YAML)
`shell_presets/drilling_station.yaml`, `production_line_1.yaml`; `shell_templates/assembly_module.yaml`, `drilling_station.yaml`, `storage_module.yaml`, `transport_station.yaml`; `submodel_templates/assemble_capability_offered.yaml`, `assemble_capability_required.yaml`, `drilling_capability_offered.yaml`, `drilling_capability_required.yaml`, `handoff_capability_offered.yaml`, `product_properties.yaml`, `service_offered.yaml`, `transport_capability_offered.yaml`

### Modified — frontend (Next.js)
`aas-config.json`, `app/api/mes/orders/[order_id]/route.ts`, `app/api/resource-control/route.ts`, `app/resource-control/page.tsx`, `components/configurator/Inspector.tsx`, `components/configurator/lib/aasExport.ts`

### Deleted
`made-react-app/lib/shell-type-utils-Jeppes_Bærbar.ts`
