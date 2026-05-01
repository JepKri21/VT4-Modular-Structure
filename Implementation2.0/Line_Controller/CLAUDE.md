# CLAUDE.md — Line Controller

This file is the source of truth for Claude (and humans) working on the Line
Controller. It is split into two halves:

1. **Conventions & architecture** — read this before writing any code.
2. **Module contracts** — the responsibility, inputs, and outputs of each
   subscript.

If anything in this file conflicts with code you find in the repo, **ask before
proceeding**. The file is intended to drift slower than the code; when it does,
that is a bug.

---

## 1. What this system is

The Line Controller orchestrates a plug-and-produce manufacturing line. It
pulls orders from the MES, plans how each product moves through the available
resources, and drives the line by exchanging MQTT messages with stations.

The line is built on these architectural choices:

- **Asset Administration Shell (AAS)** is the source of truth for everything
  _describable_: products, resources, capabilities, the line itself.
- **MQTT** is the source of truth for everything _happening_: state changes,
  commands, acknowledgments, events.
- **Product–Process–Resource (PPR)** with the **Capability–Skill–Service (CSS)**
  pattern is how we relate what a product needs to what a resource can do.
- **PackML** is the state model every actor exposes.
- The Line Controller itself is **mostly event-driven** — it reacts to MQTT
  events from stations — with a thin polling loop for sanity checks against the
  AAS server.

The Line Controller is _not_ the MES. It does not own orders, customers, or
business logic. It owns execution.

---

## 2. Core concepts and vocabulary

These terms have specific meanings in this project. Use them precisely.

**Product.** A physical thing being made. Has an AAS describing it, including a
Bill of Processes (BoP).

**Bill of Processes (BoP).** An ordered list of process steps the product must
go through. Each step references a required **capability** by `semanticId` and
declares parameters (e.g. drill diameter, depth).

**Resource.** A station or piece of equipment on the line. Has an AAS. A
resource declares which capabilities it provides and which actors can perform
each capability. Examples: Drilling Station, ACOPOS6D Transport Table, Storage.

**Actor.** A controllable sub-unit of a resource. A drilling station may have a
single actor (the drill); the ACOPOS6D table has one actor per shuttle. Each
actor has its own PackML state.

**Capability.** _What_ a resource can do, declared abstractly with a
`semanticId` and parameter ranges (min/max). Capabilities are matched against
BoP steps.

**Skill.** _How_ a resource performs a capability — the concrete, executable
implementation. The Line Controller does not invoke skills directly; it asks a
resource to perform a capability and the resource selects the skill.

**Connection point.** A physical location on a resource where a part can be
handed off in or out. Defined in the line configuration submodel of the Line
Controller's own AAS.

**Custody.** Which actor is currently responsible for the physical part. A
handoff is a transfer of custody, not necessarily a transfer of physical
location (see §6).

**Process checklist.** The Line Controller's runtime plan for a single product:
the BoP, expanded with transport and handoff steps, with completion state
tracked per step.

---

## 3. Repository layout

```
Implementation2.0/Line_Controller/   # this directory; only these files exist so far
├── CLAUDE.md
├── WorkorderExample.json            # example order payload; reference for the order schema
└── line_controller/                 # Python package (planned; not yet started)
    ├── __init__.py
    ├── main.py                  # entrypoint: starts MQTT client, MES poll loop, scheduler
    ├── config.py                # loads env / config files; no logic
    ├── aas/
    │   ├── __init__.py
    │   ├── client.py            # thin wrapper over the BaSyx REST API; returns dicts
    │   └── line_config.py       # loads the Line Controller's own AAS (resources + connection points)
    ├── order_handler.py         # pulls orders, extracts BoP, produces ProductOrder objects
    ├── resource_manager.py      # discovers resources, tracks liveness + capabilities + actor states
    ├── capability_matcher.py    # matches BoP steps to (resource, actor) candidates by semanticId + params
    ├── transport_planner.py     # expands "part needs to move from A to B" into concrete steps
    ├── process_checklist.py     # the checklist data structure + persistence + completion tracking
    ├── handshake.py             # implements the handoff handshake state machine
    ├── scheduler.py             # the main "what's next" decision loop
    ├── mqtt/
    │   ├── __init__.py
    │   ├── client.py            # connect, subscribe, publish, LWT
    │   ├── topics.py            # topic builders + parsers (single source of truth)
    │   └── messages.py          # message schemas (pydantic models)
    ├── packml.py                # PackML state enum + transition validation
    └── logging_config.py        # structured logging setup

tests/
└── ...                              # mirror the package layout
```

A few rules about this layout:

- `aas/client.py` is the **only** module that calls the BaSyx REST API.
  Everything else consumes plain Python dicts or pydantic models. This keeps
  the HTTP layer contained and makes testing trivial.
- `mqtt/topics.py` is the **only** place topic strings are constructed. Never
  hand-format a topic elsewhere.
- `scheduler.py` does not parse AAS, does not parse MQTT, does not plan
  transport. It asks the other modules. Keep it thin and readable.

---

## 4. AAS conventions

### 4.1 What the Line Controller reads

- **Order AAS** (from MES): contains a reference to the product AAS and
  order-level metadata (quantity, due date, priority).
- **Product AAS**: contains the BoP submodel.
- **Resource AAS** (one per station): contains the Capability submodel and the
  Skill submodel.
- **Line Controller AAS** (our own): contains the line configuration submodel
  describing resources, their physical positions, and connection points between
  them.

### 4.2 BaSyx access

Use `aas/client.py`. It wraps the BaSyx REST API and converts AAS responses to
plain dicts before returning. Reasons:

1. The rest of the codebase doesn't need to know about BaSyx response shapes.
2. Snapshots are easy to log and diff.
3. Tests can stub the client with hand-written dicts.

If you find yourself calling the BaSyx REST API outside `aas/`, stop and
refactor.

### 4.3 Capability declaration (resource side)

Every capability in a resource's Capability submodel must declare:

- `semanticId` — the IRI identifying _what_ the capability is.
- `parameters` — list of parameter declarations with name, type, min, max,
  unit, and `semanticId`.
- `actors` — list of actor IDs that can perform this capability.
- `requires_custody` — boolean. `true` means the resource must take custody
  of the part before performing the capability (handoff in, work, handoff
  out). `false` means the resource operates on the part in place — e.g. the
  drill operates on a part still held by an ACOPOS6D shuttle.

> **Known gap:** `requires_custody` is not yet present in existing capability
> submodels. When you encounter a capability that lacks it, default to `true`
> and emit a warning log. Adding the field to all submodels is tracked as
> follow-up work.

### 4.4 Capability matching (product side)

Every BoP step carries a `semanticId` for the required capability and concrete
values for the parameters defined by that capability. Matching is:

1. Filter resources whose Capability submodel contains a capability with the
   same `semanticId`.
2. Of those, keep capabilities whose parameter ranges contain the BoP step's
   requested values.
3. Of those, keep ones with at least one actor in PackML `Idle`.
4. If multiple candidates remain, the scheduler picks one (initially: first
   match; later: cost-based).

Never match capabilities by name. Names are for humans.

---

## 5. MQTT conventions

### 5.1 Topic structure

```
AAUSmartLab/<line_id>/<resource_id>/<channel>
```

`<line_id>` is currently `ProductionLine1`. Treat it as a config value, not a
constant.

Channels:

| Channel         | Direction             | Retained | Purpose                                                   |
| --------------- | --------------------- | -------- | --------------------------------------------------------- |
| `Status`        | resource → broker     | yes      | Presence: `online` / `offline`. LWT publishes `offline`.  |
| `State`         | resource → broker     | yes      | Per-actor PackML state. One message per actor.            |
| `CMD`           | controller → resource | no       | Commands (start, prepare_handoff, abort, etc.).           |
| `ControllerAck` | resource → controller | no       | Ack of a CMD: accepted / rejected, with reason.           |
| `Event`         | resource → controller | no       | Discrete events (process_complete, handoff_ready, error). |
| `InfoRequest`   | controller → resource | no       | Synchronous-style query.                                  |
| `InfoResponse`  | resource → controller | no       | Reply to InfoRequest, correlated by `request_id`.         |

All topics are constructed in `mqtt/topics.py`. If a channel is missing here,
add it there first, then use it.

### 5.2 Message format

JSON. Every message has at minimum:

```json
{
  "message_id": "<uuid4>",
  "timestamp": "<ISO8601 UTC>",
  "schema_version": "1.0"
}
```

Specific message types add fields. They are defined as pydantic models in
`mqtt/messages.py`. Validate on receive; serialize via the model on send.

### 5.3 Resource discovery and liveness

- Stations publish a retained `online` to `Status` on connect.
- Stations set MQTT LWT to publish `offline` to `Status` on unexpected
  disconnect.
- The `resource_manager` subscribes to `AAUSmartLab/+/+/Status` and maintains a
  live registry. On `online`, it re-fetches the resource's AAS to refresh
  capabilities. On `offline`, it marks the resource unavailable and triggers a
  reschedule of any in-flight steps assigned to it.

This means _no_ polling for liveness. MQTT itself tells us.

---

## 6. The handoff handshake

A handoff is a transfer of **custody** of a part. Custody is logical; physical
co-location is separate. Examples:

- Storage robot places a part on a shuttle: custody moves Storage → Shuttle.
- Shuttle moves part to drill, drill clamps it: custody moves Shuttle → Drill.
- Drill releases, shuttle moves on: custody moves Drill → Shuttle.
- Drill operates on a part still held by the shuttle (no clamp): **no custody
  change** — the drill's capability has `requires_custody: false`.

### 6.1 Handshake sequence (when `requires_custody` is true)

Sender = current custody holder. Receiver = next custody holder.

1. **Controller → Receiver** `CMD: prepare_handoff` with `connection_point_id`
   and part metadata.
2. **Receiver → Controller** `ControllerAck: accepted`. Receiver actor
   transitions `Idle → Execute` and prepares (opens clamp, positions tool).
3. **Receiver → Controller** `Event: ready_to_receive`.
4. **Controller → Sender** `CMD: execute_handoff` with the same
   `connection_point_id`.
5. **Sender → Controller** `Event: handoff_complete` once the part is
   physically released.
6. **Receiver → Controller** `Event: custody_acquired`. Receiver actor
   transitions `Execute → Complete → Idle`.
7. Controller updates the part's `current_location` in the checklist.

If any step times out or returns rejection/error, the controller aborts the
step and pushes the product into a recovery path (TBD; for now: log + halt).

### 6.2 No-custody case

When the next capability has `requires_custody: false`:

- Skip the handshake entirely.
- Send `CMD: start` to the operating resource.
- The actor holding custody (typically the shuttle) stays in `Execute` /
  `Idle` as appropriate; it is not commanded.

---

## 7. PackML usage

We use a reduced subset for now:

| State       | Meaning to Line Controller                                                                                                        |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `Idle`      | Actor is available to accept a CMD.                                                                                               |
| `Execute`   | Actor is performing a capability or preparing for handoff.                                                                        |
| `Complete`  | Transitions automatically back to `Idle` on the resource side. The controller may observe it transiently but does not gate on it. |
| `Stopped`   | Error / aborted. Resource is unavailable; trigger reschedule.                                                                     |
| `Aborted`   | Same handling as `Stopped`.                                                                                                       |
| `Held`      | Reserved for resilience features. Not used by current logic.                                                                      |
| `Suspended` | Reserved for resilience features. Not used by current logic.                                                                      |

The other PackML states are part of the protocol but the controller treats
them as "wait for it to leave this state." Don't add logic that depends on
them yet.

State transitions are validated in `packml.py`. If a station reports an
illegal transition, log a warning and trust the latest state; do not crash.

---

## 8. Process checklist

The checklist is the runtime plan for a single product. It is created by
`process_checklist.py` from the BoP and _expanded_ by `transport_planner.py`
with transport and handoff steps as needed.

### 8.1 Step types

- `BoPStep` — directly from the product's BoP. Completion of all BoPSteps
  means the product is finished.
- `TransportStep` — a movement of the part along the line.
- `HandoffStep` — a custody transfer at a connection point.

The first kind comes from MES; the latter two are inserted by the Line
Controller based on the line configuration and current part location.

### 8.2 Lifecycle

A step is in one of: `pending`, `assigned`, `in_progress`, `complete`,
`failed`. Transitions:

```
pending ──assign──▶ assigned ──CMD sent──▶ in_progress ──Event: complete──▶ complete
                                                       └──Event: error────▶ failed
```

Only `complete` BoPSteps count toward "product done." Transport and handoff
steps are bookkeeping.

### 8.3 Persistence

The checklist is held in memory and snapshotted to disk (JSON) on every state
change. On restart, the controller reloads in-progress checklists and
reconciles them against MQTT-retained state messages.

---

## 9. Transport planning

`transport_planner.py` is invoked by the scheduler when the next BoP step
requires a resource the part is not currently at. Inputs:

- Current part location (resource + connection point).
- Target resource (the one that will perform the next BoP step).
- The line configuration submodel (graph of resources and connection points).
- The current set of available resources (from `resource_manager`).

Output: an ordered list of `TransportStep` and `HandoffStep` instances to
insert into the checklist before the next BoP step.

The planner must:

- Treat the line configuration as a directed graph and find a valid path.
- Insert handoff steps **only** at connection points where the next capability
  on the path has `requires_custody: true`.
- Leave the BoP unchanged. BoP is owned by the product/MES.

If no path exists (e.g. a needed transport resource is offline), return an
empty plan and surface the failure to the scheduler so it can retry later or
abort.

---

## 10. Code style

We're moderately prescriptive. The goal is readable, testable, and easy to
hand off.

- **Python 3.11+**. Use modern syntax (`match`, `|` for unions, etc.).
- **Type hints everywhere.** Public functions must be fully typed. Private
  helpers can skip return types if obvious. Run `mypy --strict` on
  `line_controller/`.
- **Pydantic v2** for any data that crosses a boundary (MQTT, AAS, disk).
- **Docstrings** in Google style on every public function and class. Cover:
  what it does, args, returns, raises. Keep them short — one to three lines
  for most functions.
- **Logging via `structlog`** configured in `logging_config.py`. Never `print`.
  Log keys must include `resource_id`, `actor_id`, `product_id`, `step_id`
  where relevant. Levels:
  - `debug` — fine-grained tracing.
  - `info` — state changes the operator would care about (step started, step
    complete, resource online).
  - `warning` — recoverable anomalies (illegal PackML transition, capability
    missing `requires_custody`).
  - `error` — failures that abort a step or product.
- **No bare `except`.** Catch specific exceptions. If you genuinely need a
  catch-all, log with `exc_info=True` and re-raise unless the function's
  contract is to swallow.
- **Async** for MQTT and AAS I/O. Synchronous code is fine for pure logic
  (matching, planning).
- **Tests** with pytest. Aim for unit tests on planning/matching/checklist
  logic; integration tests with a mocked MQTT broker for the scheduler.

---

## 11. How to add a new station

This is the path to take when the line gets a new resource. Follow it in order.

1. **Author the resource AAS.** Capability submodel must include
   `semanticId`, parameter declarations, actor list, and `requires_custody`
   for every capability. Skill submodel describes how each capability is
   executed (consumed by the station's own controller, not by the Line
   Controller).
2. **Register the resource on the BaSyx server.** Use the same IRI scheme as
   existing resources (`https://aausmartlab.org/...`).
3. **Configure the station's MQTT client.** Topic prefix
   `AAUSmartLab/<line_id>/<resource_id>/`. Implement at minimum: retained
   `Status` with LWT, retained per-actor `State`, subscribers for `CMD` and
   `InfoRequest`, publishers for `ControllerAck`, `Event`, `InfoResponse`.
4. **Update the Line Controller's line configuration submodel.** Add the
   resource node and any connection points it shares with neighboring
   resources. Specify which connection points are physical handoff points.
5. **Restart the station.** It publishes `Status: online`. The
   `resource_manager` picks this up, fetches the new AAS, and adds the
   resource to the live registry. No Line Controller restart required.
6. **Verify.** From the MES UI, confirm the resource appears in the line
   configuration view. Issue a test order that requires the new capability
   and watch the scheduler assign it.

If a new capability `semanticId` is being introduced (not just a new resource
providing an existing capability), make sure products' BoPs that need it
reference the same `semanticId`. Mismatches here are the single most common
source of "why isn't it scheduling?" bugs.

---

## 12. How to add a new capability

1. Decide the `semanticId`. Reuse an existing IRI if the capability already
   exists conceptually; mint a new one only if it's genuinely new.
2. Define the parameter set: name, type, min, max, unit, `semanticId` for each
   parameter.
3. Add the capability to one or more resources' Capability submodels,
   including `requires_custody` and the list of actors that can perform it.
4. If products need to request this capability, update the BoP authoring tool
   (or the MES) to emit BoP steps with the new `semanticId`.
5. No Line Controller code changes should be required. Capability matching is
   data-driven. If you find yourself adding a special case in
   `capability_matcher.py` for a specific capability, stop — that's a sign
   the capability model is missing something the matcher should be reading
   instead.

---

## 13. Things that are deliberately not done yet

These exist as known gaps. Don't paper over them; surface them.

- **Resilience / rescheduling.** The hooks are there (`resource_manager`
  detects offline events; scheduler can re-plan) but the recovery policy is
  not. PackML `Held` / `Suspended` are reserved for this.
- **Cost-based scheduling.** Current scheduler picks the first matching
  resource. Future work: pick by queue length, distance, or operator-defined
  cost.
- **`requires_custody` field.** Not yet in existing capability submodels.
  Default to `true` with a warning when absent.
- **Recovery from handshake failure.** Currently: log and halt. A real
  recovery path is needed.
- **MQTT layer** (`mqtt/client.py`, `mqtt/topics.py`, `mqtt/messages.py`). The
  broker connection, topic builders, and pydantic message schemas described in
  §5 are not yet implemented.
- **`config.py`.** Environment and config-file loading is currently inline in
  `line_controller.py`.
- **`capability_matcher.py`.** Capability-matching logic described in §4.4
  currently lives inside `Resource_Manager/resource_manager.py`
  (`check_skill_and_component`, `_find_resources_with_skill`,
  `_resource_matches_parameters`). Splitting it out is follow-up work.
- **`transport_planner.py`.** Transport-routing logic described in §9
  currently lives inside `Resource_Manager/resource_manager.py`
  (`find_resource_connection_points`, `build_complete_execution_plan`).
  Splitting it out is follow-up work.
- **`process_checklist.py`.** The checklist data structure described in §8 is
  not yet implemented.
- **`handshake.py`.** The handoff handshake state machine described in §6 is
  not yet implemented.
- **`scheduler.py`.** The main scheduling loop is not yet implemented.
- **`packml.py`.** PackML state enum and transition validation described in §7
  are not yet implemented.
- **`logging_config.py`.** Structured logging via `structlog` described in §10
  is not yet set up.
- **`tests/`.** No test suite exists yet.

---

## 14. When in doubt

- Reading something? Go through `aas/client.py` (for AAS) or
  `mqtt/messages.py` (for MQTT; not yet built — see §13). Don't parse raw.
- Building a topic? `mqtt/topics.py` (not yet built — see §13). Never
  hand-format.
- Adding logic to the scheduler? First check whether it belongs in
  `capability_matcher`, `transport_planner`, or `process_checklist` (none yet
  built — see §13). The scheduler should be boring.
- Tempted to special-case a specific resource or capability in code? Stop.
  The data model should carry that, not the code.
