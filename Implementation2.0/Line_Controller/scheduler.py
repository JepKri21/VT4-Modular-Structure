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
from MQTTClientControllerV2 import MQTTClientController, CmdNoAckError
from order_recovery import RecoveryAction, RecoveryReason
import aas_writer


# Defaults — tweak per environment if needed.
PRE_PROCESS_TIMEOUT_S = 60.0
BOP_TIMEOUT_S = 180.0
IDLE_WAIT_S = 15.0
TICK_INTERVAL_S = 0.5
# How many consecutive ticks a step may fail arrival planning before we give
# up and let it abort. At TICK_INTERVAL_S=0.5s this is ~60s of retrying — long
# enough for a busy shuttle to free up, short enough that a truly un-runnable
# step (missing input, no capable transport) doesn't park the order forever.
PLAN_RETRY_BUDGET = 120

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
        locations: dict | None = None,
        recovery=None,
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
        self.locations = locations
        # OrderRecovery — optional so existing call sites in tests still
        # construct Scheduler without it. When set, run_order delegates
        # recovery to this object on detectable step failures.
        self.recovery = recovery
        # order_id -> WorkOrderHandler. Used by the unreachable callback
        # so we can map a freshly-offline resource to the handler(s) that
        # need to be re-evaluated.
        self._active_orders: dict[str, "WorkOrderHandler"] = {}
        # Cached full work order so we can look up an ingredient's
        # Properties when calling ProductMatcher.find_matching_components.
        # The handler also exposes Properties via get_step_execution_info,
        # but only for the ingredient that hosts the current step.
        self.workorder = workorder

        # Per-order traceability: order_id -> {ingredient_name -> specific instance IRI}.
        self._traceability: dict[str, dict[str, str]] = {}

        aas_writer.fetch_process_tracking_template(aas_server_base)

        # Cross-order instance reservation. Once an order picks a concrete
        # component instance (e.g. BottomCoverABSBlack-<uuid>) from a shared
        # inventory, claim it so a concurrent order doesn't also pick it.
        # Value is (order_id, resource_shell_id, inventory_name, slot_id) so
        # we can release the AAS SlotReserved flag when the slot empties.
        # Released after Retrieve completes; order-end release is safety net.
        self._reserved_instances: dict[str, tuple[str, str, str, str]] = {}

        # Round-robin cursor for shuttle picks. Rotates the starting actor on
        # each _pick_shuttle call so successive picks spread across actors
        # instead of always grabbing the first one in the list.
        self._shuttle_pick_cursor: int = 0

        # Bounded retry for arrival planning. A step that can't be planned
        # (no free/ capable transport, missing input) pauses and retries so
        # a *transient* shortage clears — but only up to PLAN_RETRY_BUDGET
        # ticks. Past that we treat it as un-runnable and let the failure
        # propagate to recovery, which aborts the order instead of leaving
        # it parked in the dispatch queue forever. Keyed by (order, step).
        self._plan_retry_counts: dict[tuple[str, str], int] = {}

        # Bounded retry for the occupancy commit. Mirrors _plan_retry_counts
        # but counts ticks a step spent unable to reserve its actors. A blocked
        # commit rolls the step back to PENDING and re-plans (re-picking a
        # currently-free shuttle) so a shuttle we picked but lost to another
        # order between plan and commit doesn't pin us forever — the pin is
        # what turns hold-and-wait into a circular-wait deadlock. Keyed by
        # (order, step).
        self._commit_retry_counts: dict[tuple[str, str], int] = {}

        # Serializes inventory refreshes across concurrent orders. The refresh
        # itself runs in a worker thread (off the event loop) but mutates the
        # shared ProductMatcher index, so two orders must not rebuild it at the
        # same time. Holding the lock only spans the threaded refresh, so the
        # loop stays free for the other order's non-inventory work.
        self._inventory_lock = asyncio.Lock()

    # ── Cross-order instance reservation ────────────────────────────────────

    def _reserve_instance(
        self,
        instance_iri: str,
        order_id: str,
        resource_shell_id: str = "",
        inventory_name: str = "",
        slot_id: str = "",
    ) -> bool:
        """Claim a component instance for an order.

        Returns True on a fresh reservation OR a re-claim by the same order.
        Returns False if another order already holds it (caller should pick
        a different candidate or pause).
        """
        entry = self._reserved_instances.get(instance_iri)
        if entry is None:
            self._reserved_instances[instance_iri] = (order_id, resource_shell_id, inventory_name, slot_id)
            return True
        return entry[0] == order_id

    def _release_instance_reservation(self, instance_iri: str, order_id: str) -> None:
        """Release a single slot reservation and clear SlotReserved on BaSyx."""
        entry = self._reserved_instances.get(instance_iri)
        if entry is not None and entry[0] == order_id:
            _, shell_id, inv_name, slot = entry
            del self._reserved_instances[instance_iri]
            print(f"[reserve] released {instance_iri} (slot={slot} now empty)")
            if shell_id and inv_name and slot:
                self._patch_slot_reserved(shell_id, inv_name, slot, False)

    def _consume_instance(self, instance_iri: str, order_id: str) -> None:
        """Permanently remove a consumed instance from its resource Inventory slot.

        Called at the actual consumption event — a Retrieve that pulls a part
        out of storage, or an Assemble that ate a part from a resource feeder.
        The matcher indexes a slot only while its ComponentShellReference holds
        a value (see InventoryIndexer.rebuild_from_aas), so emptying that field
        is what stops the instance being re-selected by a later order.

        SlotReserved is only a cross-order concurrency guard; clearing it alone
        (the old behaviour) left ComponentShellReference filled, so the instance
        leaked straight back into the freely-pickable pool and got assembled
        again — the duplicate ProcessHistory Assemble_N records. Here the
        controller clears ComponentShellReference itself and releases the
        reservation **only after the slot is confirmed empty**; if the clear
        didn't take, the reservation is kept so the part stays claimed rather
        than re-appearing.

        No-ops when the instance isn't a reservation we own — i.e. a part
        already emptied at Retrieve, or a transported-in sub-assembly that was
        never a reserved storage/feeder instance.
        """
        entry = self._reserved_instances.get(instance_iri)
        if entry is None or entry[0] != order_id:
            return
        _, shell_id, inv_name, slot = entry
        if not (shell_id and inv_name and slot):
            # No slot metadata to clear — fall back to a plain release.
            self._release_instance_reservation(instance_iri, order_id)
            return
        if not self._clear_slot_component(shell_id, inv_name, slot):
            print(
                f"[consume] {instance_iri}: slot {slot} not confirmed empty — "
                "keeping reservation so it is not re-selected"
            )
            return
        self._release_instance_reservation(instance_iri, order_id)

    def _clear_slot_component(
        self,
        resource_shell_id: str,
        inventory_name: str,
        slot_id: str,
    ) -> bool:
        """Empty a slot's ComponentShellReference on BaSyx, then verify.

        Drops the reference *value* entirely (not an empty-keys reference,
        which would crash the station parser at value['keys'][0]), mirroring
        the storage station's own slot-empty write. Returns True iff a re-read
        confirms the slot no longer holds a component.
        """
        import base64
        import requests as _requests
        submodel_iri = f"{resource_shell_id}/Inventory"
        b64 = base64.urlsafe_b64encode(submodel_iri.encode()).decode().rstrip("=")
        path = f"Inventories.{inventory_name}.StoredComponents.{slot_id}.ComponentShellReference"
        url = f"{self.aas_server_base}/submodels/{b64}/submodel-elements/{path}"
        try:
            resp = _requests.get(url, timeout=3)
            if resp.status_code != 200:
                print(f"[consume] GET {slot_id} ref -> {resp.status_code}")
                return False
            element = resp.json()
            element.pop("value", None)
            put = _requests.put(url, json=element, timeout=3)
            if put.status_code not in (200, 201, 204):
                print(f"[consume] PUT clear {slot_id} -> {put.status_code} {put.text[:160]}")
                return False
            check = _requests.get(url, timeout=3)
            if check.status_code != 200:
                return False
            val = check.json().get("value")
            empty = not val or not (val.get("keys") if isinstance(val, dict) else None)
            if empty:
                print(f"[consume] AAS slot {slot_id} ComponentShellReference cleared")
            return empty
        except Exception as exc:
            print(f"[consume] clear failed for {slot_id}: {exc}")
            return False

    def _consume_inputs_from_inventory(self, process_transformation: dict, order_id: str) -> None:
        """Empty the Inventory slots of every feeder input an Assemble consumed.

        Skips the identity case (input IRI also an output, e.g. Drilling) and
        defers the "is this actually a reserved feeder part?" decision to
        _consume_instance, which no-ops on already-emptied or never-reserved
        inputs.
        """
        inputs = (process_transformation or {}).get("InputTypes") or []
        outputs = {o for o in ((process_transformation or {}).get("OutputTypes") or []) if o}
        for iri in inputs:
            if not iri or iri in outputs:
                continue
            self._consume_instance(iri, order_id)

    def _patch_slot_reserved(
        self,
        resource_shell_id: str,
        inventory_name: str,
        slot_id: str,
        reserved: bool,
    ) -> None:
        """Write SlotReserved to the storage station's Inventory submodel on BaSyx."""
        import base64
        import requests as _requests
        submodel_iri = f"{resource_shell_id}/Inventory"
        b64 = base64.urlsafe_b64encode(submodel_iri.encode()).decode().rstrip("=")
        path = f"Inventories.{inventory_name}.StoredComponents.{slot_id}.SlotReserved"
        url = f"{self.aas_server_base}/submodels/{b64}/submodel-elements/{path}/$value"
        value = "true" if reserved else "false"
        try:
            _requests.patch(url, json=value, timeout=3)
            print(f"[reserve] AAS SlotReserved={value} -> {slot_id}")
        except Exception as exc:
            print(f"[reserve] AAS PATCH failed for {slot_id}: {exc}")

    def _release_order_reservations(self, order_id: str) -> None:
        # Capture full entries before deletion so we can clear SlotReserved
        # on the AAS for each freed slot. Without this, an order that ends
        # (success or failure) leaves SlotReserved=true forever and the
        # matcher will silently skip that slot on every future order.
        freed_entries = [
            (iri, entry) for iri, entry in self._reserved_instances.items()
            if entry[0] == order_id
        ]
        for iri, _entry in freed_entries:
            del self._reserved_instances[iri]
        for _iri, (_owner, shell_id, inv_name, slot) in freed_entries:
            if shell_id and inv_name and slot:
                self._patch_slot_reserved(shell_id, inv_name, slot, False)
        if freed_entries:
            print(f"[reserve] order={order_id} released {len(freed_entries)} instance reservation(s)")

    # ── Public entry point ──────────────────────────────────────────────────

    async def run_order(self, handler: WorkOrderHandler) -> None:
        """Drive a single work order to completion.

        Recoverable failures (CMD never ACKed, JobResult never arrived,
        JobResult was INCOMPLETE) route through OrderRecovery if one is
        wired. Recovery either restarts the order (resetting non-COMPLETED
        steps and excluding the failed resource) or aborts. Without a
        recovery instance the exception propagates as before.
        """
        order_id = handler.workorder["OrderId"]
        product_ref = handler.workorder.get("ProductReference", "")
        self._traceability.setdefault(order_id, {})
        self._active_orders[order_id] = handler
        # Capture the start so OrderCompleted can carry both timestamps.
        order_started_at = datetime.now()
        # Status is decided per branch and read in the finally block.
        order_final_status = MS.OrderStatus.ABORTED
        # Per-attempt context. _execute_bop_step refreshes these so
        # recovery knows which resource/step to attribute the failure to.
        self._current_bop_target_iri = None
        self._current_bop_target_topic = None
        self._current_bop_step_info = None

        await self._seed_initial_state()

        print(f"\n[run] === starting order {order_id} (product={product_ref}) ===\n")

        try:
            while True:
                if self._is_order_complete(handler):
                    await self._finalize_order(handler)
                    order_final_status = MS.OrderStatus.COMPLETED
                    return

                ready = handler.get_ready_steps()
                if not ready:
                    await asyncio.sleep(TICK_INTERVAL_S)
                    continue

                bop = ready[0]
                try:
                    await self._execute_bop_step(handler, bop)
                except (CmdNoAckError, asyncio.TimeoutError, RuntimeError) as exc:
                    if self.recovery is None:
                        raise
                    reason = self._classify_recovery_reason(exc)
                    decision = self.recovery.handle_failure(
                        handler=handler,
                        reason=reason,
                        failed_resource_iri=self._current_bop_target_iri,
                        failed_resource_topic=self._current_bop_target_topic,
                        failed_step_info=self._current_bop_step_info,
                        detail=str(exc) or type(exc).__name__,
                    )
                    if decision.action == RecoveryAction.RESTART:
                        # Wipe per-attempt instance bindings so the next
                        # attempt re-resolves inputs (a stuck cargo holder
                        # might still own the prior instance). Reservations
                        # that aren't stuck were already released in recovery.
                        self._traceability.pop(order_id, None)
                        self._traceability.setdefault(order_id, {})
                        self._release_order_reservations(order_id)
                        continue
                    # ABORT: stop driving this order.
                    return
        finally:
            self._active_orders.pop(order_id, None)
            # Drop this order's arrival-planning and commit retry counters.
            for key in [k for k in self._plan_retry_counts if k[0] == order_id]:
                self._plan_retry_counts.pop(key, None)
            for key in [k for k in self._commit_retry_counts if k[0] == order_id]:
                self._commit_retry_counts.pop(key, None)
            self._release_order_reservations(order_id)
            # release() leaves stuck cargo claimed — exactly what we want
            # when an order aborts mid-flight with a part on a shuttle.
            self.occupancy.release(order_id)
            # Emit OrderCompleted for the metrics bridge. Fire-and-forget;
            # any publish failure here must not mask the original outcome.
            try:
                self._publish_order_completed(
                    order_id=order_id,
                    product_ref=product_ref,
                    started_at=order_started_at,
                    status=order_final_status,
                    attempt_count=handler.get_attempt_count(),
                )
            except Exception as exc:
                print(f"[order_completed] publish failed: {exc}")

    def _publish_order_completed(
        self,
        *,
        order_id: str,
        product_ref: str,
        started_at: datetime,
        status,
        attempt_count: int,
    ) -> None:
        """Publish the per-order completion event to the metrics bridge.

        Topic: AAUSmartLab/<line_id>/Controller/OrderCompleted.
        Uses the controller's raw paho client directly because there's no
        per-resource topic map for the Controller namespace.
        """
        topic = f"{self.controller.base_topic}/Controller/OrderCompleted"
        msg = MS.OrderCompletedMessage(
            timestamp=datetime.now(),
            order_id=order_id,
            product_ref=product_ref or None,
            started_at=started_at,
            completed_at=datetime.now(),
            status=status,
            attempt_count=attempt_count,
        )
        payload = msg.model_dump(mode="json")
        import json as _json
        self.controller.client.publish(topic, _json.dumps(payload))
        print(f"[order_completed] {order_id} status={status.value}")

    @staticmethod
    def _classify_recovery_reason(exc: BaseException) -> RecoveryReason:
        if isinstance(exc, CmdNoAckError):
            return RecoveryReason.CMD_NO_ACK
        if isinstance(exc, asyncio.TimeoutError):
            return RecoveryReason.JOB_TIMEOUT
        msg = str(exc)
        if "INCOMPLETE" in msg or "result=" in msg:
            return RecoveryReason.JOB_INCOMPLETE
        return RecoveryReason.JOB_TIMEOUT

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

        # Refresh the inventory index for exactly this step's input types, off
        # the event loop, before any binding/planning. This is the single AAS
        # poll per step (previously done synchronously inside every
        # _resolve_input_instance call); doing it here, scoped and threaded,
        # keeps AAS authoritative while letting a concurrent order run instead
        # of freezing on our network round-trips.
        await self._refresh_inventory_for_step(info)

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
            }, order_id=order_id)
            if resolved:
                info["ComponentReference"] = resolved
                # Refresh the InputIngredients view so subsequent uses (e.g.
                # _build_process_transformation for the BoP CMD) see the bound
                # reference rather than the stale "" we initially got.
                for ing in info.get("InputIngredients") or []:
                    if ing.get("name") == ingredient_name and not ing.get("ComponentReference"):
                        ing["ComponentReference"] = resolved
            else:
                # Bounded retry: a transient stockout should clear, but a
                # permanently un-stockable input must abort to recovery instead
                # of parking the step forever while it still holds any cargo
                # reserved by earlier steps (a head-of-line block on the line).
                # Shares _plan_retry_counts with the planning-retry branch — it's
                # cleared on planning success and on order teardown.
                key = (order_id, bop["step_id"])
                attempts = self._plan_retry_counts.get(key, 0) + 1
                self._plan_retry_counts[key] = attempts
                if attempts > PLAN_RETRY_BUDGET:
                    self._plan_retry_counts.pop(key, None)
                    raise RuntimeError(
                        f"step {bop['step_id']} found no inventory match for "
                        f"'{ingredient_name}' (type={info['ComponentTypeReference']}) "
                        f"after {PLAN_RETRY_BUDGET} retries"
                    )
                print(
                    f"[bop] no inventory match for '{ingredient_name}' "
                    f"(type={info['ComponentTypeReference']}) — pausing step "
                    f"({attempts}/{PLAN_RETRY_BUDGET})"
                )
                await asyncio.sleep(TICK_INTERVAL_S)
                return

        print(
            f"\n[bop] step {bop['step_id']}  "
            f"capability={info['CapabilityReference']}  "
            f"component={info['ComponentReference']}"
        )

        # 1) Match → pick target. Excluded set comes from the handler so a
        # restarted order avoids the resource that just failed it.
        excluded = handler.get_excluded_resources()
        print("[bop] running capability matcher…")
        candidates = self.matcher.match(info, excluded_resources=excluded)
        if not candidates:
            # Bounded retry, same rationale as the no-inventory-match branch: a
            # capability that never becomes matchable must abort to recovery
            # rather than park forever holding earlier steps' cargo.
            key = (order_id, bop["step_id"])
            attempts = self._plan_retry_counts.get(key, 0) + 1
            self._plan_retry_counts[key] = attempts
            if attempts > PLAN_RETRY_BUDGET:
                self._plan_retry_counts.pop(key, None)
                raise RuntimeError(
                    f"step {bop['step_id']} found no matching resource for "
                    f"capability {info['CapabilityReference']} after "
                    f"{PLAN_RETRY_BUDGET} retries"
                )
            print(
                f"[bop] no matching resource — pausing this step "
                f"({attempts}/{PLAN_RETRY_BUDGET})"
            )
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
            resource_iri=target_iri,
        )
        print(f"[bop] target  = {target}")

        # Stash per-step context so run_order's recovery branch knows
        # which resource and step to attribute a failure to.
        self._current_bop_target_iri = target_iri
        self._current_bop_target_topic = target.resource_id
        self._current_bop_step_info = info

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
        # Terminal step id of the last sub-plan that used each shuttle. When a
        # later input reuses a shuttle (degraded fleet), its legs are chained
        # after this id so the shuttle isn't asked to carry two parts at once.
        shuttle_tail: dict[tuple[str, str], str] = {}

        for input_index, ing in enumerate(inputs):
            try:
                sub_plan, sub_iris, sub_reservations = self._plan_arrival_for_input(
                    handler=handler,
                    ingredient=ing,
                    bop_step_id=bop["step_id"],
                    order_id=order_id,
                    target=target,
                    target_iri=target_iri,
                    material=material,
                    prior_reservations=reservations,
                    input_index=input_index,
                )
            except RuntimeError as exc:
                # Arrival planning failed. Usually a *transient* shortage of
                # free Transport actors (every shuttle is busy on another
                # order); rolling the step back to PENDING and pausing lets the
                # next tick re-attempt once a shuttle frees. But if it keeps
                # failing past PLAN_RETRY_BUDGET ticks the step is effectively
                # un-runnable (input lost, no capable transport, fleet too
                # degraded) — so we stop retrying and let the error propagate
                # to recovery, which aborts the order. That clears it out of
                # the dispatch queue and frees its reservations instead of
                # leaving it parked at N% forever.
                key = (order_id, bop["step_id"])
                attempts = self._plan_retry_counts.get(key, 0) + 1
                self._plan_retry_counts[key] = attempts
                if attempts > PLAN_RETRY_BUDGET:
                    self._plan_retry_counts.pop(key, None)
                    print(
                        f"[bop] cannot plan arrival for input '{ing.get('name')}': "
                        f"{exc} — gave up after {PLAN_RETRY_BUDGET} retries; aborting step"
                    )
                    raise
                print(
                    f"[bop] cannot plan arrival for input '{ing.get('name')}': "
                    f"{exc} — pausing step for retry ({attempts}/{PLAN_RETRY_BUDGET})"
                )
                handler.update_step(bop["step_id"], StepStates.PENDING)
                await asyncio.sleep(TICK_INTERVAL_S)
                return
            if sub_plan is None:
                # Already at target; nothing to transport.
                continue

            # If this sub-plan reuses a shuttle an earlier input already used,
            # serialize: a shuttle can't carry two parts simultaneously, so
            # this sub-plan's root steps wait for the prior sub-plan's tail.
            sub_shuttle = sub_reservations[0] if sub_reservations else None
            if sub_shuttle is not None and sub_shuttle in shuttle_tail:
                prev_tail = shuttle_tail[sub_shuttle]
                print(
                    f"[plan] serializing input '{ing.get('name')}' after "
                    f"{prev_tail} (shuttle {sub_shuttle[0]}/{sub_shuttle[1]} reused)"
                )
                for s in sub_plan.steps:
                    if s.depends_on is None:
                        s.depends_on = prev_tail
            if sub_shuttle is not None and sub_plan.steps:
                shuttle_tail[sub_shuttle] = self._plan_terminal_step_id(sub_plan.steps)

            combined_steps.extend(sub_plan.steps)
            combined_occupies.extend(sub_plan.occupies_through_bop)
            iri_by_topic.update(sub_iris)
            for res in sub_reservations:
                if res not in reservations:
                    reservations.append(res)
                    if res not in shuttles_used and res[0] != target.resource_id:
                        shuttles_used.append(res)

        # Planning succeeded for every input — clear this step's retry budget
        # so a later transient stall starts fresh rather than inheriting a
        # near-exhausted count.
        self._plan_retry_counts.pop((order_id, bop["step_id"]), None)

        plan = PreProcessPlan(
            bop_step_id=bop["step_id"],
            order_id=order_id,
            target=target,
            shuttle=None,
            steps=combined_steps,
            occupies_through_bop=combined_occupies,
        )

        # Reserve all involved actors for this order while the plan runs.
        #
        # try_commit is all-or-nothing: on a partial conflict it reserves
        # *nothing*. So a shuttle this plan picked (free at plan time) can be
        # taken by another order before we manage to commit — typically because
        # we're also waiting on a scarce target (an assembler) that's still
        # busy. Retrying the SAME reservation list would then pin us to the now
        # stolen shuttle forever, even while other shuttles sit idle. If we're
        # holding a resource another order needs (an assembler with cargo), that
        # pin is a circular-wait deadlock (observed: ORD-7 holds the assembler
        # and waits on a shuttle held by ORD-9, which waits on the assembler).
        #
        # Fix: on a blocked commit, roll the step back to PENDING and return so
        # the next tick re-runs arrival planning and re-picks a currently-free
        # shuttle — the same self-healing the arrival-planning shortage path
        # already relies on. Bound it with PLAN_RETRY_BUDGET so a step that is
        # *genuinely* stuck (its only capable target is permanently held)
        # eventually raises to recovery and aborts the order instead of wedging
        # the line forever.
        blocker = self.occupancy.try_commit(order_id, reservations)
        if blocker is not None:
            key = (order_id, bop["step_id"])
            attempts = self._commit_retry_counts.get(key, 0) + 1
            self._commit_retry_counts[key] = attempts
            owner = self.occupancy.owner_of(*blocker)
            if attempts > PLAN_RETRY_BUDGET:
                self._commit_retry_counts.pop(key, None)
                raise RuntimeError(
                    f"step {bop['step_id']} could not reserve "
                    f"{blocker[0]}/{blocker[1]} (held by order {owner}) after "
                    f"{PLAN_RETRY_BUDGET} retries"
                )
            print(
                f"[bop] step {bop['step_id']} waiting on {blocker[0]}/{blocker[1]} "
                f"(held by order {owner}) — re-planning "
                f"({attempts}/{PLAN_RETRY_BUDGET})"
            )
            handler.update_step(bop["step_id"], StepStates.PENDING)
            await asyncio.sleep(TICK_INTERVAL_S)
            return

        # Commit succeeded — clear this step's commit-retry budget so a later
        # stall starts fresh rather than inheriting a near-exhausted count.
        self._commit_retry_counts.pop((order_id, bop["step_id"]), None)

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

    @staticmethod
    def _plan_terminal_step_id(steps: list[PreProcessStep]) -> str:
        """Return the tail of a sub-plan's dependency chain — the step on
        which nothing else in `steps` depends. Used to serialize a reused
        shuttle's next sub-plan after this one finishes.
        """
        referenced = {s.depends_on for s in steps if s.depends_on is not None}
        tails = [s.step_id for s in steps if s.step_id not in referenced]
        # A well-formed linear sub-plan has exactly one tail; if more than one
        # surfaces, the last-appended step is the true end of the chain.
        return tails[-1] if tails else steps[-1].step_id

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
        prior_reservations: list[tuple[str, str]] | None = None,
        input_index: int = 0,
    ) -> tuple[PreProcessPlan | None, dict[str, str], list[tuple[str, str]]]:
        """Build a PreProcessPlan that gets one input ingredient to `target`.

        Returns (plan, iri_by_topic_additions, reservations). `plan` is None
        when the input is already at the target (no transport needed).

        `input_index` namespaces the generated pre-process step ids so that
        two inputs of the SAME BoP step (e.g. an Assemble that consumes two
        parts, each fetched via its own transport leg) don't produce colliding
        step ids — and therefore colliding job ids. Without it, both sub-plans
        would emit `<step>-pp1-transport`, breaking JobResult correlation and
        the DAG executor's steps_by_id map.
        """
        ingredient_name = ingredient.get("name")
        # Distinct step-id prefix per input of this BoP step.
        plan_step_id = f"{bop_step_id}-in{input_index}"
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
        component_ref = self._resolve_input_instance(handler, ingredient, order_id=order_id)
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
                bop_step_id=plan_step_id,
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
                    resource_iri=holder_iri,
                )
                shuttle, shuttle_iri = self._pick_shuttle(
                    component_ref,
                    material=material,
                    _target_iri=target_iri,
                    _storage_iri=holder_iri,
                    excluded=prior_reservations,
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
                    bop_step_id=plan_step_id,
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
            component_ref, ingredient_name=ingredient_name, handler=handler,
        )
        shuttle, shuttle_iri = self._pick_shuttle(
            component_ref,
            material=material,
            _target_iri=target_iri,
            _storage_iri=storage_iri,
            excluded=prior_reservations,
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
            bop_step_id=plan_step_id,
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

        process_transformation = self._build_process_transformation(handler, info, order_id=order_id)
        if process_transformation is None:
            print(f"[bop] step {bop['step_id']} cannot build process_transformation "
                  "(unresolved inputs) — pausing")
            return

        bop_job_id = f"{order_id}-{bop['step_id']}"
        handler.update_step(bop["step_id"], StepStates.IN_PROGRESS)
        start_time = datetime.now()
        print(f"[bop] step {bop['step_id']} -> IN_PROGRESS")

        # AAS process-tracking writes run in a worker thread so a concurrent
        # order isn't frozen on our BaSyx round-trips. Per-order ordering is
        # preserved — we still await our own writes before continuing.
        tracking = await asyncio.to_thread(
            self._start_process_tracking, bop, info, handler, target, chosen, start_time
        )
        bop_rec_id = await asyncio.to_thread(
            self._write_bop_step_started, handler, bop, target, start_time
        )

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
            # AAS writes off the loop (BOM, slot-clear, tracking) so a peer
            # order keeps running while we talk to BaSyx.
            await asyncio.to_thread(self._update_output_bom_with_inputs, handler, info)
            # Empty the Inventory slots of any feeder parts this step consumed.
            # Storage-sourced inputs were already emptied at Retrieve (their
            # reservation is gone, so this no-ops on them); transported-in
            # sub-assemblies were never reserved feeder instances. Only a part
            # still reserved in a resource's own feeder (e.g. a Fuse the
            # assembler picked from its magazine) is cleared here — closing the
            # gap that let those parts be re-selected by later orders.
            await asyncio.to_thread(
                self._consume_inputs_from_inventory,
                result.process_transformation or process_transformation, order_id,
            )
            handler.update_step(bop["step_id"], StepStates.COMPLETED)
            print(f"[ok]  BoP step {bop['step_id']} -> COMPLETED")
            await asyncio.to_thread(
                self._complete_process_tracking,
                bop, info, handler, tracking, target, chosen, start_time, result,
            )
            await asyncio.to_thread(
                self._write_bop_step_completed, handler, bop_rec_id, result
            )
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
            dep = f"  after {s.depends_on}" if s.depends_on else ""
            print(
                f"  {s.step_id:<32s} skill={s.skill:<10s} "
                f"on={s.resource_id}/{s.actor_name}{dep}"
            )
        if plan.occupies_through_bop:
            print(f"  shuttle stays occupied through BoP: {plan.occupies_through_bop}")
        print()

        # DAG-parallel execution. Steps with no dependency start immediately
        # and concurrently; each subsequent step starts the moment its parent
        # completes. Sub-plans for different inputs of an Assemble step have
        # disjoint dependency chains, so their Transport/Retrieve/Handoff
        # sequences run in parallel across the line.
        steps_by_id: dict[str, PreProcessStep] = {s.step_id: s for s in plan.steps}
        completed: set[str] = set()
        pending = list(plan.steps)
        running: dict[asyncio.Task, str] = {}

        def _ready_now() -> list[PreProcessStep]:
            ready = []
            for s in pending:
                if s.depends_on is None or s.depends_on in completed:
                    ready.append(s)
            return ready

        try:
            while pending or running:
                # Launch every step whose dependency is satisfied.
                for s in _ready_now():
                    pending.remove(s)
                    task = asyncio.create_task(
                        self._execute_step(s, plan.order_id, iri_by_topic)
                    )
                    running[task] = s.step_id

                if not running:
                    # No tasks running and nothing became ready — the DAG
                    # has an unresolvable dependency. Surface it.
                    stuck = [s.step_id for s in pending]
                    raise RuntimeError(
                        f"Pre-process plan stuck: no step is ready to run "
                        f"(remaining: {stuck})"
                    )

                done, _ = await asyncio.wait(
                    running.keys(), return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    step_id = running.pop(task)
                    if task.exception() is not None:
                        # One step failed — cancel the rest and propagate.
                        for other in running:
                            other.cancel()
                        if running:
                            await asyncio.gather(*running, return_exceptions=True)
                        raise task.exception()
                    completed.add(step_id)
        except BaseException:
            # Make sure no orphan tasks survive on the unwind path.
            for task in running:
                task.cancel()
            if running:
                await asyncio.gather(*running, return_exceptions=True)
            raise

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

        pre_rec_id: str | None = None
        if step.component_reference:
            # AAS write off the loop so a concurrent order isn't blocked.
            pre_rec_id = await asyncio.to_thread(
                aas_writer.write_process_started,
                aas_server_base=self.aas_server_base,
                component_shell_iri=step.component_reference,
                process_type=step.skill,
                performed_by=step.resource_id,
                start_time=step.timestamps[StepStates.IN_PROGRESS].isoformat(),
            )

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
            if pre_rec_id and step.component_reference:
                await asyncio.to_thread(
                    aas_writer.write_process_completed,
                    aas_server_base=self.aas_server_base,
                    component_shell_iri=step.component_reference,
                    record_id_short=pre_rec_id,
                    completion_time=step.timestamps[StepStates.COMPLETED].isoformat(),
                )
            # Retrieve traceability clears the storage slot on BaSyx (GET/PUT/GET)
            # — offload so the slot-clear doesn't freeze a peer order.
            await asyncio.to_thread(
                self._capture_retrieve_traceability, step, result, order_id
            )
            # Apply the step's declared cargo side-effects to the ledger.
            # See PreProcessStep.cargo_transfers for the semantics:
            # Retrieve sets cargo on storage, Handoff moves cargo between
            # actors, Store clears cargo, Transport doesn't change it.
            if step.cargo_transfers:
                self.occupancy.apply_cargo_transfers(step.cargo_transfers)
                # After cargo moves, any actor that just became cargo-free
                # and is still reserved for this order can be released —
                # we won't be coming back to it for this order. release_one
                # is a no-op if cargo is still present, so this is safe.
                for resource_id, actor_name, new_cargo in step.cargo_transfers:
                    if new_cargo is None:
                        self.occupancy.release_one(resource_id, actor_name, order_id)
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
        # R1 — config-reload race guard. A live reload between this step's
        # planning pass and now may have dropped the chosen resource from the
        # line (idle resources are removed immediately). Firing a CMD at a
        # resource the controller no longer manages would hang on no-ACK; fail
        # the step instead so recovery re-plans onto the remaining resources
        # (the removed shell is gone from the registry, so it won't be re-picked).
        if target_iri not in self.rm.resource_shell_ids:
            raise CmdNoAckError(
                f"target {resource_topic} ({target_iri}) was removed from the "
                "line configuration mid-plan; re-planning step onto remaining resources"
            )

        idle = await self._wait_for_idle(resource_topic, actor_name, timeout=IDLE_WAIT_S)
        if not idle:
            # A station that started AFTER the order's initial state-seed never
            # received an InfoRequest, so it never reported IDLE — even though
            # it may be up, subscribed, and ready. Send a targeted probe to
            # prompt it and re-wait once before committing the CMD. This is the
            # late-subscribing-station case that otherwise fires a CMD into a
            # resource that hasn't confirmed reachability, producing a false
            # CMD_NO_ACK (and, for a sole-capable resource, an aborted order
            # with stranded cargo).
            print(
                f"[gate] never saw IDLE for {resource_topic}/{actor_name}; "
                "probing and re-waiting before CMD"
            )
            self.controller.request_data(MS.StateMessage, target_iri)
            idle = await self._wait_for_idle(
                resource_topic, actor_name, timeout=IDLE_WAIT_S
            )
        if not idle:
            print(
                f"[warn] {resource_topic}/{actor_name} still not IDLE after probe; "
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
        # Drop any stale JobResult for this job_id before issuing the CMD.
        # Job ids are reused across retries and across reruns of the same
        # order, and the shared job_result dict is never cleared — without
        # this, wait_for() below would instantly match a leftover result
        # from a previous attempt/run and fail (or falsely pass) the step
        # before this CMD has actually executed.
        self.jobs.forget(job_id)
        # send_command_with_ack assigns a seq_no, publishes, and waits for
        # the station ACK. Raises CmdNoAckError after retries are exhausted;
        # we let that propagate — the existing exception path treats it the
        # same as a JobResult timeout and fails the step.
        await self.controller.send_command_with_ack(target_iri, cmd)

        return await self.jobs.wait_for(job_id, timeout=timeout)

    # ── Transformation: ingredient names → instance IRIs ────────────────────

    async def _refresh_inventory_for_step(self, info: dict) -> None:
        """Scoped, off-the-loop inventory refresh for one BoP step's input types.

        Gathers the type references this step needs (the main ingredient plus
        every InputIngredient) and re-polls only the inventories that can hold
        those types, each via `asyncio.to_thread` so the event loop is free for
        other orders while we wait on the AAS. The shared index is mutated under
        `_inventory_lock` so two orders never rebuild it concurrently.

        AAS stays the single source of truth — this is the same per-step poll,
        just narrowed by type and moved off the loop thread.
        """
        if self.locations is None:
            return
        type_refs: set[str] = set()
        main_type = info.get("ComponentTypeReference")
        if main_type:
            type_refs.add(main_type)
        for ing in info.get("InputIngredients") or []:
            t = ing.get("ComponentTypeReference")
            if t:
                type_refs.add(t)
        if not type_refs:
            return
        async with self._inventory_lock:
            if not self.product_matcher.has_inventory_registry():
                # Registry not built (e.g. tests) — full poll preserves the old
                # "always fresh from AAS" behaviour, still off the loop.
                await asyncio.to_thread(
                    self.product_matcher.poll_inventory_from_aas, self.locations
                )
                return
            for type_ref in type_refs:
                await asyncio.to_thread(
                    self.product_matcher.refresh_for_type, type_ref
                )

    def _has_available_instance(self, ingredient: dict) -> bool:
        """True if a free (unreserved) instance of this ingredient's type can be
        resolved from inventory right now.

        Used to decide whether a bound-but-invisible instance is genuinely
        replaceable (a consumed raw storage part with other stock of its type) or
        an in-flight sub-assembly that simply isn't in storage (no replacement —
        keep the binding). Mirrors the candidate filtering in
        `_resolve_input_instance` so the two agree on what "available" means.
        """
        type_ref = ingredient.get("ComponentTypeReference")
        if not type_ref:
            return False
        try:
            matches = self.product_matcher.find_matching_components(
                component_type_reference=type_ref,
                order_properties=ingredient.get("Properties") or {},
            )
        except Exception:
            return False
        return any(
            self._reserved_instances.get(m.component_id) is None for m in matches
        )

    def _resolve_input_instance(
        self,
        handler: WorkOrderHandler,
        ingredient: dict,
        order_id: str | None = None,
    ) -> str | None:
        """Resolve one InputIngredients entry to its concrete instance IRI.

        - If the ingredient already has a ComponentReference, use it (and
          re-claim the reservation for this order — it's a no-op if we
          already own it).
        - Otherwise ask the ProductMatcher with the ingredient's properties
          and pick the first candidate that isn't reserved by another order.
          On a hit, persist the choice and reserve it.

        Returns None if no free instance can be resolved.

        Assumes the inventory index is already fresh for this ingredient's type:
        `_execute_bop_step` calls `_refresh_inventory_for_step` (a scoped,
        off-the-event-loop AAS poll) before any resolution/planning, so this
        method matches against the current index without doing its own blocking
        AAS round-trip on the loop thread.
        """
        existing = ingredient.get("ComponentReference") or ""
        if existing:
            # Validate the bound instance still physically exists before reusing
            # it. A Retrieve on a PRIOR (failed) attempt empties the storage slot
            # (_consume_instance clears ComponentShellReference), so an instance
            # bound on attempt 1 may be gone by attempt 2. Reusing it makes every
            # retry fail at the retrieve step with INCOMPLETE, because no resource
            # holds it and the storage fallback picks the wrong one. Accept the
            # binding only if the part is still held by an actor/shuttle or is
            # present in some inventory; otherwise drop it and re-resolve by type.
            still_held = self.occupancy.find_holder(existing) is not None
            still_stocked = (
                self.product_matcher.find_component_location(existing) is not None
            )
            # Only abandon the binding if a fresh same-type instance can actually
            # be resolved. This distinguishes the two reasons a bound instance can
            # be "invisible":
            #   (a) a raw storage part consumed by a failed earlier attempt — its
            #       type still has other stock, so we switch to a fresh one;
            #   (b) an in-flight SUB-ASSEMBLY the order is carrying that the
            #       single-cargo-per-actor ledger lost track of — a multi-input
            #       assembly target (e.g. PhoneAssembler holding BottomCoverPCBFuse
            #       *and* TopCover) overwrites the first cargo with the second, so
            #       find_holder misses it. Sub-assemblies are never in storage, so
            #       there is no replacement — keep the binding rather than deadlock.
            if still_held or still_stocked or not self._has_available_instance(ingredient):
                if order_id is not None:
                    self._reserve_instance(existing, order_id)
                return existing
            print(
                f"[reserve] '{ingredient.get('name')}': bound instance {existing} "
                f"was consumed by a failed attempt — re-resolving a fresh instance by type"
            )
            if order_id is not None:
                self._release_instance_reservation(existing, order_id)
            ingredient["ComponentReference"] = ""
            handler.update_component_reference(ingredient["name"], "")

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

        # Skip instances already reserved — by any order (concurrent) or by
        # this order for a different ingredient (same-order double-booking).
        instance = None
        for m in matches:
            entry = self._reserved_instances.get(m.component_id)
            if entry is not None:
                print(
                    f"[reserve] '{ingredient.get('name')}': skipping {m.component_id} "
                    f"(already reserved by order {entry[0]})"
                )
                continue
            if order_id is None or self._reserve_instance(
                m.component_id, order_id,
                m.resource_shell_id, m.inventory_name, m.slot_id,
            ):
                instance = m.component_id
                ingredient["ComponentReference"] = instance
                if order_id is not None:
                    self._patch_slot_reserved(m.resource_shell_id, m.inventory_name, m.slot_id, True)
                break
        if instance is None:
            print(
                f"[trans] all {len(matches)} match(es) for '{ingredient.get('name')}' "
                f"are reserved — pausing"
            )
            return None

        handler.update_component_reference(ingredient["name"], instance)
        print(f"[trans] resolved {ingredient.get('name')} -> {instance}")
        return instance

    def _build_process_transformation(
        self,
        handler: WorkOrderHandler,
        info: dict,
        order_id: str | None = None,
    ) -> dict | None:
        """Build the {InputTypes: [...], OutputTypes: [...]} CMD payload.

        Inputs and outputs are full instance IRIs (or None for legs that
        don't carry a component, per MessageStructure.CommandMessage docs).
        Returns None if any required input cannot be resolved — the caller
        should treat that as "no candidate" and pause the step.
        """
        input_iris: list[str | None] = []
        for ing in info.get("InputIngredients") or []:
            iri = self._resolve_input_instance(handler, ing, order_id=order_id)
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
        handler: WorkOrderHandler | None = None,
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
            # Fast path: if this instance is already reserved we already know
            # which resource holds it — skip the inventory index entirely.
            # (Reserved slots are excluded from the index, so find_component_location
            # would return None and the fallback would misfire.)
            entry = self._reserved_instances.get(component_ref)
            if entry is not None and entry[1]:
                storage_iri = entry[1]
                picked_instance = component_ref

        if storage_iri is None and component_ref:
            # Preferred path: component_ref is a concrete instance IRI
            # (already resolved by _resolve_input_instance). Look it up in
            # the inventory index directly.
            location = self.product_matcher.find_component_location(component_ref)
            if location is not None:
                storage_iri = location.resource_shell_id
                picked_instance = location.component_id

        if storage_iri is None and component_ref:
            # Fallback: the concrete instance isn't locatable (e.g. consumed by a
            # failed attempt, or the caller never pre-resolved). Re-resolve by the
            # ingredient's declared TYPE — NOT by component_ref, which may be a
            # full instance IRI. find_by_component_type keys on the type path, so
            # passing an instance IRI there can never match and silently misfires
            # into "first Retrieve resource".
            # Prefer the handler's workorder (per-order, safe across
             # concurrent orders); fall back to self.workorder for legacy
             # single-order use.
            workorder = (handler.workorder if handler is not None else None) or self.workorder
            ingredient = (
                (workorder or {}).get("Ingredients", {}).get(ingredient_name, {})
                if ingredient_name
                else {}
            )
            type_ref = ingredient.get("ComponentTypeReference") or component_ref
            props = (
                (workorder or {})
                .get("Properties", {})
                .get(ingredient_name, {})
                if ingredient_name
                else {}
            )
            try:
                if props:
                    matches = self.product_matcher.find_matching_components(
                        component_type_reference=type_ref,
                        order_properties=props,
                    )
                else:
                    matches = (
                        self.product_matcher.inventory_indexer
                        .find_by_component_type(type_ref)
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
            resource_iri=storage_iri,
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
                resource_iri=shuttle_iri,
            )
            return endpoint, shuttle_iri
        return None

    def _pick_shuttle(
        self,
        component_ref: str,
        material: str | None = None,
        _target_iri: str | None = None,
        _storage_iri: str | None = None,
        excluded: list[tuple[str, str]] | None = None,
    ) -> tuple[ResourceEndpoint, str]:
        """Pick an available shuttle, spreading load across actors.

        Filters applied, in order:
        - The transport resource's Transport capability must list this
          component (or its type prefix) in its `SupportedComponents`, AND
          the material must be in `AllowedMaterials`. Either list empty
          means "no restriction" — same convention as CapabilityMatcher.
        - The actor must be `available` per OccupancyManager: not reserved
          for any order AND not currently carrying cargo.
        - The (topic, actor) pair must not be in `excluded` — used by the
          planner to thread already-picked shuttles from earlier sub-plans
          of the same BoP step so they aren't grabbed twice.

        Among the actors that pass all filters, a class-level round-robin
        cursor rotates the starting index each call so consecutive picks
        with the same free pool alternate between actors instead of always
        returning the first one. This is what spreads load across Shuttle1
        and Shuttle2 even when both are idle.

        The two IRI args are unused today — they'll feed the future
        connection-point reachability filter (walking LineConfiguration's
        graph to verify the shuttle reaches both endpoints).
        """
        offering = self.rm.find_skill_offering("Transport")
        if not offering:
            raise RuntimeError("No resource offers a Transport skill")

        excluded_set: set[tuple[str, str]] = set(excluded or [])

        # If every distinct shuttle is taken by an earlier input of the SAME
        # step (i.e. only `excluded` shuttles remain available), we fall back
        # to reusing one of them. A single shuttle can serve several inputs as
        # long as their transport legs run sequentially — the caller chains
        # the reusing sub-plan after the prior one. This is what keeps a line
        # whose fleet is degraded to one shuttle (e.g. the other is STUCK)
        # from deadlocking on a multi-input step; it just runs slower.
        reuse: tuple[str, str, str, int] | None = None  # (topic, actor, iri, next_cursor)

        for shuttle_iri, topic, actors in offering:
            if not self._transport_supports(shuttle_iri, component_ref, material):
                print(
                    f"[plan] shuttle {topic} skipped: Transport capability "
                    f"doesn't support component={component_ref} material={material}"
                )
                continue

            # Rotate the starting index so consecutive picks don't all land
            # on actors[0]. Modulo over the actor count keeps the cursor
            # bounded; advancing once per call gives a simple round-robin.
            n = len(actors)
            if n == 0:
                continue
            start = self._shuttle_pick_cursor % n

            for offset in range(n):
                actor = actors[(start + offset) % n]
                # A shuttle being retired is excluded from ALL new picks (not
                # even a reuse fallback) — it must run down to idle+empty and
                # leave, never take on fresh cargo. It stays routable for the
                # order already holding it via the endpoint baked into that
                # order's plan. See ResourceManager._draining_actors.
                if self.rm.is_actor_draining(topic, actor):
                    continue
                if not self.occupancy.is_available(topic, actor):
                    continue
                if (topic, actor) in excluded_set:
                    # Already claimed for an earlier input of this step.
                    # Remember the first such shuttle as a reuse fallback,
                    # but keep looking for a genuinely free one first.
                    if reuse is None:
                        reuse = (topic, actor, shuttle_iri, (start + offset + 1) % n)
                    continue
                self._shuttle_pick_cursor = (start + offset + 1) % n
                endpoint = ResourceEndpoint(
                    resource_id=topic,
                    actor_name=actor,
                    has_handoff=self.rm.has_handoff(shuttle_iri),
                    resource_iri=shuttle_iri,
                )
                return endpoint, shuttle_iri

        if reuse is not None:
            topic, actor, shuttle_iri, next_cursor = reuse
            self._shuttle_pick_cursor = next_cursor
            print(
                f"[plan] no spare shuttle free; reusing {topic}/{actor} "
                "sequentially for another input of this step"
            )
            endpoint = ResourceEndpoint(
                resource_id=topic,
                actor_name=actor,
                has_handoff=self.rm.has_handoff(shuttle_iri),
                resource_iri=shuttle_iri,
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
        """If the step was a Retrieve, record the picked instance and free
        its slot reservation.

        Historically this read the IRI back from
        `result.output_parameters["ComponentReference"]`, but the scheduler
        now pre-resolves the instance via _resolve_input_instance before
        sending the CMD — `step.component_reference` is already the IRI
        the storage station retrieved. Reading the JobResult is redundant
        AND breaks against the generic runner, which returns
        `output_parameters` as a pydantic CollectionElement (not a dict).
        """
        if step.skill != "Retrieve":
            return
        instance = step.component_reference
        if not instance:
            return
        self._traceability.setdefault(order_id, {})[instance] = instance
        print(f"[trace] {order_id}: Retrieve -> {instance}")
        # The part has physically left storage. Empty its slot on the AAS
        # (so the matcher stops offering it) and release the reservation once
        # the slot is confirmed empty.
        self._consume_instance(instance, order_id)

    # ── Finalization (post-process + AAS writeback + status) ────────────────

    def _is_order_complete(self, handler: WorkOrderHandler) -> bool:
        return all(
            s["state"] == StepStates.COMPLETED
            for s in handler.execution_plan["steps"]
        )

    async def _finalize_order(self, handler: WorkOrderHandler) -> None:
        order_id = handler.workorder["OrderId"]
        print(f"\n[finalize] order {order_id} — all BoP steps complete")

        await self._run_post_process(handler)
        await asyncio.to_thread(self._write_traceability, order_id, handler)
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
            resource_iri=holder_iri,
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
            resource_iri=store_iri,
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

        # Wait for the shuttle to become free instead of raising if a
        # concurrent order currently owns it. Mirrors the wait-loop in
        # _execute_bop_step so post-process doesn't kill the order on
        # cross-order contention — but bounded: the shuttle was picked once
        # (above) and an unbounded wait re-creates the very pin/deadlock the
        # main path was fixed for (finished product wedged on the holder while
        # we wait forever on a stolen shuttle). On exhaustion give up storing
        # and leave the part on the holder, matching the "no Store"/"no shuttle"
        # early-returns above; the order is still marked COMPLETE by the caller.
        post_reservation = [(shuttle.resource_id, shuttle.actor_name)]
        committed = False
        for _ in range(PLAN_RETRY_BUDGET):
            blocker = self.occupancy.try_commit(order_id, post_reservation)
            if blocker is None:
                committed = True
                break
            print(
                f"[finalize] post-process waiting on {blocker[0]}/{blocker[1]} "
                f"(held by order {self.occupancy.owner_of(*blocker)})"
            )
            await asyncio.sleep(TICK_INTERVAL_S)
        if not committed:
            print(
                f"[finalize] post-process could not reserve {shuttle.resource_id}/"
                f"{shuttle.actor_name} after {PLAN_RETRY_BUDGET} retries — "
                f"leaving part on holder"
            )
            return
        try:
            await self._print_and_execute_plan(plan, iri_by_topic, "post-process")
        finally:
            # Release only what post_process committed — not the whole order.
            # run_order's outer finally still calls occupancy.release(order_id)
            # for any leftover reservations.
            for resource_id, actor_name in post_reservation:
                self.occupancy.release_one(resource_id, actor_name, order_id)

    def _find_cargo_holder_for_order(
        self, order_id: str
    ) -> tuple[str, str] | None:
        """Pick an actor that's currently carrying cargo AND is reserved by
        this order. Returns None if nothing on the line belongs to this order.

        Strictly per-order: never fall back to "any cargo on the line" — in
        a multi-order run that would let one order's post-process pick up
        another order's in-flight part.
        """
        for resource_id, actor, _cargo in self.occupancy.all_cargo():
            if self.occupancy.owner_of(resource_id, actor) == order_id:
                return (resource_id, actor)
        return None

    def _is_transport_actor(self, shell_iri: str) -> bool:
        return "Transport" in self.rm.get_resource_skills(shell_iri)

    def _final_bop_step(self, handler: WorkOrderHandler) -> dict | None:
        """The step with the highest precedence (deepest in the BoP)."""
        steps = handler.execution_plan["steps"]
        if not steps:
            return None
        return max(steps, key=lambda s: s["precedence"])

    def _start_process_tracking(
        self,
        bop: dict,
        info: dict,
        handler: WorkOrderHandler,
        target: ResourceEndpoint,
        chosen: dict,
        start_time: datetime,
    ) -> dict[str, tuple[str, str]]:
        """Write InProgress ProcessRecords on all input shells and any pre-known output shells.

        Called just before _send_and_wait so the record exists on BaSyx from the moment
        the CMD is sent. Uses the handler's live Ingredients dict because
        _resolve_input_instance() wrote resolved IRIs there, not back into info.

        Returns:
            Mapping of ingredient_name -> (shell_iri, record_id_short) for every record
            successfully created. Passed to _complete_process_tracking() to PATCH them.
        """
        process_type = (bop.get("required_capability") or "Unknown").rsplit("/", 1)[-1]
        capability_ref = info.get("RequiredCapabilitySubmodelIRI") or chosen.get("capability_submodel_reference")
        skill_ref = f"{chosen['resource_id']}/Skills" if chosen.get("resource_id") else None
        skill_name = chosen.get("skill_name")
        performed_by = target.resource_id
        start_iso = start_time.isoformat()
        live = (handler.workorder or {}).get("Ingredients", {})

        tracking: dict[str, tuple[str, str]] = {}
        seen_iris: set[str] = set()

        all_ingredients = list(info.get("InputIngredients") or []) + list(info.get("OutputIngredients") or [])
        for ing in all_ingredients:
            name = ing.get("name", "")
            shell_iri = live.get(name, {}).get("ComponentReference") or ""
            if not shell_iri or shell_iri in seen_iris:
                continue
            seen_iris.add(shell_iri)
            rec_id = aas_writer.write_process_started(
                aas_server_base=self.aas_server_base,
                component_shell_iri=shell_iri,
                process_type=process_type,
                performed_by=performed_by,
                capability_reference_iri=capability_ref,
                skill_reference_iri=skill_ref,
                skill_name=skill_name,
                start_time=start_iso,
            )
            if rec_id:
                tracking[name] = (shell_iri, rec_id)

        return tracking

    def _complete_process_tracking(
        self,
        bop: dict,
        info: dict,
        handler: WorkOrderHandler,
        tracking: dict[str, tuple[str, str]],
        target: ResourceEndpoint,
        chosen: dict,
        start_time: datetime,
        result: MS.JobResultMessage,
    ) -> None:
        """Patch InProgress records to Completed, and write full records for new output shells.

        Called after _apply_output_traceability() so newly-created output shell IRIs
        are already in handler.workorder["Ingredients"].
        """
        completion_iso = result.timestamp.isoformat() if result.timestamp else datetime.now().isoformat()
        process_type = (bop.get("required_capability") or "Unknown").rsplit("/", 1)[-1]
        capability_ref = info.get("RequiredCapabilitySubmodelIRI") or chosen.get("capability_submodel_reference")
        skill_ref = f"{chosen['resource_id']}/Skills" if chosen.get("resource_id") else None
        skill_name = chosen.get("skill_name")
        start_iso = start_time.isoformat()
        live = (handler.workorder or {}).get("Ingredients", {})

        # Patch every record that was created at step start.
        for name, (shell_iri, rec_id) in tracking.items():
            aas_writer.write_process_completed(
                aas_server_base=self.aas_server_base,
                component_shell_iri=shell_iri,
                record_id_short=rec_id,
                completion_time=completion_iso,
            )

        # Output shells whose IRI was only resolved after the result came back
        # (newly assembled sub-assemblies): write a full record now.
        tracked_iris = {iri for _, (iri, _) in tracking.items()}
        for ing in info.get("OutputIngredients") or []:
            name = ing.get("name", "")
            shell_iri = live.get(name, {}).get("ComponentReference") or ""
            if not shell_iri or shell_iri in tracked_iris:
                continue  # already handled above
            aas_writer.write_process_record(
                aas_server_base=self.aas_server_base,
                component_shell_iri=shell_iri,
                process_type=process_type,
                performed_by=target.resource_id,
                capability_reference_iri=capability_ref,
                skill_reference_iri=skill_ref,
                skill_name=skill_name,
                start_time=start_iso,
                completion_time=completion_iso,
            )

    def _update_output_bom_with_inputs(
        self,
        handler: WorkOrderHandler,
        info: dict,
    ) -> None:
        """Write each input ingredient's instance IRI into the output shell's BOM.

        Called after _build_process_transformation succeeds and before _send_and_wait.
        All input IRIs are resolved by this point. Output shell IRIs are pre-assigned
        in the WorkOrder so we don't need to wait for the JobResult.
        Best-effort — never raises.
        """
        live = (handler.workorder or {}).get("Ingredients", {})

        for out_ing in info.get("OutputIngredients") or []:
            out_name = out_ing.get("name", "")
            out_shell_iri = live.get(out_name, {}).get("ComponentReference") or ""
            if not out_shell_iri:
                continue

            for in_ing in info.get("InputIngredients") or []:
                in_name = in_ing.get("name", "")
                in_instance_iri = live.get(in_name, {}).get("ComponentReference") or ""
                in_type_iri = live.get(in_name, {}).get("ComponentTypeReference") or ""
                print(f"[bom] input {in_name}: instance={in_instance_iri} type={in_type_iri}")
                if not in_instance_iri or not in_type_iri:
                    print(f"[bom] skipping {in_name} — missing instance or type IRI")
                    continue

                bom_entry = aas_writer.get_bom_entry_for_type(
                    self.aas_server_base, out_shell_iri, in_type_iri
                )
                if not bom_entry:
                    print(f"[bom] no BOM entry found for type {in_type_iri} in {out_shell_iri}")
                    continue

                aas_writer.write_bom_component_instance_ref(
                    self.aas_server_base, out_shell_iri, bom_entry, in_instance_iri
                )

    def _product_shell_iri(self, handler: WorkOrderHandler) -> str:
        product_ref = handler.workorder.get("ProductReference", "") or ""
        if not product_ref:
            return ""
        return product_ref if product_ref.startswith("http") else f"https://aausmartlab.org/Shells/Assembly/{product_ref}"

    def _write_bop_step_started(
        self,
        handler: WorkOrderHandler,
        bop: dict,
        target: ResourceEndpoint,
        start_time: datetime,
    ) -> str | None:
        shell_iri = self._product_shell_iri(handler)
        if not shell_iri:
            return None
        return aas_writer.write_bop_step_started(
            aas_server_base=self.aas_server_base,
            product_shell_iri=shell_iri,
            step_id_short=bop["step_id"],
            executed_by=target.resource_id,
            start_time=start_time.isoformat(),
        )

    def _write_bop_step_completed(
        self,
        handler: WorkOrderHandler,
        rec_id: str | None,
        result: MS.JobResultMessage,
    ) -> None:
        if not rec_id:
            return
        shell_iri = self._product_shell_iri(handler)
        if not shell_iri:
            return
        completion_iso = result.timestamp.isoformat() if result.timestamp else datetime.now().isoformat()
        aas_writer.write_bop_step_completed(
            aas_server_base=self.aas_server_base,
            product_shell_iri=shell_iri,
            record_id_short=rec_id,
            completion_time=completion_iso,
        )

    def _write_traceability(self, order_id: str, handler: WorkOrderHandler) -> None:
        used = self._traceability.get(order_id, {})
        if not used:
            return
        shell_iri = self._product_shell_iri(handler)
        if shell_iri:
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
