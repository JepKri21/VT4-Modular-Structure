# Implementation2.0 — Python-side Overview

This folder contains every Python process in the system: the **AAS
generator**, the **MES** (FastAPI + dispatcher + Postgres bridge), the
**Line Controller**, and the **station runtime** (Generic Resource
Runner). Everything in this folder talks to two external services — a
**BaSyx AAS server** for AAS HTTP and an **MQTT broker** for runtime —
plus a **PostgreSQL** instance for queue/metrics state.

The single design rule that ties this folder together:

> AAS describes everything **describable**.
> MQTT carries everything **happening**.
> Pydantic schemas in [`InformationModels/MessageStructure.py`](ClassesAndBuilderMethods/InformationModels/MessageStructure.py)
> are the wire format for everything in (2). Stations and the controller
> import the same module; the React app re-encodes from the same shapes.

---

## 1. Folder map

```
Implementation2.0/
├── ClassesAndBuilderMethods/
│   ├── BaSyx_AAS_Generator/          # YAML → AAS Environment JSON → BaSyx upload
│   ├── InformationModels/
│   │   └── MessageStructure.py       # canonical Pydantic schemas for every MQTT message
│   ├── MES/                          # FastAPI + queue + dispatcher + bridge
│   │   ├── mes_api.py                #   FastAPI app (port 8000); boots dispatcher + bridge as threads
│   │   ├── order_processor.py        #   customer order → N work orders → queue
│   │   ├── queue_manager.py          #   PENDING/RELEASED/COMPLETED/ABORTED transitions
│   │   ├── order_store.py            #   JSON sidecar of orders.json
│   │   ├── dispatcher.py             #   releases up to MES_MAX_CONCURRENT to MQTT
│   │   ├── psql_bridge.py            #   subscribes to MQTT, writes to Postgres
│   │   ├── workorder_builder.py      #   composes a WorkOrder JSON for one product
│   │   ├── webshop_notify.py         #   callbacks to Next.js when order state changes
│   │   ├── shell_uploader.py         #   pushes AAS shells to BaSyx
│   │   ├── preset_loader.py          #   reads YAML presets at runtime
│   │   └── schema.sql                #   Postgres schema (seeded by docker compose)
│   ├── MQTT/
│   │   └── ResourceMQTT.py           # base MQTT client used by stations
│   └── PackML/
│       ├── PackMLMachineClass.py     # PackML state machine + StationBehavior hooks
│       └── StationBehaviorBlank.py   # template for new station behaviors
├── Line_Controller/                  # see §3 — detailed step-by-step
│   ├── main.py
│   ├── scheduler.py
│   ├── workorder_handler.py
│   ├── resource_manager.py
│   ├── capability_matcher.py
│   ├── product_property_matcher.py
│   ├── transport_planner.py
│   ├── pre_process_planner.py
│   ├── occupancy_manager.py
│   ├── job_tracker.py
│   ├── aas_writer.py
│   ├── controller_alarms.py
│   ├── order_recovery.py
│   ├── MQTTClientControllerV2.py
│   ├── ARCHITECTURE.md               # ← canonical reference (also linked below)
│   └── CLAUDE.md
└── ProductAndResourceImplementations/
    └── Generic_Resource_Runner/      # data-driven station runtime
        ├── Generic_Resource_Runner.py
        ├── Generic_Resource_Models.py
        └── Generic_Resource_Submodel_Parser.py
```

---

## 2. The MES (FastAPI + dispatcher + bridge)

`mes_api.py` is started once and brings up three concurrent things in the
same process:

| Concurrent unit | What it does |
|---|---|
| **FastAPI app** | `POST /api/v1/orders` accepts a webshop payload, returns 202, runs `order_processor.process_order` in the background. `GET /api/v1/orders` exposes the in-memory registry. |
| **Dispatcher thread** (`dispatcher.main`) | Subscribes to `<line>/Controller/OrderCompleted`. On boot and on every completion, calls `queue_manager.peek_next()` and publishes the payload to `AAUSmartLab/<line>/MES/WorkOrder`. Respects `MES_MAX_CONCURRENT` and the per-order `next_attempt_at` backoff for retries. |
| **PSQL bridge thread** (`psql_bridge.main`) | At startup walks BaSyx for every resource shell, reads its `Communication` submodel, builds subscription filters from the declared suffixes, and writes incoming messages to `alarms` / `state_transitions` / `job_results` / `order_completions`. |

### Flow when a customer places an order

```
Next.js  ──POST /api/v1/orders──▶ mes_api.lifespan-started FastAPI
                                       │
                                       ▼
                            order_processor.process_order
                                       │
                       ┌───────────────┼─────────────────────────┐
                       ▼               ▼                         ▼
              shell_uploader     workorder_builder         queue_manager.enqueue
              (upload product   (compose WorkOrder         (INSERT mes_orders rows,
               instance shells   JSON for one product       one per product, sharing
               to BaSyx)         with BoP from preset)      batch_id + batch_index)
                       │               │                         │
                       └───────────────┴─────────────────────────┘
                                                                 │
                                              dispatcher reacts on next tick
                                                                 │
                                              MQTT publish ─▶ Line Controller
```

---

## 3. The Line Controller — detailed flow

The Line Controller's authoritative reference is
[`Line_Controller/ARCHITECTURE.md`](Line_Controller/ARCHITECTURE.md). This
section gives the **step-by-step function call sequence** for one work
order — what calls what, where the data crosses a module boundary, and
which side-effects each call has.

### 3.1 Wiring (one-time at boot)

`main.py` does only wiring — never business logic. In order:

```text
main.main()
├── MQTTClientControllerV2(...)                 # broker connect, retain CMD, watchdog
├── controller.update_information()             # walks BaSyx for every shell under the resource prefix:
│                                               #   - reads Communication submodel → topic suffixes
│                                               #   - subscribes to <ns>/State/+, /JobResult/+, /InventoryLevel/+
│                                               #   - registers shells with reachability=False until first State arrives
├── ResourceManager(controller)                 # walks shells again, builds skill/capability index
├── CapabilityMatcher(resource_manager)
├── TransportPlanner.load_line_config_from_aas  # reads the Controller's own LineConfiguration submodel
├── PreProcessPlanner(transport_planner)
├── OccupancyManager(controller)                # in-memory custody ledger + Occupancy/Cargo MQTT
├── JobTracker(controller)                      # awaits JobResult by (order_id, step_id)
├── ProductMatcher(...)                         # inventory index + AAS property resolver
├── controller.register_handler(StateMessage,        handle_state_message)
├── controller.register_handler(JobResultMessage,    handle_job_result_message)
├── controller.register_handler(InventoryLevelMessage, handle_inventory_level)
├── controller.register_handler(OccupancyMessage,    occupancy.apply_occupancy)
├── controller.register_handler(CargoMessage,        occupancy.apply_cargo)
├── OrderRecovery(controller)                   # 3-attempt restart + alarm publishing
├── handler = WorkOrderHandler(); handler.load_workorder(json)
└── Scheduler(...).run_order(handler)
```

After `update_information()`, `MQTTClientControllerV2` is the **only**
module that touches `paho.mqtt`; everything else publishes through
`controller.publish_message(shell_iri, msg)` and reads from
`controller.shared_handler_variable[...]` dictionaries.

### 3.2 `Scheduler.run_order(handler)` — top-level loop

```python
async def run_order(self, handler):
    order_id = handler.workorder["OrderId"]
    self._traceability[order_id] = {}
    await self._seed_initial_state()        # request_data(StateMessage) for cold-start visibility

    while True:
        if self._is_order_complete(handler):
            await self._finalize_order(handler)        # post-process + traceability + WorkOrderStatus.COMPLETE
            return MS.OrderStatus.COMPLETED

        ready = handler.get_ready_steps()              # ←─ §3.3
        if not ready:
            await asyncio.sleep(TICK_INTERVAL_S)
            continue

        try:
            await self._execute_bop_step(handler, ready[0])   # ←─ §3.4
        except (CmdNoAckError, TimeoutError, RuntimeError) as exc:
            decision = self.recovery.handle_failure(...)      # ←─ §3.6
            if decision.action == RecoveryAction.RESTART:
                self._release_order_reservations(order_id)
                continue
            return MS.OrderStatus.ABORTED
    # finally: release reservations, publish OrderCompleted (see §3.7)
```

### 3.3 `WorkOrderHandler.get_ready_steps()`

`WorkOrderHandler` owns the BoP and its dependency graph.

```text
get_ready_steps()
├── for each step in BoP:
│   ├── if step.state != PENDING: skip
│   ├── _dependencies_complete(step.Dependencies)?      # all dep step IDs in COMPLETED
│   ├── _is_ingredient_complete(step.Ingredient)?       # recursively: every sub-ingredient COMPLETED
│   └── if both true: add step to ready list
└── return ready list
```

The dependency graph is built once in `_build_dependency_graph()` from
the BoP's `Dependencies` arrays. `_compute_precedence_levels()` gives a
deterministic ordering — used by `_generate_execution_plan()` and the
debug `print_process_list()`.

### 3.4 `Scheduler._execute_bop_step(handler, bop)` — the core

This is where most of the logic lives. The numbered comments below
correspond to the numbered cases in
[`ARCHITECTURE.md` §3](Line_Controller/ARCHITECTURE.md).

```text
_execute_bop_step(handler, bop)
│
├── 1.  capability_matcher.match(bop)
│       ├── reads bop.RequiredCapability.semanticId
│       ├── filters ResourceManager.find_by_capability(semantic_id) by:
│       │     - parameter ranges (flattened across nested SMC, with alias map)
│       │     - SupportedComponents (compared by type prefix)
│       │     - AllowedMaterials
│       └── returns candidates [(shell_iri, actor_name), …]
│       on empty: alarm "no matching resource" → raise RuntimeError
│
├── 2.  pick the first candidate            ← greedy; see §3.8
│       target_iri, target_actor = candidates[0]
│       _current_bop_target_iri/topic/step_info = ...   # for recovery telemetry
│
├── 3.  handler.get_step_execution_info(bop.id)
│       returns the ingredient ComponentReference (type IRI) + Material
│
├── 4.  _resolve_storage_for(component_ref, ingredient)
│       ├── product_matcher.find_matching_components(type, order_properties)
│       │     - reads controller.shared_handler_variable["inventory"]
│       │     - InventoryIndexer rebuilds index per (resource, inventory, slot)
│       │     - AASPropertyResolver fetches properties from BaSyx
│       │     - ConstraintEvaluator compares requested vs actual properties
│       └── returns (storage_iri, picked_instance_iri)
│       _traceability[order][ingredient] = picked_instance_iri
│
├── 5.  _pick_shuttle(component_ref, material)
│       ├── ResourceManager.find_skill_offering("Transport")
│       ├── filters by SupportedComponents (type prefix + material)
│       ├── checks OccupancyManager — no shuttle currently committed to another order
│       └── returns shuttle_iri, shuttle_actor
│
├── 6.  release_sequence_for(storage_iri, component_ref)
│       (top-level helper in pre_process_planner.py)
│       reads inventory + the storage's advertised skills:
│         - storage advertises Retrieve + Handoff  →  ["Retrieve","Handoff"]
│         - storage advertises only Handoff        →  ["Handoff"]
│
├── 7.  pre_process_planner.plan(
│             target=target_iri, storage=storage_iri,
│             shuttle=shuttle_iri, release_skills=[...])
│       returns a PreProcessPlan: ordered list of PreProcessStep with
│         - skill ∈ {Transport, Retrieve, Handoff, Store}
│         - cargo_transfers (ledger side-effect; see §3.5)
│         - the 4-case handoff rule encoded inline (see ARCHITECTURE.md)
│
├── 8.  occupancy.commit(shuttle, target_iri, order_id)
│       (also publishes OccupancyMessage so observers see the reservation)
│
├── 9.  _print_and_execute_plan(steps)
│       for each PreProcessStep:
│         a. _execute_step(step):
│              ├── job_id = f"{order_id}-{step.id}"
│              ├── _send_and_wait(target=step.target_iri, msg=CommandMessage, job_id=job_id)
│              │     ├── controller.publish_message(target_iri, CommandMessage(START, ...))
│              │     ├── await station State transitions to STARTING/EXECUTE
│              │     └── result = await job_tracker.wait_for(job_id, timeout=...)
│              ├── if result.result != OK: raise RuntimeError → recovery
│              └── occupancy.apply_cargo_transfers(step.cargo_transfers)
│                     - Retrieve  → storage actor gains cargo (component_reference)
│                     - Handoff   → cargo transfers per the 4-case rule
│                     - Store     → storing actor clears cargo
│                     - Transport → no-op (carrier moves, cargo stays with whoever held it)
│
├── 10. _execute_bop_command(target_iri, actor, bop, parameters)
│       same _send_and_wait pattern with the BoP step's CMD
│       (e.g. Drilling/Assemble with the BoP parameters)
│
├── 11. handler.update_step(bop.id, COMPLETED)
│       which calls _update_workorder_state() and may flip the order's
│       overall state to RUNNING / COMPLETED.
│
├── 12. _capture_retrieve_traceability(bop, result)
│       writes the consumed instance into the in-memory traceability map
│       (known bug — see ARCHITECTURE.md §4)
│
└── 13. occupancy.release_one(shuttle_actor); occupancy.release_one(target_actor)
        publish OccupancyMessage so dashboards see the reservation drop.
```

### 3.5 Cargo ledger semantics

`OccupancyManager.apply_cargo_transfers(step.cargo_transfers)` runs right
after a PreProcessStep transitions to COMPLETED. Each `cargo_transfers`
entry is one of:

| Skill | Side effect |
|---|---|
| `Transport` | none — carrier moves but doesn't change who's carrying |
| `Retrieve` | storage actor **gains** cargo (`component_reference`) |
| `Handoff` | per the 4-case rule (sender ↔ receiver, with/without in-flight carry) |
| `Store` | the storing actor **clears** its cargo |

The ledger persists into `controller.shared_handler_variable["cargo"]`
and is mirrored on the `<line>/Controller/Cargo` topic so the dashboard
can render who's holding what.

### 3.6 Recovery (`OrderRecovery.handle_failure`)

```text
on CmdNoAckError | TimeoutError | RuntimeError in _execute_bop_step:
   reason = _classify_recovery_reason(exc)            # NO_ACK / TIMEOUT / JOB_FAILED
   decision = recovery.handle_failure(
       handler, reason,
       failed_resource_iri=self._current_bop_target_iri,
       failed_step_info=self._current_bop_step_info)
   if decision.action == RESTART:
       handler.reset_for_retry(failed_resource=...)   # PENDING-reset non-COMPLETED steps,
       _release_order_reservations(order_id)          #   exclude failed resource on next match
       continue                                        # loop in run_order picks it up
   else:  # ABORT
       publish ControllerAlarmMessage(severity=CRITICAL)
       return MS.OrderStatus.ABORTED
```

The retry is **at-most 3** — `handler.get_attempt_count()` is read by the
finally block and shipped in `OrderCompletedMessage` so the MES
dispatcher can decide whether to requeue the whole order with backoff.

### 3.7 Finalisation

When `_is_order_complete(handler)` is true:

```text
_finalize_order(handler)
├── _run_post_process(handler)
│     mirrors §3.4 but with PreProcessPlanner.plan_post_process(...)
│     — Handoff → Transport → Store back to a free storage
├── _write_traceability(order_id, handler)
│     aas_writer writes a Traceability submodel to the product shell
│     listing which physical component instance was consumed for each
│     ingredient name
└── _publish_order_complete(handler)
      controller.publish_message(line, WorkOrderStatusMessage(COMPLETE))

run_order's finally block then:
├── _release_order_reservations(order_id)
├── occupancy.release(order_id)     # except stuck cargo (intentional)
└── _publish_order_completed(order_id, status, attempt_count)
      controller.publish_message(<line>/Controller/OrderCompleted, OrderCompletedMessage)
      → MES dispatcher consumes this and releases the next PENDING.
```

### 3.8 What the scheduler does **not** do (deliberate omissions)

- Pick the best candidate — it picks `candidates[0]`. A cost-aware or
  round-robin policy belongs near step 2 of §3.4.
- Walk the line graph to confirm a shuttle can reach both the storage
  and the target. `_pick_shuttle` filters by `SupportedComponents` and
  occupancy only. The `_target_iri`/`_storage_iri` arguments to
  `_transport_supports` are plumbed for a future graph filter.
- Plan multi-input assemblies. `PreProcessPlanner.plan()` fetches one
  component. Assembly steps need N fetches — loop `planner.plan` per
  ingredient and concatenate, but the loop isn't wired in yet.
- Persist `WorkOrderHandler` state. If the controller dies mid-order, the
  in-memory step state is lost; recovery is from MES requeue, not from a
  warm controller restart.

---

## 4. Stations (Generic Resource Runner)

`Generic_Resource_Runner.py` is a single Python process per resource
shell. It is **data-driven** — it does not know what kind of station it
is at import time.

```text
GenericResourceExecutor.__init__(shell_id)
├── AASResourceLoader.load(shell_id)         # GET /shells/<id> + walks submodels via BaSyx HTTP
├── ResourceParser.parse(raw_resource)       # turns AAS dicts into typed runtime objects:
│     ─ Capabilities (semanticId, parameters)
│     ─ Skills (the executable side — Transport, Retrieve, Handoff, Store, BoP capabilities)
│     ─ Communication (MQTT prefix + suffixes)
│     ─ Inventory layout (slots per actor)
├── for each actor: PackMLStateMachine(behavior=GenericBehavior(actor, skills))
├── MQTTClientResource.connect()
│     subscribes to <ns>/CMD/<actor>/+ and publishes <ns>/PackMLState/<actor>
│     using the suffixes from Communication
└── run loop: dispatch CMD → state machine → behavior.execute → publish JobResult
```

The Line Controller has no knowledge of individual stations — it sees
**capabilities**. To bring up a new physical station you only need to
create its AAS shell + Communication/Capability/Skill/Inventory
submodels and point a `Generic_Resource_Runner.py` process at it.

---

## 5. Postgres schema (`MES/schema.sql`)

Tables owned by the MES side of the system:

| Table | Writer | Consumer |
|---|---|---|
| `alarms` | `psql_bridge` (station alarms, controller alarms) | `/alarms` page, `navbar` bell |
| `state_transitions` | `psql_bridge` (PackML transitions) | `/api/metrics/resources`, `/api/metrics/lines` |
| `job_results` | `psql_bridge` (JobResultMessage) | OEE Performance + Quality |
| `mes_orders` | `mes_api`, `dispatcher` | `/orders` page, `DispatchQueueView` |
| `order_completions` | `psql_bridge` (OrderCompletedMessage) | `/performance` recent-orders panel |

The bridge subscribes to **every** resource shell discovered at startup —
the topic structure is read off each shell's Communication submodel, so
the bridge picks up new stations the next time you restart it.

---

## 6. Where to look when…

| Symptom | Look in |
|---|---|
| No matching resource for a BoP step | `capability_matcher.py` — debug prints show parameter mismatches |
| `[plan] product matcher has no record of …` | `product_property_matcher.py` — InventoryLevel hasn't been received yet or type prefix mismatch |
| Station hangs in COMPLETING | the station's `completing()` threw; check `Generic_Resource_Runner` log + `MessageStructure.JobResultMessage` validation |
| Controller times out waiting for JobResult | station never published it; or topic-split bug in `MQTTClientControllerV2.on_message` |
| Resource stays UNREACHABLE | `_watch_last_seen_loop` aged it out; check State retained message |
| Order stuck in RELEASED | controller died before publishing OrderCompleted; use `/api/resilience/clear-stuck` |
| Two orders released before persistent session settled | confirm `clean_session=False` (controller) and `retain=False` (dispatcher) |
