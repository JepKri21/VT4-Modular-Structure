"""Pre-process planner.

Given one BoP step that the scheduler is ready to execute, this module
expands it into the ordered list of pre-process steps required to deliver
the part to the chosen resource — transport, retrieve, and handoff steps.

Inputs are simple value objects (see ResourceEndpoint below). The planner
owns the handoff rule logic; it does not touch MQTT or the AAS server.

Handoff rules (between a *sender* who currently holds the part and a
*receiver* who needs it next):

    sender has Handoff | receiver has Handoff | inserted steps
    ───────────────────┼──────────────────────┼─────────────────────────────────
    no                 | no                   | none — both occupied through BoP
    no                 | yes                  | one Handoff on receiver
    yes                | no                   | one Handoff on sender
    yes                | yes                  | Handoff on sender, then receiver

The (no, no) case for the shuttle→target handoff produces an empty handoff
section but populates `PreProcessPlan.occupies_through_bop` so the scheduler
keeps the shuttle marked occupied while the BoP step runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from workorder_handler import StepStates

if TYPE_CHECKING:
    from transport_planner import TransportPlanner


# ─────────────────────────────────────────────────────────────────────────────
# Value objects
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ResourceEndpoint:
    """A (resource, actor) pair plus whether the resource offers a Handoff skill.

    `resource_id` is the short id (last URI segment) used in MQTT topics.
    `resource_iri` is the full AAS shell IRI — used to look up positions in
    the Line Configuration submodel, which is keyed by IRI.
    `has_handoff` is the capability check the matcher does upstream; the planner
    only consumes it. Shuttles typically have `has_handoff=False`.
    """
    resource_id: str
    actor_name: str
    has_handoff: bool
    resource_iri: str = ""


# A cargo transfer is (resource_id, actor_name, new_cargo_or_None) applied
# atomically when a step completes. `None` means "this actor stops carrying".
CargoTransfer = tuple[str, str, "str | None"]


@dataclass
class PreProcessStep:
    """A single executable step in a PreProcessPlan.

    `skill` matches the strings each station checks in its `starting()` method:
    "Transport", "Retrieve", "Handoff", "Store".

    `cargo_transfers` declares the physical-cargo side-effects of this step
    succeeding — the scheduler applies them to the OccupancyManager on
    StepStates.COMPLETED. A Transport step has none (the carrier just moves);
    a Retrieve sets cargo on the storage actor; a Handoff (per the 4-case
    rule) is the moment when cargo actually changes hands; a Store clears
    the storage actor's cargo.
    """
    step_id: str
    skill: str
    resource_id: str
    actor_name: str
    parameters: dict
    component_reference: str
    depends_on: str | None
    state: StepStates = StepStates.PENDING
    assigned_resource: str | None = None
    job_id: str | None = None
    cargo_transfers: tuple[CargoTransfer, ...] = ()
    # For Handoff steps only: which side of the handoff this CMD targets.
    # "sender" = currently holds the part and will release it (encodes as
    # InputTypes=None, OutputTypes=[iri]). "receiver" = will acquire the
    # part (encodes as InputTypes=[iri], OutputTypes=None). None for
    # non-Handoff steps.
    handoff_role: str | None = None
    timestamps: dict = field(default_factory=lambda: {
        StepStates.ASSIGNED: None,
        StepStates.IN_PROGRESS: None,
        StepStates.COMPLETED: None,
    })


@dataclass
class PreProcessPlan:
    """The ordered set of steps to insert before a BoP step.

    `occupies_through_bop` lists (resource_id, actor_name) pairs that must be
    marked occupied for the duration of the BoP step itself — used when there
    is no physical handoff and a shuttle must stay clamped under the target
    resource.
    """
    bop_step_id: str
    order_id: str
    target: ResourceEndpoint
    shuttle: ResourceEndpoint | None
    steps: list[PreProcessStep]
    occupies_through_bop: list[tuple[str, str]]


class NoShuttleAvailable(RuntimeError):
    """Raised when the plan needs transport but no shuttle was supplied."""


class NoReleaseSequence(RuntimeError):
    """Raised when a resource holds a part but can't release it.

    Happens if the resource has neither Retrieve (to pull it out of inventory)
    nor Handoff (to give it directly to a shuttle). The caller should pick a
    different source or surface a fault.
    """


def release_sequence_for(
    resource: "ResourceEndpoint",
    component_ref: str,
    *,
    shell_iri: str,
    rm,                # ResourceManager — kept loose to avoid a circular import
) -> list[str]:
    """Ordered skill names needed to make `component_ref` available for handoff
    from `resource`.

    Today's heuristic (data-driven via the resource's declared skills):
      - If the resource exposes a Retrieve skill → ["Retrieve", "Handoff"].
        (The scheduler has already verified this resource holds the component
        via ProductMatcher before calling this, so Retrieve is always valid.)
      - Else if the resource has Handoff → ["Handoff"]. (Used for picking up
        a part that's already sitting at a non-storage station.)
      - Otherwise raise NoReleaseSequence.

    Future: when each resource declares its own release recipe via an AAS
    submodel, this function reads that instead. The return shape stays the
    same so call sites don't change.
    """
    skills = rm.get_resource_skills(shell_iri)
    has_retrieve = "Retrieve" in skills

    if has_retrieve:
        return ["Retrieve", "Handoff"]
    if resource.has_handoff:
        return ["Handoff"]
    raise NoReleaseSequence(
        f"{resource.resource_id} cannot release {component_ref}: "
        f"has_retrieve={has_retrieve} has_handoff={resource.has_handoff}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Planner
# ─────────────────────────────────────────────────────────────────────────────

class PreProcessPlanner:
    """Builds a PreProcessPlan for a single BoP step.

    Stateless apart from its TransportPlanner reference; safe to call from
    the scheduler whenever a new BoP step becomes ready.
    """

    def __init__(self, transport_planner: "TransportPlanner") -> None:
        self.transport = transport_planner

    # ── Entry point ──────────────────────────────────────────────────────────

    def plan(
        self,
        *,
        bop_step_id: str,
        order_id: str,
        component_reference: str,
        current_location: ResourceEndpoint,
        target: ResourceEndpoint,
        shuttle: ResourceEndpoint | None,
        release_skills: list[str] | None = None,
    ) -> PreProcessPlan:
        """Build the pre-process plan for one BoP step.

        Args:
            bop_step_id: ProcessStepId of the BoP step (e.g. "1x1").
            order_id: WorkOrder OrderId (used for job_id construction).
            component_reference: IRI of the part being processed.
            current_location: where the part is right now (storage actor that
                will run the Retrieve / sender Handoff).
            target: the resource/actor that will perform the BoP step.
            shuttle: a Transport (resource, actor) reserved for this plan.
                May be None *only if* current_location.resource_id == target.resource_id.
            release_skills: ordered skill names needed to make the component
                releasable from `current_location` (typically computed via
                `release_sequence_for(...)`). Defaults to
                ["Retrieve", "Handoff"] for backwards-compat when the caller
                doesn't compute it explicitly.

        Returns:
            PreProcessPlan with sequential, chained steps. If the part is
            already at the target resource the plan has no steps.

        Raises:
            NoShuttleAvailable: if transport is required but no shuttle was supplied.
        """
        # Case: part already at target — nothing to do.
        if current_location.resource_id == target.resource_id:
            return PreProcessPlan(
                bop_step_id=bop_step_id,
                order_id=order_id,
                target=target,
                shuttle=None,
                steps=[],
                occupies_through_bop=[],
            )

        if shuttle is None:
            raise NoShuttleAvailable(
                f"BoP step {bop_step_id} needs transport from "
                f"{current_location.resource_id} to {target.resource_id} "
                "but no shuttle was supplied."
            )

        if release_skills is None:
            release_skills = ["Retrieve", "Handoff"]

        builder = _StepIdBuilder(bop_step_id)
        steps: list[PreProcessStep] = []

        storage_pos = self.transport.handoff_position(current_location.resource_iri)
        target_pos = self.transport.handoff_position(target.resource_iri)

        # 1) Move shuttle to the source handoff zone.
        # Shuttle is EMPTY on this leg — it hasn't picked up the part yet
        # (Retrieve+Handoff load it in steps 2 and 3). Pass an empty
        # component_reference so process_transformation encodes as
        # InputTypes=None, OutputTypes=None — matching the capability's
        # TransportEmpty declaration.
        steps.append(self._transport_step(
            builder=builder,
            shuttle=shuttle,
            target_resource_iri=current_location.resource_iri,
            component_reference="",
            depends_on=None,
        ))

        # 2) Optional: Retrieve the part from inventory (only if the
        #    release sequence calls for it — skip when picking up a part
        #    that's already at the resource but not in inventory).
        if "Retrieve" in release_skills:
            steps.append(self._retrieve_step(
                builder=builder,
                storage=current_location,
                component_reference=component_reference,
                depends_on=steps[-1].step_id,
            ))

        # 3) Handoff: storage → shuttle (rules applied).
        handoffs_a = self._build_handoff_steps(
            builder=builder,
            sender=current_location,
            receiver=shuttle,
            position=storage_pos,
            component_reference=component_reference,
            depends_on=steps[-1].step_id,
        )
        steps.extend(handoffs_a)
        last_id = handoffs_a[-1].step_id if handoffs_a else steps[-1].step_id

        # 4) Move shuttle to the target handoff zone.
        steps.append(self._transport_step(
            builder=builder,
            shuttle=shuttle,
            target_resource_iri=target.resource_iri,
            component_reference=component_reference,
            depends_on=last_id,
        ))

        # 5) Handoff: shuttle → target (rules applied).
        handoffs_b = self._build_handoff_steps(
            builder=builder,
            sender=shuttle,
            receiver=target,
            position=target_pos,
            component_reference=component_reference,
            depends_on=steps[-1].step_id,
        )
        steps.extend(handoffs_b)

        # 6) If neither shuttle nor target has Handoff, the shuttle must stay
        #    clamped under the target during the BoP step.
        occupies_through_bop: list[tuple[str, str]] = []
        if not shuttle.has_handoff and not target.has_handoff:
            occupies_through_bop.append((shuttle.resource_id, shuttle.actor_name))

        return PreProcessPlan(
            bop_step_id=bop_step_id,
            order_id=order_id,
            target=target,
            shuttle=shuttle,
            steps=steps,
            occupies_through_bop=occupies_through_bop,
        )

    # ── Post-process: store the finished part back into storage ──────────────

    def plan_post_process(
        self,
        *,
        bop_step_id: str,
        order_id: str,
        component_reference: str,
        target: ResourceEndpoint,
        store_destination: ResourceEndpoint,
        shuttle: ResourceEndpoint | None,
    ) -> PreProcessPlan:
        """Build the steps that move the finished part off the target resource
        and into the destination storage.

        Mirror of `plan()`: shuttle picks up from the target, transports to
        storage, stores it. Applies the same 4-case handoff rule between
        target↔shuttle and shuttle↔storage.

        Used after the final BoP step of a work order to close it out.

        Returns:
            PreProcessPlan with steps starting at id `{bop_step_id}-post1-...`.
        """
        if target.resource_id == store_destination.resource_id:
            return PreProcessPlan(
                bop_step_id=bop_step_id,
                order_id=order_id,
                target=store_destination,
                shuttle=None,
                steps=[],
                occupies_through_bop=[],
            )
        if shuttle is None:
            raise NoShuttleAvailable(
                f"Post-process for BoP step {bop_step_id} needs transport "
                f"from {target.resource_id} to {store_destination.resource_id} "
                "but no shuttle was supplied."
            )

        builder = _StepIdBuilder(f"{bop_step_id}-post")
        steps: list[PreProcessStep] = []

        target_pos = self.transport.handoff_position(target.resource_iri)
        store_pos = self.transport.handoff_position(store_destination.resource_iri)

        # 1) Move shuttle to the target's handoff zone.
        # Shuttle is EMPTY here too — the finished part is still on the
        # target; the shuttle goes to pick it up. See the matching comment
        # in plan() for why component_reference is empty on fetch legs.
        steps.append(self._transport_step(
            builder=builder,
            shuttle=shuttle,
            target_resource_iri=target.resource_iri,
            component_reference="",
            depends_on=None,
        ))

        # 2) Handoff: target → shuttle.
        handoffs_a = self._build_handoff_steps(
            builder=builder,
            sender=target,
            receiver=shuttle,
            position=target_pos,
            component_reference=component_reference,
            depends_on=steps[-1].step_id,
        )
        steps.extend(handoffs_a)
        last_id = handoffs_a[-1].step_id if handoffs_a else steps[-1].step_id

        # 3) Move shuttle to the storage handoff zone.
        steps.append(self._transport_step(
            builder=builder,
            shuttle=shuttle,
            target_resource_iri=store_destination.resource_iri,
            component_reference=component_reference,
            depends_on=last_id,
        ))

        # 4) Handoff: shuttle → storage.
        handoffs_b = self._build_handoff_steps(
            builder=builder,
            sender=shuttle,
            receiver=store_destination,
            position=store_pos,
            component_reference=component_reference,
            depends_on=steps[-1].step_id,
        )
        steps.extend(handoffs_b)

        # 5) Store: tell the storage station to file the part.
        steps.append(PreProcessStep(
            step_id=builder.next("store"),
            skill="Store",
            resource_id=store_destination.resource_id,
            actor_name=store_destination.actor_name,
            parameters={},
            component_reference=component_reference,
            depends_on=steps[-1].step_id,
            # After Store, the storage actor has filed the part — it no
            # longer carries it.
            cargo_transfers=(
                (store_destination.resource_id, store_destination.actor_name, None),
            ),
        ))

        return PreProcessPlan(
            bop_step_id=bop_step_id,
            order_id=order_id,
            target=store_destination,
            shuttle=shuttle,
            steps=steps,
            occupies_through_bop=[],
        )

    def plan_shuttle_to_target(
        self,
        *,
        bop_step_id: str,
        order_id: str,
        component_reference: str,
        shuttle: ResourceEndpoint,
        target: ResourceEndpoint,
    ) -> PreProcessPlan:
        """Plan an arrival when the shuttle already carries the cargo.

        Used when a prior BoP step left the input part on a shuttle and the
        next BoP step on the same order needs it elsewhere. Skips Retrieve
        and the source-side handoff entirely — just transport to the target
        and (if applicable) hand off into the target.

        Returns a PreProcessPlan with Transport + zero/one/two Handoff steps,
        following the same 4-case rule as the full plan() path.
        """
        builder = _StepIdBuilder(bop_step_id)
        steps: list[PreProcessStep] = []

        target_pos = self.transport.handoff_position(target.resource_iri)

        # 1) Move the shuttle (already carrying cargo) to the target.
        steps.append(self._transport_step(
            builder=builder,
            shuttle=shuttle,
            target_resource_iri=target.resource_iri,
            component_reference=component_reference,
            depends_on=None,
        ))

        # 2) Handoff: shuttle → target (rules applied).
        handoffs = self._build_handoff_steps(
            builder=builder,
            sender=shuttle,
            receiver=target,
            position=target_pos,
            component_reference=component_reference,
            depends_on=steps[-1].step_id,
        )
        steps.extend(handoffs)

        # If no physical handoff was produced (neither side has Handoff),
        # the shuttle must stay clamped under the target through the BoP.
        occupies = []
        if not handoffs:
            occupies = [(shuttle.resource_id, shuttle.actor_name)]

        return PreProcessPlan(
            bop_step_id=bop_step_id,
            order_id=order_id,
            target=target,
            shuttle=shuttle,
            steps=steps,
            occupies_through_bop=occupies,
        )

    # ── Step constructors ────────────────────────────────────────────────────

    def _transport_step(
        self,
        *,
        builder: "_StepIdBuilder",
        shuttle: ResourceEndpoint,
        target_resource_iri: str,
        component_reference: str,
        depends_on: str | None,
    ) -> PreProcessStep:
        # The Transport CMD's TargetPosition must be in the SHUTTLE's local
        # coordinate frame (bounded by the table size, e.g. 600..6600 mm),
        # not the global frame. The LineConfiguration's ConnectionPoint
        # records every connected resource with both global and local
        # coords; local_handoff_position picks out the shuttle's local view.
        local_target = self.transport.local_handoff_position(
            target_resource_iri, shuttle.resource_iri
        )
        return PreProcessStep(
            step_id=builder.next("transport"),
            skill="Transport",
            resource_id=shuttle.resource_id,
            actor_name=shuttle.actor_name,
            parameters=self.transport.transport_params(local_target, component_reference),
            component_reference=component_reference,
            depends_on=depends_on,
        )

    def _retrieve_step(
        self,
        *,
        builder: "_StepIdBuilder",
        storage: ResourceEndpoint,
        component_reference: str,
        depends_on: str | None,
    ) -> PreProcessStep:
        return PreProcessStep(
            step_id=builder.next("retrieve"),
            skill="Retrieve",
            resource_id=storage.resource_id,
            actor_name=storage.actor_name,
            parameters={},
            component_reference=component_reference,
            depends_on=depends_on,
            # After Retrieve, the storage actor is physically holding the part.
            cargo_transfers=(
                (storage.resource_id, storage.actor_name, component_reference),
            ),
        )

    def _handoff_step(
        self,
        *,
        builder: "_StepIdBuilder",
        performer: ResourceEndpoint,
        position: tuple[float, float],
        component_reference: str,
        depends_on: str | None,
        role: str,
    ) -> PreProcessStep:
        return PreProcessStep(
            step_id=builder.next("handoff"),
            skill="Handoff",
            resource_id=performer.resource_id,
            actor_name=performer.actor_name,
            parameters=self.transport.handoff_params(position, component_reference),
            component_reference=component_reference,
            depends_on=depends_on,
            handoff_role=role,
        )

    # ── Handoff rules ────────────────────────────────────────────────────────

    def _build_handoff_steps(
        self,
        *,
        builder: "_StepIdBuilder",
        sender: ResourceEndpoint,
        receiver: ResourceEndpoint,
        position: tuple[float, float],
        component_reference: str,
        depends_on: str | None,
    ) -> list[PreProcessStep]:
        """Apply the 4-case rule and return 0–2 handoff steps.

        Whenever at least one handoff is generated, the cargo transfer
        (sender loses, receiver gains) is attached to the LAST step in the
        sequence — the moment the part has physically changed hands. In the
        (False, False) case no steps are produced and the sender keeps the
        cargo (the shuttle stays clamped under the target through the BoP).
        """
        s = sender.has_handoff
        r = receiver.has_handoff

        cargo_after = (
            (sender.resource_id,   sender.actor_name,   None),
            (receiver.resource_id, receiver.actor_name, component_reference),
        )

        match (s, r):
            case (False, False):
                # No physical handoff possible — cargo stays with the sender.
                return []
            case (False, True):
                step = self._handoff_step(
                    builder=builder, performer=receiver, position=position,
                    component_reference=component_reference, depends_on=depends_on,
                    role="receiver",
                )
                step.cargo_transfers = cargo_after
                return [step]
            case (True, False):
                step = self._handoff_step(
                    builder=builder, performer=sender, position=position,
                    component_reference=component_reference, depends_on=depends_on,
                    role="sender",
                )
                step.cargo_transfers = cargo_after
                return [step]
            case (True, True):
                # Sender first (releases part), then receiver (acquires part).
                # Cargo moves only after the receiver finishes clamping it.
                first = self._handoff_step(
                    builder=builder, performer=sender, position=position,
                    component_reference=component_reference, depends_on=depends_on,
                    role="sender",
                )
                second = self._handoff_step(
                    builder=builder, performer=receiver, position=position,
                    component_reference=component_reference, depends_on=first.step_id,
                    role="receiver",
                )
                second.cargo_transfers = cargo_after
                return [first, second]
            case _:
                return []


# ─────────────────────────────────────────────────────────────────────────────
# Internal: deterministic step-id generation
# ─────────────────────────────────────────────────────────────────────────────

class _StepIdBuilder:
    """Builds step IDs of the form `{bop_step_id}-pp{idx}-{tag}`.

    The numeric index keeps execution order obvious in logs; the tag tells you
    what kind of step it is at a glance.
    """

    def __init__(self, bop_step_id: str) -> None:
        self._bop = bop_step_id
        self._counter = 0

    def next(self, tag: str) -> str:
        self._counter += 1
        return f"{self._bop}-pp{self._counter}-{tag}"
