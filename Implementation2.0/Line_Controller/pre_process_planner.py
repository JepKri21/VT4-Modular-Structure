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
from datetime import datetime
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

    `has_handoff` is the capability check the matcher does upstream; the planner
    only consumes it. Shuttles typically have `has_handoff=False`.
    """
    resource_id: str
    actor_name: str
    has_handoff: bool


@dataclass
class PreProcessStep:
    """A single executable step in a PreProcessPlan.

    `skill` matches the strings each station checks in its `starting()` method:
    "Transport", "Retrieve", "Handoff".
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

        builder = _StepIdBuilder(bop_step_id)
        steps: list[PreProcessStep] = []

        storage_pos = self.transport.handoff_position(current_location.resource_id)
        target_pos = self.transport.handoff_position(target.resource_id)

        # 1) Move shuttle to the storage handoff zone.
        steps.append(self._transport_step(
            builder=builder,
            shuttle=shuttle,
            target_position=storage_pos,
            component_reference=component_reference,
            depends_on=None,
        ))

        # 2) Retrieve the part from storage.
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
            target_position=target_pos,
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

        target_pos = self.transport.handoff_position(target.resource_id)
        store_pos = self.transport.handoff_position(store_destination.resource_id)

        # 1) Move shuttle to the target's handoff zone.
        steps.append(self._transport_step(
            builder=builder,
            shuttle=shuttle,
            target_position=target_pos,
            component_reference=component_reference,
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
            target_position=store_pos,
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
            parameters={"ComponentReference": component_reference},
            component_reference=component_reference,
            depends_on=steps[-1].step_id,
        ))

        return PreProcessPlan(
            bop_step_id=bop_step_id,
            order_id=order_id,
            target=store_destination,
            shuttle=shuttle,
            steps=steps,
            occupies_through_bop=[],
        )

    # ── Step constructors ────────────────────────────────────────────────────

    def _transport_step(
        self,
        *,
        builder: "_StepIdBuilder",
        shuttle: ResourceEndpoint,
        target_position: tuple[float, float],
        component_reference: str,
        depends_on: str | None,
    ) -> PreProcessStep:
        return PreProcessStep(
            step_id=builder.next("transport"),
            skill="Transport",
            resource_id=shuttle.resource_id,
            actor_name=shuttle.actor_name,
            parameters=self.transport.transport_params(target_position, component_reference),
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
            parameters={"ComponentReference": component_reference},
            component_reference=component_reference,
            depends_on=depends_on,
        )

    def _handoff_step(
        self,
        *,
        builder: "_StepIdBuilder",
        performer: ResourceEndpoint,
        position: tuple[float, float],
        component_reference: str,
        depends_on: str | None,
    ) -> PreProcessStep:
        return PreProcessStep(
            step_id=builder.next("handoff"),
            skill="Handoff",
            resource_id=performer.resource_id,
            actor_name=performer.actor_name,
            parameters=self.transport.handoff_params(position, component_reference),
            component_reference=component_reference,
            depends_on=depends_on,
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
        """Apply the 4-case rule and return 0–2 handoff steps."""
        s = sender.has_handoff
        r = receiver.has_handoff

        match (s, r):
            case (False, False):
                # No physical handoff possible — occupation carries the part logically.
                return []
            case (False, True):
                return [self._handoff_step(
                    builder=builder, performer=receiver, position=position,
                    component_reference=component_reference, depends_on=depends_on,
                )]
            case (True, False):
                return [self._handoff_step(
                    builder=builder, performer=sender, position=position,
                    component_reference=component_reference, depends_on=depends_on,
                )]
            case (True, True):
                # Sender first (releases part), then receiver (acquires part).
                first = self._handoff_step(
                    builder=builder, performer=sender, position=position,
                    component_reference=component_reference, depends_on=depends_on,
                )
                second = self._handoff_step(
                    builder=builder, performer=receiver, position=position,
                    component_reference=component_reference, depends_on=first.step_id,
                )
                return [first, second]
            case _:
                # Unreachable — kept for exhaustiveness.
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
