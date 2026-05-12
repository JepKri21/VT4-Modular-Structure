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
from resource_manager import ResourceManager, request_state_update
from capability_matcher import CapabilityMatcher
from inventory_manager import InventoryManager, request_inventory_update
from job_tracker import JobTracker
from occupancy_manager import OccupancyManager
from pre_process_planner import (
    PreProcessPlanner,
    PreProcessPlan,
    PreProcessStep,
    ResourceEndpoint,
    NoShuttleAvailable,
)
from transport_planner import TransportPlanner
from MQTTClientController_Simple import MQTTClientController
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
        inventory: InventoryManager,
        occupancy: OccupancyManager,
        aas_server_base: str,
    ) -> None:
        self.controller = controller
        self.rm = resource_manager
        self.matcher = matcher
        self.planner = pre_process_planner
        self.transport_planner = transport_planner
        self.jobs = job_tracker
        self.inventory = inventory
        self.occupancy = occupancy
        self.aas_server_base = aas_server_base

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
        """Ping every known resource for state, and every storage for inventory."""
        for iri in list(self.rm.resource_shell_ids):
            request_state_update(self.controller, iri)
        request_inventory_update(self.controller, self.rm)
        await asyncio.sleep(1.0)  # let responses arrive

    # ── BoP step pipeline ───────────────────────────────────────────────────

    async def _execute_bop_step(self, handler: WorkOrderHandler, bop: dict) -> None:
        order_id = handler.workorder["OrderId"]
        info = handler.get_step_execution_info(bop["step_id"])
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

        # 2) Resolve storage + shuttle
        try:
            storage, storage_iri = self._resolve_storage_for(info["ComponentReference"])
            shuttle, shuttle_iri = self._pick_shuttle(target_iri, storage_iri)
        except RuntimeError as exc:
            print(f"[bop] cannot resolve endpoints: {exc}")
            return
        print(f"[bop] storage = {storage}")
        print(f"[bop] shuttle = {shuttle}")

        iri_by_topic = {
            target.resource_id:  target_iri,
            storage.resource_id: storage_iri,
            shuttle.resource_id: shuttle_iri,
        }

        # 3) Build + execute pre-process plan
        try:
            plan = self.planner.plan(
                bop_step_id=bop["step_id"],
                order_id=order_id,
                component_reference=info["ComponentReference"] or "",
                current_location=storage,
                target=target,
                shuttle=shuttle,
            )
        except NoShuttleAvailable as exc:
            print(f"[bop] {exc}")
            return

        # Reserve the shuttle (and target actor) for this order while the plan runs.
        reservations = [(shuttle.resource_id, shuttle.actor_name),
                        (target.resource_id, target.actor_name)]
        self.occupancy.commit(order_id, reservations)

        try:
            await self._print_and_execute_plan(plan, iri_by_topic, "pre-process")

            # 4) Execute the BoP step
            await self._execute_bop_command(handler, bop, info, target, target_iri, chosen)

        finally:
            # Release shuttle now that the BoP step is done (target stays until
            # the post-process plan, which we drive separately if this was the
            # last BoP step).
            self.occupancy.release_one(shuttle.resource_id, shuttle.actor_name, order_id)
            self.occupancy.release_one(target.resource_id, target.actor_name, order_id)

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
        component_ref = info.get("ComponentReference") or ""

        bop_skill = chosen["skill_name"]
        bop_params = _flatten_parameters(bop["parameters"])
        bop_params["ComponentReference"] = component_ref

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
            timeout=BOP_TIMEOUT_S,
        )

        if result.result == MS.Result.COMPLETE:
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
            timeout=PRE_PROCESS_TIMEOUT_S,
        )

        if result.result == MS.Result.COMPLETE:
            step.state = StepStates.COMPLETED
            step.timestamps[StepStates.COMPLETED] = datetime.now()
            print(f"[ok]        {step.step_id} ({step.skill}) -> COMPLETED\n")
            self._capture_retrieve_traceability(step, result, order_id)
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
        timeout: float,
    ) -> MS.JobResultMessage:
        """Wait until idle (best-effort), publish CMD, wait for JobResult."""
        idle = await self.rm.wait_for_idle(resource_topic, actor_name, timeout=IDLE_WAIT_S)
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
            parameters=parameters,
        )
        print(f"[cmd]       -> {resource_topic}/{actor_name}  skill={skill}  job={job_id}")
        self.controller.publish_message(target_iri, cmd)

        return await self.jobs.wait_for(job_id, timeout=timeout)

    # ── Endpoint resolution ─────────────────────────────────────────────────

    def _resolve_storage_for(self, component_ref: str) -> tuple[ResourceEndpoint, str]:
        """Pick a storage resource that actually has the component.

        Falls back to "any Retrieve-capable resource" if inventory hasn't been
        seeded yet — useful for the first run before InventoryLevel arrives.
        """
        matches = self.inventory.find_storage_for(component_ref) if component_ref else []
        if matches:
            storage_iri = matches[0][0]
        else:
            offering = self.rm.find_skill_offering("Retrieve")
            if not offering:
                raise RuntimeError("No resource offers a Retrieve skill")
            storage_iri = offering[0][0]
            if component_ref:
                print(
                    f"[plan] inventory has no record of {component_ref}; "
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
        return endpoint, storage_iri

    def _pick_shuttle(
        self, _target_iri: str, _storage_iri: str
    ) -> tuple[ResourceEndpoint, str]:
        """First idle, un-occupied shuttle that exposes the Transport skill.

        The two IRI args are unused today — they're there because the future
        connection-point reachability filter (walking `LineConfiguration`'s
        graph to check that the shuttle reaches both endpoints) will need them.
        For the current line topology the single shuttle pool reaches every
        resource, so we just take the first free one.
        """
        offering = self.rm.find_skill_offering("Transport")
        if not offering:
            raise RuntimeError("No resource offers a Transport skill")

        for shuttle_iri, topic, actors in offering:
            for actor in actors:
                if self.occupancy.is_occupied(topic, actor):
                    continue
                # actor_state may be None (haven't seen one yet) — allow it
                # since wait_for_idle handles the first-command case.
                endpoint = ResourceEndpoint(
                    resource_id=topic,
                    actor_name=actor,
                    has_handoff=self.rm.has_handoff(shuttle_iri),
                )
                return endpoint, shuttle_iri

        raise RuntimeError("No free Transport actor available")

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
        """Move the finished part off the final BoP target and into storage."""
        order_id = handler.workorder["OrderId"]
        product_ref = handler.workorder.get("ProductReference", "")

        # Where did the final BoP step run? Use the last COMPLETED step's
        # assigned_resource — it's the same actor that just finished.
        final = self._final_bop_step(handler)
        if final is None or not final.get("assigned_resource"):
            print("[finalize] no final BoP step to harvest from; skipping post-process")
            return

        target_iri = final["assigned_resource"]
        actors = self.rm.actors_for_skill(
            target_iri, final["required_capability"].rsplit("/", 1)[-1]
        )
        target = ResourceEndpoint(
            resource_id=ResourceManager.topic_id_for_iri(target_iri),
            actor_name=(actors[0] if actors else ""),
            has_handoff=self.rm.has_handoff(target_iri),
        )

        # Where to put it? First Store-capable storage. (Later: respect product type.)
        store_offering = self.rm.find_skill_offering("Store")
        if not store_offering:
            print("[finalize] no resource offers Store; leaving part on target")
            return
        store_iri, store_topic, store_actors = store_offering[0]
        store = ResourceEndpoint(
            resource_id=store_topic,
            actor_name=store_actors[0],
            has_handoff=self.rm.has_handoff(store_iri),
        )

        try:
            shuttle, shuttle_iri = self._pick_shuttle(target_iri, store_iri)
        except RuntimeError as exc:
            print(f"[finalize] post-process needs a shuttle: {exc}")
            return

        plan = self.planner.plan_post_process(
            bop_step_id=final["step_id"],
            order_id=order_id,
            component_reference=product_ref,
            target=target,
            store_destination=store,
            shuttle=shuttle,
        )

        iri_by_topic = {
            target.resource_id:  target_iri,
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
