# Line Controller — Architecture

This is the runbook for the Line Controller as it stands today. It exists so
the group can see what each module does, how a work order flows through
them, and where to look first when something breaks.

> Source of truth for higher-level design is still `CLAUDE.md`. This file
> covers the **current code** — what actually runs.

---

## 1. The 30-second mental model

```
                            ┌─────────────────────┐
  WorkOrder JSON  ───────▶  │  WorkOrderHandler   │  BoP steps with deps
                            └──────────┬──────────┘
                                       │ get_ready_steps()
                                       ▼
        ┌──────────────────────────────────────────────────┐
        │                    Scheduler                      │
        │  for each ready step:                             │
        │    1. CapabilityMatcher  → list of resources      │
        │    2. PreProcessPlanner  → transport/retrieve/handoff
        │    3. execute steps     (MQTT CMD + wait JobResult)
        │    4. execute BoP cmd                             │
        │  when all steps done:                             │
        │    5. plan_post_process → handoff/transport/Store │
        │    6. aas_writer        → traceability submodel   │
        │    7. publish WorkOrderStatus.COMPLETE            │
        └──────────────────────────────────────────────────┘
                    ▲                ▲                ▲
        ┌───────────┴────┐ ┌─────────┴────┐ ┌────────┴──────┐
        │ ResourceManager│ │  JobTracker  │ │ Inventory     │
        │ + actor_states │ │ wait_for(job)│ │ find_storage_ │
        │ + reachability │ │              │ │     for(ref)  │
        └───────────┬────┘ └──────────────┘ └───────────────┘
                    │                        OccupancyManager
                    │                        (cross-order locks)
                    ▼
       MQTTClientController  ◀──── stations publish State / JobResult / InventoryLevel
                              ───▶ Line Controller publishes CMD / InfoRequest
```

---

## 2. Modules

| File | What it owns |
|---|---|
| `main.py` | Wiring only. Loads config, builds managers, hands a work order to `Scheduler.run_order(...)`. |
| `workorder_handler.py` | Parses the work order JSON, builds the dependency graph between ingredients, exposes `get_ready_steps()` and per-step state transitions (PENDING → ASSIGNED → IN_PROGRESS → COMPLETED). |
| `resource_manager.py` | AAS discovery: walks the BaSyx server for shells, reads their Skills / Capability submodels. Also holds runtime PackML state per actor (`actor_states`) and reachability per shell. `make_state_handler(rm)` is the MQTT closure that keeps those fresh. |
| `capability_matcher.py` | Filters discovered resources to those that can actually run a given BoP step (semanticId + parameter ranges + supported components + allowed materials). Returns candidates, never picks. |
| `transport_planner.py` | Parses `LineConfiguration` (resource positions + connection points). Provides `handoff_position(resource_id)` and the parameter-dict builders for Transport / Handoff commands. |
| `pre_process_planner.py` | Given a chosen target + storage + shuttle, produces the ordered list of pre-process steps (`Transport`, `Retrieve`, `Handoff`) using the 4-case handoff rule. Also `plan_post_process(...)` mirrors that to put the finished part into storage. |
| `inventory_manager.py` | Listens for `InventoryLevelMessage` from each storage station. Answers "which storage has this component?". Has `request_inventory_update(...)` to ping all storages on startup. |
| `job_tracker.py` | Listens for `JobResultMessage`. Exposes `await tracker.wait_for(job_id)` so the scheduler can block until a station finishes a command. |
| `occupancy_manager.py` | In-memory ledger of `(resource, actor) → order_id`. `commit()` reserves, `release()` frees. Also publishes `OccupancyMessage` so observers can see who's holding what. |
| `aas_writer.py` | Writes a `Traceability` submodel back to the product shell after the work order completes, recording which specific component instances were consumed. |
| `scheduler.py` | The orchestration loop. Drives one or more work orders end-to-end using everything above. |
| `MQTTClientController_Simple.py` | Generic MQTT pump. Subscribes to every known resource's full namespace, parses topics into `topic_info`, dispatches by message type to registered handlers, publishes outbound messages on the right topic. |

---

## 3. One full BoP step — sequence diagram (text)

```
Scheduler                       MQTT                  Station
   │                              │                     │
   │── matcher.match(step) ─┐     │                     │
   │   (queries AAS server) │     │                     │
   │← candidates ───────────┘     │                     │
   │                              │                     │
   │── planner.plan(...)         │                     │
   │← PreProcessPlan: 4 steps     │                     │
   │                              │                     │
   │── occupancy.commit(...)     │                     │
   │   publishes Occupancy ────▶ │                     │
   │                              │                     │
   │   ──── pp1: Transport ───────────────────────────▶ │ Shuttle1: IDLE→STARTING
   │                              │ ◀── State STARTING  │
   │                              │ ◀── State EXECUTE   │
   │                              │ ◀── State COMPLETING│
   │                              │ ◀── JobResult ──────│
   │ jobs.wait_for(job_id) →      │                     │
   │ ✓ COMPLETED                  │                     │
   │                              │ ◀── State IDLE      │
   │                              │                     │
   │   ──── pp2: Retrieve ────────────────────────────▶ │ Storage UR5
   │                              │ ◀── JobResult       │
   │                              │     output_parameters│
   │                              │     .ComponentReference = ".../Bottom_Cover-BC003"
   │   _capture_retrieve_traceability records that      │
   │                              │                     │
   │   ──── pp3: Handoff (storage actor) ─────────────▶ │
   │                              │ ◀── JobResult       │
   │                              │                     │
   │   ──── pp4: Transport to drill ──────────────────▶ │ Shuttle1
   │                              │ ◀── JobResult       │
   │                              │                     │
   │   ──── BoP: Drilling ────────────────────────────▶ │ Drilling KUKA
   │                              │ ◀── State EXECUTE   │
   │                              │ ◀── JobResult       │
   │                              │                     │
   │ handler.update_step(COMPLETED)                     │
   │── occupancy.release(...)                          │
```

When the **last** BoP step completes, the scheduler runs the post-process plan
(Handoff → Transport → Store) the same way, then writes the Traceability
submodel to the product shell and publishes `WorkOrderStatus.COMPLETE`.

---

## 4. Where to look when X happens

| Symptom | First place to look |
|---|---|
| No matching resource | `capability_matcher.py` debug prints. Most likely cause: parameter names disagree between the work order and the capability YAML. The matcher prints both lists on a rejection. |
| Station hangs in COMPLETING | The station's own `completing()` method threw an exception. Look at the station log first; typo in skill name comparisons (e.g. `"Retrive"` vs `"Retrieve"`) is the historical favourite. |
| Controller times out waiting for JobResult | The station never published it — see above. If the station logged a `Published to ...JobResult/...`, the topic split is the suspect; check `MQTTClientController_Simple.on_message`. |
| First command warns "never saw IDLE" | Expected on cold start — stations don't publish State until their first transition. The `request_state_update(...)` calls in `Scheduler._seed_initial_state` paper over this. |
| Inventory lookup returns nothing | `inventory_manager.py` hasn't received the `InventoryLevelMessage` yet, OR the work order's `ComponentReference` doesn't prefix-match any inventory item. The handler logs each catalogued storage. |
| Resource stays UNREACHABLE | The state handler isn't running OR the station hasn't published any State. Check `make_state_handler(rm)` is registered on the controller. |

---

## 5. Concurrency model (where this is heading)

Today: **single order** in the run loop. Job correlation already uses
`{order_id}-{step_id}` so `job_results` won't collide across orders.

Multi-order will be a small change:

```python
# scheduler additions, sketched
async def run_orders(self, handlers: list[WorkOrderHandler]):
    await asyncio.gather(*(self.run_order(h) for h in handlers))
```

The pieces that already work across orders:
- `OccupancyManager` is keyed on `(resource, actor)` and tags reservations
  with `order_id` — two orders fighting for the same shuttle is handled.
- `JobTracker.results` is keyed on `job_id` which includes `order_id`.
- `_traceability` in `Scheduler` is per `order_id`.

The pieces that still need attention before multi-order is real:
- The scheduler picks `candidates[0]` greedily. With concurrent orders, that
  can starve one of them. A "cost-aware" or "round-robin among free
  candidates" rule belongs in `_pick_target_for(step)`.
- Order-level state (which step is next, what's been retrieved) is split
  between `WorkOrderHandler` and `Scheduler._traceability`. If we want a
  durable line controller, that needs persisting somewhere — the work order
  AAS itself is the natural home.

---

## 6. What's deliberately not done yet

These are the same "known gaps" you'd write in CLAUDE.md §13, surfaced here
so the group sees them in one place:

- **Connection-point reachability filter on shuttles.** `_pick_shuttle` just
  takes the first free Transport actor. When the line grows another shuttle
  pool, the LineConfiguration graph filter goes there.
- **Cost-based scheduling.** Same — first match for now.
- **Handshake failure recovery.** A failed pre-process step raises and the
  order stops. PackML `Held` / `Suspended` are reserved for resume support.
- **Multi-input planning for assembly.** `PreProcessPlanner.plan()` fetches
  **one** component. Assembly steps need N fetches — the scheduler can loop
  `planner.plan(...)` per ingredient and concatenate the step lists, but
  the loop isn't wired in yet. (See §5 of CLAUDE.md for the data model:
  `Assemblies[product].Ingredients` lists which ingredients an assembly
  consumes.)
- **Traceability resolution.** The work order's `ProductReference` is a
  short name (e.g. `Bottom_Cover_Drilled_PCB-BCDP001`). `aas_writer` falls
  back to a constructed IRI; if your product shells live under a different
  prefix, this needs to look it up via the AAS server instead.

---

## 7. Quick file-reading order (for a new collaborator)

1. **`workorder_handler.py`** — what shape the work order has and how steps progress.
2. **`pre_process_planner.py`** — read the 4-case handoff rule. Understanding this is half the design.
3. **`scheduler.py`** — `run_order()` and `_execute_bop_step()`. The rest is helpers.
4. **`resource_manager.py`** — how AAS data is fetched and the runtime queries on top of it.
5. **`main.py`** — to see how everything plugs together at startup.

Everything else is supporting infrastructure (MQTT plumbing, message
schemas, the route lookup). Read those when you hit them.
