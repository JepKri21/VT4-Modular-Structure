# Line Controller — Architecture

This is the runbook for the Line Controller as it stands today. It exists so
the group can see what each module does, how a work order flows through them,
and where to look first when something breaks.

> Source of truth for higher-level design is still `CLAUDE.md`. This file
> covers the **current code** — what actually runs.

---

## 1. The 30-second mental model

```
                              ┌─────────────────────┐
   WorkOrder JSON  ─────────▶ │  WorkOrderHandler   │  BoP steps + dep graph
                              └──────────┬──────────┘
                                         │ get_ready_steps()
                                         ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │                          Scheduler                                │
   │  for each ready BoP step:                                         │
   │    1. CapabilityMatcher  → resources that can run this step       │
   │    2. _resolve_storage_for() → ProductMatcher picks the actual    │
   │                                instance + the storage that has it │
   │    3. _pick_shuttle()    → first free Transport actor that        │
   │                            supports this component+material       │
   │    4. release_sequence_for() → ["Retrieve","Handoff"] vs ["Handoff"]│
   │    5. PreProcessPlanner.plan() → Transport/Retrieve/Handoff steps │
   │    6. execute each step (MQTT CMD ▶ wait JobResult ▶ cargo xfer)  │
   │    7. execute the BoP CMD                                         │
   │                                                                   │
   │  when all BoP steps are COMPLETED:                                │
   │    8. plan_post_process → Handoff/Transport/Store back to storage │
   │    9. aas_writer.write_traceability  → product shell submodel     │
   │   10. publish WorkOrderStatus.COMPLETE                            │
   └────────┬──────────────────┬─────────────────────┬─────────────────┘
            │                  │                     │
   ┌────────┴───────┐  ┌───────┴──────┐    ┌─────────┴─────────┐
   │ ResourceManager│  │ ProductMatcher│   │ OccupancyManager  │
   │  AAS discovery │  │ InventoryIndex│   │ (resource,actor)  │
   │  + reachability│  │ + AAS props   │   │ → order_id, cargo │
   │  + skills/caps │  │ + constraints │   │  + Occupancy MQTT │
   └────────┬───────┘  └───────┬──────┘    └─────────┬─────────┘
            │                  │                     │
            │     ┌────────────┴─────┐               │
            │     │   JobTracker     │               │
            │     │ wait_for(job_id) │               │
            │     └────────┬─────────┘               │
            ▼              ▼                         ▼
        MQTTClientController (V2) ◀── stations: State / JobResult / InventoryLevel
                                  ──▶ Line Controller: CMD / InfoRequest / Occupancy
```

The scheduler does not parse AAS, does not parse MQTT, does not plan transport.
It asks the other modules. Keep it that way when adding logic.

---

## 2. Modules

### `main.py`

Wiring only. Loads the work order, builds every manager, registers the five flat MQTT handlers (`State`, `JobResult`, `InventoryLevel`, `Occupancy`, `Cargo`), and hands the order to `Scheduler.run_order(...)`. The `_product_matcher` global is owned here so the inventory handler can refresh the index on every `InventoryLevel`.

### `workorder_handler.py`

Parses the work order JSON, builds the assembly dependency graph between ingredients, exposes `get_ready_steps()` (recursive ingredient-completeness + per-step `Dependencies`), and per-step state transitions (`PENDING → ASSIGNED → IN_PROGRESS → COMPLETED`). `get_step_execution_info(step_id)` also resolves the ingredient's `ComponentReference` and `Material` from the work order.

### `resource_manager.py`

AAS discovery: walks the BaSyx server for resource shells, reads their Skills / Capability submodels. Holds reachability per shell. Exposes `find_by_capability`, `find_skill_offering`, `actors_for_skill`, `has_handoff`, `get_resource_skills`, `get_capability_parameters`, and the static helper `topic_id_for_iri`.

### `capability_matcher.py`

Filters discovered resources to those that can actually run a given BoP step. Match key is the capability `semanticId`. Validates parameter ranges (flattened across nested collections, with a small alias map), SupportedComponents (compared by type prefix `…/Shells/<Category>/<Type>`), and AllowedMaterials. Returns candidates; never picks.

### `product_property_matcher.py`

Replaces `inventory_manager.py`. `InventoryIndexer` rebuilds an index of held components per `(resource, inventory, slot)` from `controller.shared_handler_variable["inventory"]`. `AASPropertyResolver` fetches normalized property submodels from BaSyx. `ConstraintEvaluator` compares requested-vs-actual `(semanticId, value)`. `ProductMatcher.find_matching_components(type, order_properties)` answers "which storage has the right instance?"

### `transport_planner.py`

Two things share the file:

- `LineConfig` / `parse_line_config` / `load_line_config_from_aas` — reads the `LineConfiguration` submodel from the Line Controller's own shell.
- `LineGraph` does BFS routing through `TransportEdge`s.

`TransportPlanner` is the thin façade the scheduler/planner use: `handoff_position`, `transport_params`, `handoff_params`, `transports_between`, `find_route`.

### `pre_process_planner.py`

Given target + storage + shuttle + a `release_skills` sequence, produces a `PreProcessPlan` of `PreProcessStep`s (`Transport`, `Retrieve`, `Handoff`, `Store`). Implements the **4-case handoff rule** (see the comment block at the top of the file). Each step also carries `cargo_transfers`, the cargo-ledger side effect to apply on success. `plan_post_process(...)` mirrors all of this for finished parts. `release_sequence_for(...)` is a free function that decides whether the source needs `[Retrieve, Handoff]` or just `[Handoff]` — driven by inventory state + the source's advertised skills.

### `job_tracker.py`

Listens for `JobResultMessage` via the shared `controller.shared_handler_variable["job_result"]`. `await tracker.wait_for(job_id, timeout=...)` blocks the scheduler until a station finishes a command (or times out).

### `occupancy_manager.py`

In-memory ledger of `(resource, actor) → order_id` **and** `(resource, actor) → component_reference`. `commit()` / `release()` / `release_one()` for reservations, `set_cargo()` / `clear_cargo()` / `apply_cargo_transfers()` for cargo. Mirrors both via `OccupancyMessage` / `CargoMessage` so observers (and the controller itself, via `handle_occupancy_message` / `handle_cargo_message`) see who's holding what.

### `aas_writer.py`

Writes a `Traceability` submodel back to the product shell after the work order completes, recording which specific component instance was consumed for each ingredient name.

### `scheduler.py`

The orchestration loop. Drives one or more work orders end-to-end using everything above. The only async actor in the system other than the MQTT client.

### `MQTTClientControllerV2.py`

Generic MQTT pump. Discovers each resource's `Communication` submodel (suffixes for `CMD`, `State`, `JobResult`, `InventoryLevel`, `InfoRequest`, …) via `update_information()`, subscribes to every resource's namespace, parses topics into `topic_info`, dispatches by message type to handlers registered with `register_handler()`, publishes outbound via `publish_message(shell_iri, msg)`. `request_data(MessageType)` does an InfoRequest fan-out. Also runs a watchdog (`_watch_last_seen_loop`) that flips a resource UNREACHABLE if its retained State message hasn't refreshed in time.

### `inventory_manager.py` _(deprecated)_

Superseded by `product_property_matcher.py`. The file still exists but `main.py` does not import it; safe to delete once nothing else references it.

---

## 3. One full BoP step — sequence diagram (text)

```text
Scheduler                           MQTT broker            Station(s)
   │                                     │                     │
   │── matcher.match(step) ─────────────▶│   (AAS HTTP query)  │
   │◀── candidates ──────────────────────│                     │
   │                                     │                     │
   │── _resolve_storage_for(ref, ingredient)                   │
   │      └─ ProductMatcher.find_matching_components(          │
   │              type, order_properties)                      │
   │◀── chosen storage IRI + picked_instance                   │
   │      └─ self._traceability[order][ingredient] = …         │
   │                                     │                     │
   │── _pick_shuttle(ref, material)                            │
   │      filters Transport caps + checks Occupancy ledger     │
   │◀── shuttle endpoint                                       │
   │                                     │                     │
   │── release_sequence_for(storage, ref)                      │
   │◀── e.g. ["Retrieve","Handoff"]  (or just ["Handoff"])     │
   │                                     │                     │
   │── planner.plan(...)                                       │
   │◀── PreProcessPlan: ordered steps + cargo_transfers        │
   │                                     │                     │
   │── occupancy.commit(shuttle, target)                       │
   │── publish OccupancyMessage ────────▶│                     │
   │                                     │                     │
   │  ─── pp1: Transport CMD ───────────▶│────────────────────▶│ Shuttle1
   │                                     │◀── State STARTING ──│
   │                                     │◀── State EXECUTE ───│
   │                                     │◀── State COMPLETING─│
   │                                     │◀── JobResult ───────│
   │                                     │◀── State IDLE ──────│
   │  jobs.wait_for(job_id) ✓                                  │
   │                                                           │
   │  ─── pp2: Retrieve CMD ────────────▶│────────────────────▶│ Storage UR5
   │                                     │◀── State STARTING ──│
   │                                     │◀── State EXECUTE ───│
   │                                     │◀── JobResult ───────│  + inventory slot cleared
   │                                     │◀── InventoryLevel ──│  → InventoryIndexer rebuilds
   │  apply_cargo_transfers ▶ ledger: storage UR5 holds part   │
   │                                                           │
   │  ─── pp3: Handoff CMD (per 4-case rule) ──────────────────▶ Storage UR5 ⇄ Shuttle1
   │                                     │◀── JobResult ───────│
   │  apply_cargo_transfers ▶ ledger: Shuttle1 holds part      │
   │                                                           │
   │  ─── pp4: Transport CMD ───────────▶│────────────────────▶│ Shuttle1
   │                                     │◀── JobResult ───────│
   │                                                           │
   │  ─── BoP CMD: Drilling ────────────▶│────────────────────▶│ Drilling KUKA
   │                                     │◀── State EXECUTE ───│
   │                                     │◀── JobResult ───────│
   │                                                           │
   │  handler.update_step(COMPLETED)                           │
   │── occupancy.release_one(shuttle); release_one(target)     │
   │── publish OccupancyMessage ────────▶│                     │
```

When the **last** BoP step completes, the scheduler runs the post-process plan
(Handoff → Transport → Store) the same way, then writes the Traceability
submodel to the product shell and publishes `WorkOrderStatus.COMPLETE`.

### Cargo ledger semantics

`PreProcessStep.cargo_transfers` is what makes the ledger track the part:

| Skill       | Side effect on success                                       |
| ----------- | ------------------------------------------------------------ |
| `Transport` | none — carrier moves but doesn't change who's carrying       |
| `Retrieve`  | storage actor gains cargo (`component_reference`)            |
| `Handoff`   | per the 4-case rule: cargo moves between sender and receiver |
| `Store`     | the storing actor clears its cargo                           |

`OccupancyManager.apply_cargo_transfers(step.cargo_transfers)` is called in
`Scheduler._execute_step` right after a step transitions to COMPLETED.

---

## 4. Where to look when X happens

### No matching resource

`capability_matcher.py` debug prints. Most likely cause: parameter names disagree between the work order and the capability YAML, or the SupportedComponents list uses a different `Category/Type` segment than the work order's `ComponentReference`. The matcher prints both lists on rejection.

### `[plan] product matcher has no record of …`

`product_property_matcher.py`. Either no `InventoryLevel` has arrived yet (scheduler runs `_seed_initial_state` to ask, but stations take a moment to reply), or the work order asks for a type prefix that doesn't match any indexed component.

### Station hangs in COMPLETING

The station's own `completing()` method threw. Look at the station log first; an empty `self.result` / `self.quality` makes `JobResultMessage` validation fail — common cause is the station not finding the component in its inventory but still proceeding.

### Controller times out waiting for JobResult

The station never published it — see above. If the station logged `Published to .../JobResult/...`, the topic split is the suspect; check `MQTTClientControllerV2.on_message`.

### First command warns "never saw IDLE"

Expected on cold start — stations don't publish State until their first transition. `Scheduler._seed_initial_state` calls `controller.request_data(MS.StateMessage)` to ask everyone for it. After that, every state change refreshes the topic.

### Resource stays UNREACHABLE

The state handler isn't registered OR no State has ever arrived. Check `handle_state_message` is registered on the controller (in `main.py`) and that the watchdog (`_watch_last_seen_loop` in `MQTTClientControllerV2`) hasn't aged it out.

### Traceability submodel is empty

The `_traceability` map is populated in two places:

- `_resolve_storage_for` writes `picked_instance` when ProductMatcher finds a match.
- `_capture_retrieve_traceability` reads after a Retrieve JobResult — but it currently reads `result.output_parameters["ComponentReference"]` while the storage publishes on `result.component_reference`. Known bug.

If the first path also didn't fire (no inventory match), traceability stays empty.

### Order finishes but Store step is skipped

`_find_cargo_holder_for_order` returned `None` — i.e. no actor reports carrying anything for this order. Check the cargo ledger (`controller.shared_handler_variable["cargo"]` and the `OccupancyManager.all_cargo()` print) — usually means a Handoff didn't apply a cargo transfer.

---

## 5. Concurrency model (where this is heading)

Today: **single order** in the run loop. Job correlation already uses
`{order_id}-{step_id}` so `job_results` won't collide across orders.

Multi-order will be a small change:

```python
# scheduler additions, sketched
async def run_orders(self, handlers: list[WorkOrderHandler]):
    await asyncio.gather(*(self.run_order(h) for h in handlers))
````

The pieces that already work across orders:

- `OccupancyManager` is keyed on `(resource, actor)` and tags reservations
  with `order_id` — two orders fighting for the same shuttle is handled.
- `JobTracker` reads from `shared_handler_variable["job_result"]` keyed by
  job_id, which already includes the order_id.
- `_traceability` in `Scheduler` is per `order_id`.

The pieces that still need attention before multi-order is real:

- The scheduler picks `candidates[0]` greedily. With concurrent orders, that
  can starve one of them. A "cost-aware" or "round-robin among free
  candidates" rule belongs near `_execute_bop_step`'s match handling.
- Order-level state (which step is next, what's been retrieved) is split
  between `WorkOrderHandler` and `Scheduler._traceability`. If we want a
  durable line controller, that needs persisting somewhere — the work order
  AAS itself is the natural home.

---

## 6. What's deliberately not done yet

These are the same "known gaps" you'd write in CLAUDE.md §13, surfaced here
so the group sees them in one place:

- **Connection-point reachability filter on shuttles.** `_pick_shuttle`
  filters by SupportedComponents and Occupancy, but does **not** walk the
  `LineConfig` graph to verify the shuttle can actually reach both the
  storage and the target. When the line grows another shuttle pool, that
  filter goes in `_transport_supports` (the IRI args `_target_iri` /
  `_storage_iri` are already plumbed for it).
- **Cost-based scheduling.** First match for now.
- **Handshake failure recovery.** A failed pre-process step raises and the
  order stops. PackML `Held` / `Suspended` are reserved for resume support.
- **Multi-input planning for assembly.** `PreProcessPlanner.plan()` fetches
  **one** component. Assembly steps need N fetches — the scheduler can loop
  `planner.plan(...)` per ingredient and concatenate the step lists, but
  that loop isn't wired in yet.
- **`_capture_retrieve_traceability` bug.** Reads
  `result.output_parameters["ComponentReference"]`; storage station publishes
  the instance on `JobResultMessage.component_reference`. Today `picked_instance`
  from `_resolve_storage_for` covers traceability, so the bug is dormant —
  but normalize before relying on Retrieve JobResults as a fallback path.
- **Traceability resolution.** The work order's `ProductReference` may be a
  short name. `aas_writer` falls back to constructing an IRI under
  `…/Shells/Assembly/`; if your product shells live elsewhere, look it up
  via the AAS server instead.

---

## 7. Quick file-reading order (for a new collaborator)

1. **`workorder_handler.py`** — what shape the work order has and how steps progress.
2. **`pre_process_planner.py`** — the 4-case handoff rule + `release_sequence_for`. Understanding this is half the design.
3. **`scheduler.py`** — `run_order()` and `_execute_bop_step()`. The rest is helpers.
4. **`resource_manager.py`** + **`product_property_matcher.py`** — how AAS data is fetched and the runtime queries on top of it.
5. **`main.py`** — how everything plugs together at startup, plus the five flat MQTT handlers.

Everything else is supporting infrastructure (`MQTTClientControllerV2`, message
schemas, `aas_writer`, `transport_planner`'s graph). Read those when you hit them.
