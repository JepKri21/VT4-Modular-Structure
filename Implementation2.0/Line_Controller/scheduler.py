"""The Line Controller's orchestration loop.

Pulls ready BoP steps from one or more `WorkOrderHandler`s, matches each to a
resource via `CapabilityMatcher`, builds a pre-process plan via
`PreProcessPlanner`, executes the plan + the BoP command over MQTT, then
moves on. When a work order's last BoP step is done it appends a post-process
(Handoff/Transport/Store) to put the finished part back in storage and patches
the product AAS with traceability info.

The scheduler is async + event-driven. It awaits MQTT `JobResult` messages via
`JobTracker.wait_for(...)` and `ResourceManager.wait_for_idle(...)` between
commands. It is concurrency-aware via `OccupancyManager` — but the run loop
itself is single-order today. Wrapping it in `asyncio.gather` for multi-order
is the obvious extension once we want it.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS

from workorder_handler import WorkOrderHandler, StepStates
from resource_manager import ResourceManager
from capability_matcher import CapabilityMatcher
from product_property_matcher import ProductMatcher
from job_tracker import JobTracker
from occupancy_manager import OccupancyManager
from pre_process_planner import (
    PreProcessPlanner,
    PreProcessPlan,
    PreProcessStep,
    ResourceEndpoint,
    NoShuttleAvailable,
    NoReleaseSequence,
    release_sequence_for,
)
from transport_planner import TransportPlanner
from MQTTClientControllerV2 import MQTTClientController
import aas_writer


# Defaults — tweak per environment if needed.
PRE_PROCESS_TIMEOUT_S = 60.0
BOP_TIMEOUT_S = 180.0
IDLE_WAIT_S = 15.0
TICK_INTERVAL_S = 0.5

CAP_HANDOFF = "https://aausmartlab.org/Submodels/Capability/Handoff"


# ─────────────────────────────────────────────────────────────────────────────
# Small utilities
# ─────────────────────────────────────────────────────────────────────────────

def _flatten_parameters(params: dict) -> dict:
    """Strip {semantic_id|semanticId, value} wrapping recursively.

    Work order leaves are encoded as {"name": {"semantic_id": "...", "value": X}}
    but stations expect bare values (or nested bare-value dicts for
    TargetPosition.XPos / .YPos). This unwraps leaves wherever they appear in
    the tree while preserving the surrounding structure.
    """

    def is_leaf_wrapper(node):
        return isinstance(node, dict) and "value" in node and (
            "semantic_id" in node or "semanticId" in node or len(node) <= 2
        )

    def walk(node):
        if is_leaf_wrapper(node):
            return node["value"]
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        return node

    return walk(params or {})


def _pre_process_transformation(
    skill: str,
    component_reference: str,
    handoff_role: str | None = None,
) -> dict:
    """Build the CMD's process_transformation block for a pre/post-process
    step (Retrieve / Handoff / Store / Transport).

    Shapes follow the docstring in MessageStructure.CommandMessage —
    a leg with no cargo is encoded as the whole value being None, not
    as `[None]`:
      - Retrieve : InputTypes=None,    OutputTypes=[<iri>]
      - Store    : InputTypes=[<iri>], OutputTypes=None
      - Transport: InputTypes=[<iri>], OutputTypes=[<iri>]  (loaded)
                   InputTypes=None,    OutputTypes=None     (empty travel)
      - Handoff  : per-side. "sender" releases the part
                   (InputTypes=None, OutputTypes=[<iri>]);
                   "receiver" acquires it
                   (InputTypes=[<iri>], OutputTypes=None).

    component_reference may be an instance IRI or empty. Empty signals
    "no cargo on this side" and is encoded as None on the relevant leg.
    """
    iri = component_reference or None
    if skill == "Retrieve":
        return {"InputTypes": None, "OutputTypes": [iri] if iri else None}
    if skill == "Store":
        return {"InputTypes": [iri] if iri else None, "OutputTypes": None}
    if skill == "Handoff":
        side = [iri] if iri else None
        if handoff_role == "sender":
            return {"InputTypes": None, "OutputTypes": side}
        if handoff_role == "receiver":
            return {"InputTypes": side, "OutputTypes": None}
        # No role provided — fall back to symmetric for safety.
        return {"InputTypes": side, "OutputTypes": side}
    # Transport / anything else: pass the part through. If the leg has
    # no cargo (e.g. empty shuttle travelling to storage), encode both
    # sides as None.
    side = [iri] if iri else None
    return {"InputTypes": side, "OutputTypes": side}


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler
# ─────────────────────────────────────────────────────────────────────────────

class Scheduler:
    """Drives one or more work orders through the line.

    Single-order in the current run loop; multi-order ready in the helpers
    (every per-step method takes the WorkOrderHandler as input).
    """

    def __init__(
        self,
        *,
        controller: MQTTClientController,
        resource_manager: ResourceManager,
        matcher: CapabilityMatcher,
        pre_process_planner: PreProcessPlanner,
        transport_planner: TransportPlanner,
        job_tracker: JobTracker,
        product_matcher: ProductMatcher,
        occupancy: OccupancyManager,
        aas_server_base: str,
        workorder: dict | None = None,
    ) -> None:
        self.controller = controller
        self.rm = resource_manager
        self.matcher = matcher
        self.planner = pre_process_planner
        self.transport_planner = transport_planner
        self.jobs = job_tracker
        self.product_matcher = product_matcher
        self.occupancy = occupancy
        self.aas_server_base = aas_server_base
        # Cached full work order so we can look up an ingredient's
        # Properties when calling ProductMatcher.find_matching_components.
        # The handler also exposes Properties via get_step_execution_info,
        # but only for the ingredient that hosts the current step.
        self.workorder = workorder

        # Per-order traceability: order_id -> {ingredient_name -> specific instance IRI}.
        self._traceability: dict[str, dict[str, str]] = {}

    # ── Public entry point ──────────────────────────────────────────────────

    async def run_order(self, handler: WorkOrderHandler) -> None:
        """Drive a single work order to completion."""
        order_id = handler.workorder["OrderId"]
        product_ref = handler.workorder.get("ProductReference", "")
        self._traceability.setdefault(order_id, {})

        await self._seed_initial_state()

        print(f"\n[run] === starting order {order_id} (product={product_ref}) ===\n")

        while True:
            if self._is_order_complete(handler):
                await self._finalize_order(handler)
                return

            ready = handler.get_ready_steps()
            if not ready:
                # nothing to do this tick — could be waiting on dependencies
                await asyncio.sleep(TICK_INTERVAL_S)
                continue

            bop = ready[0]
            await self._execute_bop_step(handler, bop)

    # ── One-time bootstrap ──────────────────────────────────────────────────

    async def _seed_initial_state(self) -> None:
        """Ask every resource for its current State + InventoryLevel.

        Stations don't publish State on startup — only after their first
        PackML transition — so the first command's `_wait_for_idle` would
        time out without this. `controller.request_data(MessageType)` does
        the fan-out: it sends an InfoRequest to every resource that exposes
        the requested message type.
        """
        self.controller.request_data(MS.StateMessage)
        self.controller.request_data(MS.InventoryLevelMessage)
        await asyncio.sleep(1.0)  # let responses arrive

    # ── State observation (reads shared_handler_variable) ───────────────────

    async def _wait_for_idle(
        self,
        resource_id_short: str,
        actor_name: str,
        timeout: float = IDLE_WAIT_S,
        poll: float = 0.2,
    ) -> bool:
        """Wait until (resource, actor) reports IDLE.

        State lives on `controller.shared_handler_variable["state"]` —
        populated by `handle_state_message` in main.py. We translate the
        topic-side resource_id (idShort) to the shell IRI used as the key
        in that dict.

        Returns:
            True if IDLE was observed within the timeout; False otherwise.
            (Stations don't publish State until their first transition, so
            the very first command may legitimately time out — callers
            should treat False as "send anyway".)
        """
        shell_iri = self.controller.topic_to_shell_id.get(resource_id_short)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if shell_iri is not None:
                state = (
                    self.controller.shared_handler_variable
                    .get("state", {})
                    .get(shell_iri, {})
                    .get(actor_name)
                )
                if state == MS.PackMLState.IDLE:
                    return True
            await asyncio.sleep(poll)
        return False

    # ── BoP step pipeline ───────────────────────────────────────────────────

    async def _execute_bop_step(self, handler: WorkOrderHandler, bop: dict) -> None:
        order_id = handler.workorder["OrderId"]
        info = handler.get_step_execution_info(bop["step_id"])

        # If this step's ingredient is a raw input (ComponentReference still
        # empty), bind it to a concrete instance via the ProductMatcher *now*,
        # before planning or sending any CMD. The pre-process plan and the
        # Retrieve CMD both need a real instance IRI to look up in storage.
        if not info.get("ComponentReference") and info.get("ComponentTypeReference"):
            ingredient_name = info["Ingredient"]
            resolved = self._resolve_input_instance(handler, {
                "name": ingredient_name,
                "ComponentTypeReference": info["ComponentTypeReference"],
                "ComponentReference": "",
                "Properties": (handler.workorder.get("Properties", {}) or {}).get(ingredient_name, {}),
            })
            if resolved:
                info["ComponentReference"] = resolved
                # Refresh the InputIngredients view so subsequent uses (e.g.
                # _build_process_transformation for the BoP CMD) see the bound
                # reference rather than the stale "" we initially got.
                for ing in info.get("InputIngredients") or []:
                    if ing.get("name") == ingredient_name and not ing.get("ComponentReference"):
                        ing["ComponentReference"] = resolved
            else:
                print(
                    f"[bop] no inventory match for '{ingredient_name}' "
                    f"(type={info['ComponentTypeReference']}) — pausing step"
                )
                await asyncio.sleep(TICK_INTERVAL_S)
                return

        print(
            f"\n[bop] step {bop['step_id']}  "
            f"capability={info['CapabilityReference']}  "
            f"component={info['ComponentReference']}"
        )

        # 1) Match → pick target
        print("[bop] running capability matcher…")
        candidates = self.matcher.match(info)
        if not candidates:
            print("[bop] no matching resource — pausing this step")
            await asyncio.sleep(TICK_INTERVAL_S)
            return
        chosen = candidates[0]
        target_iri = chosen["resource_id"]
        target_actors = self.rm.actors_for_skill(target_iri, chosen["skill_name"])
        if not target_actors:
            print(f"[bop] no actors for {chosen['skill_name']} on {target_iri}; aborting step")
            return

        target = ResourceEndpoint(
            resource_id=ResourceManager.topic_id_for_iri(target_iri),
            actor_name=target_actors[0],
            has_handoff=self.rm.has_handoff(target_iri),
        )
        print(f"[bop] target  = {target}")

        handler.update_step(bop["step_id"], StepStates.ASSIGNED, resource=target_iri)

        # 2) Per-input arrival planning.
        # For each input ingredient, decide how to get it to `target`:
        #   - Already at target → no-op.
        #   - Held by a Transport actor (e.g. shuttle from a prior step) →
        #     transport + handoff only; no storage trip.
        #   - Otherwise → storage Retrieve + handoffs + transport + handoff
        #     into target (the classic path).
        inputs = info.get("InputIngredients") or [{
            # Fallback for older shapes: synthesise a single-input list from
            # the step's main ingredient.
            "name": info.get("Ingredient"),
            "ComponentReference": info.get("ComponentReference"),
            "ComponentTypeReference": info.get("ComponentTypeReference"),
            "Properties": (handler.workorder.get("Properties", {}) or {}).get(info.get("Ingredient"), {}),
        }]

        material = info.get("Material")
        combined_steps: list[PreProcessStep] = []
        combined_occupies: list[tuple[str, str]] = []
        iri_by_topic: dict[str, str] = {target.resource_id: target_iri}
        reservations: list[tuple[str, str]] = [(target.resource_id, target.actor_name)]
        shuttles_used: list[tuple[str, str]] = []

        for ing in inputs:
            try:
                sub_plan, sub_iris, sub_reservations = self._plan_arrival_for_input(
                    handler=handler,
                    ingredient=ing,
                    bop_step_id=bop["step_id"],
                    order_id=order_id,
                    target=target,
                    target_iri=target_iri,
                    material=material,
                )
            except RuntimeError as exc:
                print(f"[bop] cannot plan arrival for input '{ing.get('name')}': {exc}")
                return
            if sub_plan is None:
                # Already at target; nothing to transport.
                continue
            combined_steps.extend(sub_plan.steps)
            combined_occupies.extend(sub_plan.occupies_through_bop)
            iri_by_topic.update(sub_iris)
            for res in sub_reservations:
                if res not in reservations:
                    reservations.append(res)
                    if res not in shuttles_used and res[0] != target.resource_id:
                        shuttles_used.append(res)

        plan = PreProcessPlan(
            bop_step_id=bop["step_id"],
            order_id=order_id,
            target=target,
            shuttle=None,
            steps=combined_steps,
            occupies_through_bop=combined_occupies,
        )

        # Reserve all involved actors for this order while the plan runs.
        self.occupancy.commit(order_id, reservations)

        try:
            await self._print_and_execute_plan(plan, iri_by_topic, "pre-process")

            # 3) Execute the BoP step
            await self._execute_bop_command(handler, bop, info, target, target_iri, chosen)

        finally:
            # Release shuttles now that the BoP step is done. release_one is a
            # no-op when an actor still carries cargo, so a shuttle that kept
            # the output (or another input not consumed by this step) stays
            # held for the next BoP step.
            for resource_id, actor_name in shuttles_used:
                self.occupancy.release_one(resource_id, actor_name, order_id)
            self.occupancy.release_one(target.resource_id, target.actor_name, order_id)

    def _plan_arrival_for_input(
        self,
        *,
        handler: WorkOrderHandler,
        ingredient: dict,
        bop_step_id: str,
        order_id: str,
        target: ResourceEndpoint,
        target_iri: str,
        material: str | None,
    ) -> tuple[PreProcessPlan | None, dict[str, str], list[tuple[str, str]]]:
        """Build a PreProcessPlan that gets one input ingredient to `target`.

        Returns (plan, iri_by_topic_additions, reservations). `plan` is None
        when the input is already at the target (no transport needed).
        """
        ingredient_name = ingredient.get("name")
        iris: dict[str, str] = {}
        reservations: list[tuple[str, str]] = []

        # Case A0: the target resource already has a component of the right
        # type in its OWN inventory. Trust the local inventory (type-only
        # lookup, no Properties evaluation) and bind the ingredient to it —
        # the target will self-source it during the BoP CMD, so no transport
        # plan is needed.
        type_ref = ingredient.get("ComponentTypeReference")
        existing_ref = ingredient.get("ComponentReference") or ""
        if not existing_ref and type_ref:
            local_matches = self.product_matcher.find_in_resource_inventory(
                resource_shell_id=target_iri,
                component_type_reference=type_ref,
            )
            if local_matches:
                local_iri = local_matches[0].component_id
                if ingredient_name:
                    handler.update_component_reference(ingredient_name, local_iri)
                    self._traceability.setdefault(order_id, {})[ingredient_name] = local_iri
                ingredient["ComponentReference"] = local_iri
                print(
                    f"[plan] '{ingredient_name}' found in target's own inventory "
                    f"({target.resource_id}); skipping transport"
                )
                print(f"[trace] {order_id}: {ingredient_name} -> {local_iri}")
                return None, iris, reservations

        # Make sure we have a concrete instance IRI to plan around.
        component_ref = self._resolve_input_instance(handler, ingredient)
        if not component_ref:
            raise RuntimeError(
                f"input '{ingredient_name}' could not be resolved to an instance"
            )

        # Case A: already on the target actor — nothing to do.
        holder = self.occupancy.find_holder(component_ref)
        if holder is not None and holder[0] == target.resource_id:
            return None, iris, reservations

        # Case A2: instance lives in the target's own inventory (not on an
        # actor). Same outcome as A0 — target self-sources, no arrival plan.
        location = self.product_matcher.find_component_location(component_ref)
        if location is not None and location.resource_shell_id == target_iri:
            print(
                f"[plan] '{ingredient_name}' ({component_ref}) is in target's own "
                f"inventory ({target.resource_id}); skipping transport"
            )
            return None, iris, reservations

        # Case B: held by a Transport actor (shuttle) — reuse it.
        held = self._find_shuttle_holding(component_ref, order_id)
        if held is not None:
            shuttle, shuttle_iri = held
            print(
                f"[plan] reusing shuttle {shuttle.resource_id}/{shuttle.actor_name} "
                f"already carrying {component_ref}"
            )
            iris[shuttle.resource_id] = shuttle_iri
            reservations.append((shuttle.resource_id, shuttle.actor_name))
            plan = self.planner.plan_shuttle_to_target(
                bop_step_id=bop_step_id,
                order_id=order_id,
                component_reference=component_ref,
                shuttle=shuttle,
                target=target,
            )
            return plan, iris, reservations

        # Case B2: held by a non-shuttle actor with Handoff capability
        # (e.g. an upstream process resource that just produced this part).
        # Pick a shuttle, handoff from the holder to the shuttle, transport,
        # then handoff to target.
        if holder is not None:
            holder_topic, holder_actor = holder
            holder_iri = self._iri_for_topic(holder_topic)
            if holder_iri and self.rm.has_handoff(holder_iri):
                source = ResourceEndpoint(
                    resource_id=holder_topic,
                    actor_name=holder_actor,
                    has_handoff=True,
                )
                shuttle, shuttle_iri = self._pick_shuttle(
                    component_ref,
                    material=material,
                    _target_iri=target_iri,
                    _storage_iri=holder_iri,
                )
                iris[holder_topic] = holder_iri
                iris[shuttle.resource_id] = shuttle_iri
                reservations.append((shuttle.resource_id, shuttle.actor_name))
                release_skills = release_sequence_for(
                    source, component_ref, shell_iri=holder_iri, rm=self.rm
                )
                print(
                    f"[plan] picking up '{ingredient_name}' from "
                    f"{source.resource_id}/{source.actor_name} (release={release_skills})"
                )
                plan = self.planner.plan(
                    bop_step_id=bop_step_id,
                    order_id=order_id,
                    component_reference=component_ref,
                    current_location=source,
                    target=target,
                    shuttle=shuttle,
                    release_skills=release_skills,
                )
                return plan, iris, reservations

        # Case C: classic — fetch from storage.
        storage, storage_iri, picked_instance = self._resolve_storage_for(
            component_ref, ingredient_name=ingredient_name
        )
        shuttle, shuttle_iri = self._pick_shuttle(
            component_ref,
            material=material,
            _target_iri=target_iri,
            _storage_iri=storage_iri,
        )
        if picked_instance and ingredient_name:
            self._traceability.setdefault(order_id, {})[ingredient_name] = picked_instance
            print(f"[trace] {order_id}: {ingredient_name} -> {picked_instance}")

        iris[storage.resource_id] = storage_iri
        iris[shuttle.resource_id] = shuttle_iri
        reservations.append((shuttle.resource_id, shuttle.actor_name))

        release_skills = release_sequence_for(
            storage, component_ref, shell_iri=storage_iri, rm=self.rm
        )
        print(f"[plan] release sequence at source for '{ingredient_name}': {release_skills}")
        plan = self.planner.plan(
            bop_step_id=bop_step_id,
            order_id=order_id,
            component_reference=component_ref,
            current_location=storage,
            target=target,
            shuttle=shuttle,
            release_skills=release_skills,
        )
        return plan, iris, reservations

    async def _execute_bop_command(
        self,
        handler: WorkOrderHandler,
        bop: dict,
        info: dict,
        target: ResourceEndpoint,
        target_iri: str,
        chosen: dict,
    ) -> None:
        order_id = handler.workorder["OrderId"]

        bop_skill = chosen["skill_name"]
        bop_params = _flatten_parameters(bop["parameters"])

        process_transformation = self._build_process_transformation(handler, info)
        if process_transformation is None:
            print(f"[bop] step {bop['step_id']} cannot build process_transformation "
                  "(unresolved inputs) — pausing")
            return

        bop_job_id = f"{order_id}-{bop['step_id']}"
        handler.update_step(bop["step_id"], StepStates.IN_PROGRESS)
        print(f"[bop] step {bop['step_id']} -> IN_PROGRESS")

        result = await self._send_and_wait(
            target_iri=target_iri,
            resource_topic=target.resource_id,
            actor_name=target.actor_name,
            skill=bop_skill,
            order_id=order_id,
            job_id=bop_job_id,
            parameters=bop_params,
            process_transformation=process_transformation,
            timeout=BOP_TIMEOUT_S,
        )

        if result.result == MS.Result.COMPLETE:
            self._apply_output_traceability(handler, info, result)
            self._apply_bop_cargo_transformation(info, result)
            handler.update_step(bop["step_id"], StepStates.COMPLETED)
            print(f"[ok]  BoP step {bop['step_id']} -> COMPLETED")
        else:
            print(f"[fail] BoP step {bop['step_id']} returned {result.result.value}")
            # Leave the step as IN_PROGRESS — operator decides what to do.
            raise RuntimeError(f"BoP step {bop['step_id']} did not complete")

    # ── Pre/post-process step driver ────────────────────────────────────────

    async def _print_and_execute_plan(
        self,
        plan: PreProcessPlan,
        iri_by_topic: dict[str, str],
        label: str,
    ) -> None:
        print(f"\n=== {label} plan ({len(plan.steps)} step(s)) ===")
        for s in plan.steps:
            print(
                f"  {s.step_id:<32s} skill={s.skill:<10s} "
                f"on={s.resource_id}/{s.actor_name}"
            )
        if plan.occupies_through_bop:
            print(f"  shuttle stays occupied through BoP: {plan.occupies_through_bop}")
        print()

        for step in plan.steps:
            await self._execute_step(step, plan.order_id, iri_by_topic)

    async def _execute_step(
        self,
        step: PreProcessStep,
        order_id: str,
        iri_by_topic: dict[str, str],
    ) -> None:
        iri = iri_by_topic.get(step.resource_id)
        if iri is None:
            raise RuntimeError(
                f"No shell IRI registered for resource topic '{step.resource_id}'"
            )

        job_id = f"{order_id}-{step.step_id}"
        step.job_id = job_id
        step.assigned_resource = step.resource_id

        print(
            f"[step]      {step.step_id}  skill={step.skill}  "
            f"on={step.resource_id}/{step.actor_name}"
        )
        step.state = StepStates.ASSIGNED
        step.timestamps[StepStates.ASSIGNED] = datetime.now()

        step.state = StepStates.IN_PROGRESS
        step.timestamps[StepStates.IN_PROGRESS] = datetime.now()

        result = await self._send_and_wait(
            target_iri=iri,
            resource_topic=step.resource_id,
            actor_name=step.actor_name,
            skill=step.skill,
            order_id=order_id,
            job_id=job_id,
            parameters=step.parameters,
            process_transformation=_pre_process_transformation(
                step.skill, step.component_reference, step.handoff_role
            ),
            timeout=PRE_PROCESS_TIMEOUT_S,
        )

        if result.result == MS.Result.COMPLETE:
            step.state = StepStates.COMPLETED
            step.timestamps[StepStates.COMPLETED] = datetime.now()
            print(f"[ok]        {step.step_id} ({step.skill}) -> COMPLETED\n")
            self._capture_retrieve_traceability(step, result, order_id)
            # Apply the step's declared cargo side-effects to the ledger.
            # See PreProcessStep.cargo_transfers for the semantics:
            # Retrieve sets cargo on storage, Handoff moves cargo between
            # actors, Store clears cargo, Transport doesn't change it.
            if step.cargo_transfers:
                self.occupancy.apply_cargo_transfers(step.cargo_transfers)
        else:
            raise RuntimeError(
                f"Step {step.step_id} failed: result={result.result.value}"
            )

    async def _send_and_wait(
        self,
        *,
        target_iri: str,
        resource_topic: str,
        actor_name: str,
        skill: str,
        order_id: str,
        job_id: str,
        parameters: dict,
        process_transformation: dict,
        timeout: float,
    ) -> MS.JobResultMessage:
        """Wait until idle (best-effort), publish CMD, wait for JobResult.

        `process_transformation` is the full {InputTypes: [...], OutputTypes: [...]}
        block with **instance** IRIs (or None for the no-cargo legs of a
        Handoff/Retrieve/Store). The matcher works on types; the scheduler
        resolves to instances right before issuing the CMD.
        """
        idle = await self._wait_for_idle(resource_topic, actor_name, timeout=IDLE_WAIT_S)
        if not idle:
            print(
                f"[warn] never saw IDLE for {resource_topic}/{actor_name}; "
                "sending CMD anyway"
            )

        cmd = MS.CommandMessage(
            timestamp=datetime.now(),
            resource_id=resource_topic,
            skill=skill,
            actor_name=actor_name,
            skill_trigger=MS.CommandType.START,
            order_id=order_id,
            job_id=job_id,
            process_transformation=process_transformation,
            parameters=parameters,
        )
        print(f"[cmd]       -> {resource_topic}/{actor_name}  skill={skill}  job={job_id}")
        self.controller.publish_message(target_iri, cmd)

        return await self.jobs.wait_for(job_id, timeout=timeout)

    # ── Transformation: ingredient names → instance IRIs ────────────────────

    def _resolve_input_instance(
        self,
        handler: WorkOrderHandler,
        ingredient: dict,
    ) -> str | None:
        """Resolve one InputIngredients entry to its concrete instance IRI.

        - If the ingredient already has a ComponentReference, use it.
        - Otherwise ask the ProductMatcher with the ingredient's properties.
          On a hit, persist the choice via handler.update_component_reference
          so subsequent steps see the same instance.

        Returns None if no instance can be resolved.
        """
        existing = ingredient.get("ComponentReference") or ""
        if existing:
            return existing

        type_ref = ingredient.get("ComponentTypeReference")
        if not type_ref:
            return None

        try:
            matches = self.product_matcher.find_matching_components(
                component_type_reference=type_ref,
                order_properties=ingredient.get("Properties") or {},
            )
        except Exception as exc:
            print(f"[trans] product matcher lookup failed for {ingredient.get('name')}: {exc}")
            return None
        if not matches:
            print(f"[trans] no inventory match for ingredient '{ingredient.get('name')}' "
                  f"(type={type_ref})")
            return None
        instance = matches[0].component_id
        handler.update_component_reference(ingredient["name"], instance)
        print(f"[trans] resolved {ingredient.get('name')} -> {instance}")
        return instance

    def _build_process_transformation(
        self,
        handler: WorkOrderHandler,
        info: dict,
    ) -> dict | None:
        """Build the {InputTypes: [...], OutputTypes: [...]} CMD payload.

        Inputs and outputs are full instance IRIs (or None for legs that
        don't carry a component, per MessageStructure.CommandMessage docs).
        Returns None if any required input cannot be resolved — the caller
        should treat that as "no candidate" and pause the step.
        """
        input_iris: list[str | None] = []
        for ing in info.get("InputIngredients") or []:
            iri = self._resolve_input_instance(handler, ing)
            if iri is None:
                # No instance available for a required input. Caller pauses.
                return None
            input_iris.append(iri)

        # For outputs, prefer the cached info value but fall back to the
        # workorder's current Ingredients dict — _resolve_input_instance
        # may have written an instance IRI there after info was built.
        ingredients = (handler.workorder or {}).get("Ingredients", {}) or {}
        output_iris: list[str | None] = []
        for ing in info.get("OutputIngredients") or []:
            iri = (
                ing.get("ComponentReference")
                or ingredients.get(ing.get("name"), {}).get("ComponentReference")
                or None
            )
            output_iris.append(iri)

        return {"InputTypes": input_iris, "OutputTypes": output_iris}

    def _apply_bop_cargo_transformation(
        self,
        info: dict,
        result: MS.JobResultMessage,
    ) -> None:
        """Reflect the BoP's input→output transformation in the cargo ledger.

        After a transforming BoP step (e.g. Assemble: BottomCover + PCB →
        BottomCoverPCB) completes, any actor still carrying one of the
        consumed input IRIs should now carry the output IRI instead — the
        physical part *is* the output now. Without this, the next BoP step
        would still see the old input on the target and fail to find the
        output anywhere on the line.

        Uses the JobResult's process_transformation if present (station's
        authoritative answer), else falls back to the step's declared
        ProcessTransformation. No-op if there's no output IRI or if input
        and output are the same.
        """
        process_t = (result.process_transformation
                     or info.get("ProcessTransformation")
                     or {})
        input_iris = {i for i in (process_t.get("InputTypes") or []) if i}
        output_iris = [o for o in (process_t.get("OutputTypes") or []) if o]
        if not output_iris or not input_iris:
            return
        output_iri = output_iris[0]
        if output_iri in input_iris and len(input_iris) == 1:
            return  # identity transformation (e.g. Drilling)
        for resource_id, actor_name, cargo in list(self.occupancy.all_cargo()):
            if cargo in input_iris and cargo != output_iri:
                self.occupancy.set_cargo(resource_id, actor_name, output_iri)
                print(
                    f"[cargo]     {resource_id}/{actor_name}: "
                    f"{cargo} -> {output_iri} (transformation)"
                )

    def _apply_output_traceability(
        self,
        handler: WorkOrderHandler,
        info: dict,
        result: MS.JobResultMessage,
    ) -> None:
        """After a JobResult lands, fill in any output ingredient's
        ComponentReference that was empty in the work order.

        The station's authoritative answer is in
        `result.process_transformation["OutputTypes"]` (full instance IRIs,
        same order as the step's OutputIngredients).
        """
        output_iris = (result.process_transformation or {}).get("OutputTypes") or []
        for ing, iri in zip(info.get("OutputIngredients") or [], output_iris):
            if not iri:
                continue
            if not ing.get("ComponentReference"):
                handler.update_component_reference(ing["name"], iri)
                print(f"[trans] output {ing['name']} -> {iri}")

    # ── Endpoint resolution ─────────────────────────────────────────────────

    def _resolve_storage_for(
        self,
        component_ref: str,
        ingredient_name: str | None = None,
    ) -> tuple[ResourceEndpoint, str, str | None]:
        """Pick a storage resource that actually has the component.

        Uses ProductMatcher:
          - If `ingredient_name` is supplied and the work order has properties
            for it, `find_matching_components(type, properties)` narrows down
            to instances that meet the constraints (material, dimensions,
            etc).
          - Otherwise type-only lookup via the index.
          - Final fallback: any Retrieve-capable resource (first run, before
            any InventoryLevel has arrived).

        Returns:
            (endpoint, shell_iri, picked_instance_id) — the third value is
            the specific instance the matcher chose (or None for the
            fallback path). The scheduler uses it for traceability.
        """
        picked_instance: str | None = None
        storage_iri: str | None = None

        if component_ref:
            # Preferred path: component_ref is a concrete instance IRI
            # (already resolved by _resolve_input_instance). Look it up in
            # the inventory index directly.
            location = self.product_matcher.find_component_location(component_ref)
            if location is not None:
                storage_iri = location.resource_shell_id
                picked_instance = location.component_id

        if storage_iri is None and component_ref:
            # Fallback: treat component_ref as a TYPE IRI (e.g. when the
            # caller hasn't pre-resolved to an instance).
            props = (
                (self.workorder or {})
                .get("Properties", {})
                .get(ingredient_name, {})
                if ingredient_name
                else {}
            )
            try:
                if props:
                    matches = self.product_matcher.find_matching_components(
                        component_type_reference=component_ref,
                        order_properties=props,
                    )
                else:
                    matches = (
                        self.product_matcher.inventory_indexer
                        .find_by_component_type(component_ref)
                    )
                    matches = [
                        # Adapt indexed-component → ComponentLocation-shaped dict-like.
                        type("M", (), {
                            "component_id": c.component_id,
                            "resource_shell_id": c.resource_shell_id,
                            "actor_names": c.accessible_actors,
                        })()
                        for c in matches
                    ]
            except Exception as exc:
                print(f"[plan] product matcher lookup failed: {exc}")
                matches = []

            if matches:
                chosen = matches[0]
                storage_iri = chosen.resource_shell_id
                picked_instance = getattr(chosen, "component_id", None)

        if storage_iri is None:
            offering = self.rm.find_skill_offering("Retrieve")
            if not offering:
                raise RuntimeError("No resource offers a Retrieve skill")
            storage_iri = offering[0][0]
            if component_ref:
                print(
                    f"[plan] product matcher has no record of {component_ref}; "
                    f"falling back to first Retrieve resource"
                )

        actors = self.rm.actors_for_skill(storage_iri, "Retrieve")
        if not actors:
            raise RuntimeError(f"No Retrieve actors on {storage_iri}")
        endpoint = ResourceEndpoint(
            resource_id=ResourceManager.topic_id_for_iri(storage_iri),
            actor_name=actors[0],
            has_handoff=self.rm.has_handoff(storage_iri),
        )
        return endpoint, storage_iri, picked_instance

    def _iri_for_topic(self, topic_id: str) -> str | None:
        """Reverse-lookup the shell IRI for a known resource topic id."""
        for iri in self.rm.resource_shell_ids:
            if ResourceManager.topic_id_for_iri(iri) == topic_id:
                return iri
        return None

    def _find_shuttle_holding(
        self,
        component_ref: str,
        order_id: str | None,
    ) -> tuple[ResourceEndpoint, str] | None:
        """If some Transport actor already carries `component_ref`, return it.

        Honored only when the actor is unowned OR owned by the same order —
        we never poach a held shuttle from another order. Returns None when
        no Transport actor holds the part.
        """
        if not component_ref:
            return None
        holder = self.occupancy.find_holder(component_ref)
        if holder is None:
            return None
        topic, actor = holder
        # The holder may or may not be a shuttle. Only treat as such if a
        # Transport-offering resource matches this topic.
        for shuttle_iri, shuttle_topic, actors in self.rm.find_skill_offering("Transport"):
            if shuttle_topic != topic or actor not in actors:
                continue
            owner = self.occupancy.owner_of(topic, actor)
            if owner not in (None, order_id):
                return None
            endpoint = ResourceEndpoint(
                resource_id=topic,
                actor_name=actor,
                has_handoff=self.rm.has_handoff(shuttle_iri),
            )
            return endpoint, shuttle_iri
        return None

    def _pick_shuttle(
        self,
        component_ref: str,
        material: str | None = None,
        _target_iri: str | None = None,
        _storage_iri: str | None = None,
    ) -> tuple[ResourceEndpoint, str]:
        """First available shuttle whose Transport capability supports
        the component (and material, if known).

        Filters applied, in order:
        - The transport resource's Transport capability must list this
          component (or its type prefix) in its `SupportedComponents`, AND
          the material must be in `AllowedMaterials`. Either list empty
          means "no restriction" — same convention as CapabilityMatcher.
        - The actor must be `available` per OccupancyManager: not reserved
          for any order AND not currently carrying cargo.

        The two IRI args are unused today — they'll feed the future
        connection-point reachability filter (walking LineConfiguration's
        graph to verify the shuttle reaches both endpoints).
        """
        offering = self.rm.find_skill_offering("Transport")
        if not offering:
            raise RuntimeError("No resource offers a Transport skill")

        for shuttle_iri, topic, actors in offering:
            if not self._transport_supports(shuttle_iri, component_ref, material):
                print(
                    f"[plan] shuttle {topic} skipped: Transport capability "
                    f"doesn't support component={component_ref} material={material}"
                )
                continue
            for actor in actors:
                if not self.occupancy.is_available(topic, actor):
                    continue
                endpoint = ResourceEndpoint(
                    resource_id=topic,
                    actor_name=actor,
                    has_handoff=self.rm.has_handoff(shuttle_iri),
                )
                return endpoint, shuttle_iri

        raise RuntimeError(
            f"No free Transport actor that supports {component_ref} / {material}"
        )

    def _transport_supports(
        self,
        shuttle_iri: str,
        component_ref: str,
        material: str | None = None,
    ) -> bool:
        """Does the shuttle's Transport capability advertise this component
        AND allow this material?

        A capability with no SupportedComponents OR no AllowedMaterials is
        treated as universal for that dimension — same convention as
        CapabilityMatcher._check_component / _check_material.
        """
        if not component_ref:
            return True
        skills = self.rm.get_resource_skills(shuttle_iri)
        cap_ref = skills.get("Transport", {}).get("CapabilitySubmodelReference")
        if not cap_ref:
            return False
        cap_data = self.rm.get_capability_parameters(cap_ref)
        if not cap_data:
            return False
        _params, supported, allowed_materials, _transformations = cap_data

        # 1) SupportedComponents check
        if supported and not any(
            component_ref == c or component_ref.startswith(c + "/")
            for c in supported
        ):
            return False

        # 2) AllowedMaterials check (mirrors CapabilityMatcher._check_material)
        if material and allowed_materials:
            allowed = [m for m in allowed_materials if m]
            if allowed:
                if material in allowed:
                    return True
                basenames = {url.rsplit("/", 1)[-1] for url in allowed}
                if material not in basenames:
                    return False

        return True

    # ── Traceability ────────────────────────────────────────────────────────

    def _capture_retrieve_traceability(
        self,
        step: PreProcessStep,
        result: MS.JobResultMessage,
        order_id: str,
    ) -> None:
        """If the step was a Retrieve, record the specific instance picked.

        The storage station puts the actual item IRI in
        `result.output_parameters["ComponentReference"]`. We don't currently
        know which `ingredient_name` requested this step (the pre-process
        planner doesn't carry it), so we use `component_reference` from the
        step as the key — same value the work order's `Ingredients` map uses.
        """
        if step.skill != "Retrieve":
            return
        outputs = result.output_parameters or {}
        instance = outputs.get("ComponentReference")
        if not instance:
            return
        self._traceability.setdefault(order_id, {})[step.component_reference] = instance
        print(f"[trace] {order_id}: {step.component_reference} -> {instance}")

    # ── Finalization (post-process + AAS writeback + status) ────────────────

    def _is_order_complete(self, handler: WorkOrderHandler) -> bool:
        return all(
            s["state"] == StepStates.COMPLETED
            for s in handler.execution_plan["steps"]
        )

    async def _finalize_order(self, handler: WorkOrderHandler) -> None:
        order_id = handler.workorder["OrderId"]
        product_ref = handler.workorder.get("ProductReference", "")
        print(f"\n[finalize] order {order_id} — all BoP steps complete")

        await self._run_post_process(handler)
        self._write_traceability(order_id, product_ref)
        self._publish_order_complete(handler)

        print(f"[finalize] order {order_id} -> COMPLETE\n")

    async def _run_post_process(self, handler: WorkOrderHandler) -> None:
        """Move the finished part off wherever it currently sits and into storage.

        The cargo ledger is authoritative about "where is the product right
        now" — after the final BoP step, the part may still be on the shuttle
        (no-handoff case) rather than on the target. We start the post-process
        from whichever actor currently has cargo.
        """
        order_id = handler.workorder["OrderId"]
        product_ref = handler.workorder.get("ProductReference", "")

        final = self._final_bop_step(handler)
        if final is None:
            print("[finalize] no final BoP step recorded; skipping post-process")
            return

        # ── 1. Find the current holder via cargo state ─────────────────────
        holder_topic_actor = self._find_cargo_holder_for_order(order_id)
        if holder_topic_actor is None:
            print(
                "[finalize] no actor reports carrying this order's part; "
                "skipping post-process. If a Handoff was expected this is "
                "the place to look."
            )
            return
        holder_topic, holder_actor = holder_topic_actor
        holder_iri = self.controller.topic_to_shell_id.get(holder_topic)
        if holder_iri is None:
            print(f"[finalize] cannot resolve IRI for holder {holder_topic}")
            return
        holder = ResourceEndpoint(
            resource_id=holder_topic,
            actor_name=holder_actor,
            has_handoff=self.rm.has_handoff(holder_iri),
        )
        print(f"[finalize] product currently held by {holder}")

        # ── 2. Pick destination storage (first Store-capable resource) ─────
        store_offering = self.rm.find_skill_offering("Store")
        if not store_offering:
            print("[finalize] no resource offers Store; leaving part on holder")
            return
        store_iri, store_topic, store_actors = store_offering[0]
        store = ResourceEndpoint(
            resource_id=store_topic,
            actor_name=store_actors[0],
            has_handoff=self.rm.has_handoff(store_iri),
        )

        # ── 3. Pick a shuttle (skip if the shuttle itself is the holder) ───
        shuttle: ResourceEndpoint | None
        shuttle_iri: str
        if self._is_transport_actor(holder_iri):
            # The carrier IS a shuttle — it can just move to the store zone.
            shuttle, shuttle_iri = holder, holder_iri
        else:
            try:
                shuttle, shuttle_iri = self._pick_shuttle(
                    product_ref, _target_iri=holder_iri, _storage_iri=store_iri
                )
            except RuntimeError as exc:
                print(f"[finalize] post-process needs a shuttle: {exc}")
                return

        plan = self.planner.plan_post_process(
            bop_step_id=final["step_id"],
            order_id=order_id,
            component_reference=product_ref,
            target=holder,                     # plan starts where the part actually is
            store_destination=store,
            shuttle=shuttle,
        )

        iri_by_topic = {
            holder.resource_id:  holder_iri,
            store.resource_id:   store_iri,
            shuttle.resource_id: shuttle_iri,
        }

        self.occupancy.commit(order_id, [
            (shuttle.resource_id, shuttle.actor_name),
        ])
        try:
            await self._print_and_execute_plan(plan, iri_by_topic, "post-process")
        finally:
            self.occupancy.release(order_id)

    def _find_cargo_holder_for_order(
        self, order_id: str
    ) -> tuple[str, str] | None:
        """Pick an actor that's currently carrying *something* and was
        reserved by this order. If nothing's carrying, return None.

        For one-order operation this is just "first cargo on the line".
        For multi-order this needs to disambiguate by what was loaded
        for which order — left as a TODO until multi-order matters.
        """
        # Simplest correct version: any actor with cargo whose reservation
        # belongs to this order, OR (failing that) any actor with cargo.
        owned: tuple[str, str] | None = None
        anything: tuple[str, str] | None = None
        for resource_id, actor, _cargo in self.occupancy.all_cargo():
            if anything is None:
                anything = (resource_id, actor)
            if self.occupancy.owner_of(resource_id, actor) == order_id:
                owned = (resource_id, actor)
                break
        return owned or anything

    def _is_transport_actor(self, shell_iri: str) -> bool:
        return "Transport" in self.rm.get_resource_skills(shell_iri)

    def _final_bop_step(self, handler: WorkOrderHandler) -> dict | None:
        """The step with the highest precedence (deepest in the BoP)."""
        steps = handler.execution_plan["steps"]
        if not steps:
            return None
        return max(steps, key=lambda s: s["precedence"])

    def _write_traceability(self, order_id: str, product_ref: str) -> None:
        used = self._traceability.get(order_id, {})
        if not used or not product_ref:
            return
        # WorkOrder's product_ref is short (e.g. "Bottom_Cover_Drilled_PCB-BCDP001").
        # Convert to a shell IRI candidate; if it's already an IRI it'll pass through.
        if product_ref.startswith("http"):
            shell_iri = product_ref
        else:
            shell_iri = f"https://aausmartlab.org/Shells/Assembly/{product_ref}"
        aas_writer.write_traceability(self.aas_server_base, shell_iri, used)

    def _publish_order_complete(self, handler: WorkOrderHandler) -> None:
        """Publish a WorkOrderStatus message indicating the order is done."""
        order_id = handler.workorder["OrderId"]
        msg = MS.WorkOrderStatusMessage(
            timestamp=datetime.now(),
            order_id=order_id,
            line_id=self.controller.base_topic.rsplit("/", 1)[-1],
            status=MS.WorkOrderStatus.COMPLETE,
            message=None,
            seq_no=None,
        )
        topic = f"{self.controller.base_topic}/WorkOrderStatus/{order_id}"
        try:
            self.controller.client.publish(topic, msg.model_dump_json())
            print(f"[status]   published WorkOrderStatus.COMPLETE on {topic}")
        except Exception as e:
            print(f"[status]   publish failed: {e}")
