"""Tracks which (resource, actor) pairs are currently reserved for an order.

This is the Line Controller's internal occupancy ledger. It exists so two
concurrent orders can't both grab the same shuttle while it's still carrying
a part for the first one. Occupancy is independent of PackML state — a
shuttle holding a part may be PackMLState.IDLE between Transport hops, but
must NOT be assignable to other orders.

The decision was made by the group:

    "Orchestrator keeps track of occupancy, but shares occupancy status on
     MQTT. If no resources of the two have a handoff, both will be occupied
     until the process is done."

So we keep the truth here and also publish `OccupancyMessage` to a
per-(resource, actor) topic for any observer that cares.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS


class OccupancyManager:
    """In-memory ledger keyed by (resource_id_short, actor_name).

    Tracks two parallel facts per actor:

    - **owner**: which order_id has reserved this actor (cross-order arbitration).
    - **cargo**: which component_ref this actor is currently physically carrying
      (set on Retrieve/Handoff-receive, cleared on Handoff-give/Store).

    An actor is **available** when both are empty — not reserved AND not
    holding anything. That second condition is what stops a "free" shuttle
    from being given a new job while it's still clamping the part from the
    last one.

    The topic suffixes used for the MQTT broadcasts come from each resource's
    Communication submodel (OccupancySuffix / CargoSuffix) via the
    controller's topic_maps — they're NOT hardcoded here.
    """

    def __init__(self, controller=None, base_topic: str | None = None) -> None:
        """Args:
            controller: MQTT client used to publish status messages. May be
                None for unit-test use; in that case publishing is skipped.
            base_topic: prefix like "AAUSmartLab/ProductionLine1". Needed when
                controller is set.
        """
        self._owner: dict[tuple[str, str], str | None] = {}
        self._cargo: dict[tuple[str, str], str | None] = {}
        # Stuck-cargo ledger: when an order fails while an actor is still
        # carrying its cargo, we cannot release the (resource, actor)
        # reservation safely — a part really is sitting on that shuttle.
        # Mark it stuck instead; the actor is unavailable to all orders
        # until an operator clears it via MQTT (see main.py handler).
        self._stuck: set[tuple[str, str]] = set()
        self._controller = controller
        self._base_topic = base_topic

    # ── Queries ─────────────────────────────────────────────────────────────

    def is_occupied(self, resource_id_short: str, actor_name: str) -> bool:
        return self._owner.get((resource_id_short, actor_name)) is not None

    def has_cargo(self, resource_id_short: str, actor_name: str) -> bool:
        return self._cargo.get((resource_id_short, actor_name)) is not None

    def is_stuck(self, resource_id_short: str, actor_name: str) -> bool:
        return (resource_id_short, actor_name) in self._stuck

    def is_available(self, resource_id_short: str, actor_name: str) -> bool:
        """Not reserved for an order AND not currently carrying anything
        AND not marked as stuck after a failed order."""
        return (
            not self.is_occupied(resource_id_short, actor_name)
            and not self.has_cargo(resource_id_short, actor_name)
            and not self.is_stuck(resource_id_short, actor_name)
        )

    def mark_stuck(self, resource_id_short: str, actor_name: str) -> None:
        """Flag an actor as physically holding cargo we can no longer track.

        Called by recovery when an order fails while one of its actors
        still has cargo. The actor stays excluded from new assignments
        until clear_stuck() is called (typically by an operator via the
        ClearStuckCargo topic).
        """
        key = (resource_id_short, actor_name)
        self._stuck.add(key)
        print(f"[occupancy] STUCK CARGO: {resource_id_short}/{actor_name}")

    def clear_stuck(self, resource_id_short: str, actor_name: str) -> bool:
        """Operator action: confirm the part has been removed manually.

        Also clears the cargo ledger so the actor returns to fully
        available. Returns True if the actor was actually stuck.
        """
        key = (resource_id_short, actor_name)
        if key not in self._stuck:
            return False
        self._stuck.discard(key)
        self._cargo[key] = None
        print(f"[occupancy] stuck cleared: {resource_id_short}/{actor_name}")
        return True

    def stuck_pairs_for_order(
        self,
        order_id: str,
    ) -> list[tuple[str, str]]:
        """All (resource, actor) reserved by this order that have cargo —
        i.e. the actors that would need to be marked stuck if the order
        fails right now.
        """
        return [
            (r, a)
            for (r, a), owner in self._owner.items()
            if owner == order_id and self._cargo.get((r, a)) is not None
        ]

    def owner_of(self, resource_id_short: str, actor_name: str) -> str | None:
        return self._owner.get((resource_id_short, actor_name))

    def cargo_of(self, resource_id_short: str, actor_name: str) -> str | None:
        return self._cargo.get((resource_id_short, actor_name))

    def find_holder(self, component_ref: str) -> tuple[str, str] | None:
        """First (resource_id, actor) currently carrying this component, or None."""
        for (resource_id, actor), cargo in self._cargo.items():
            if cargo == component_ref or (
                cargo is not None and cargo.startswith(component_ref + "/")
            ):
                return (resource_id, actor)
        return None

    def all_occupied(self) -> list[tuple[str, str, str]]:
        """Snapshot of (resource_id, actor_name, order_id) for everything currently held."""
        return [
            (r, a, o) for (r, a), o in self._owner.items() if o is not None
        ]

    def all_cargo(self) -> list[tuple[str, str, str]]:
        """Snapshot of (resource_id, actor_name, component_ref) for everything carried."""
        return [
            (r, a, c) for (r, a), c in self._cargo.items() if c is not None
        ]

    # ── Mutations ───────────────────────────────────────────────────────────

    def commit(
        self,
        order_id: str,
        actors: list[tuple[str, str]],
    ) -> None:
        """Reserve (resource, actor) pairs for one order. Idempotent for same order."""
        for resource_id, actor_name in actors:
            key = (resource_id, actor_name)
            current = self._owner.get(key)
            if current is not None and current != order_id:
                raise RuntimeError(
                    f"{resource_id}/{actor_name} already reserved for {current}; "
                    f"cannot also assign to {order_id}"
                )
            self._owner[key] = order_id
            self._publish(resource_id, actor_name, order_id, occupied=True)
        print(f"[occupancy] order={order_id} committed: {actors}")

    def try_commit(
        self,
        order_id: str,
        actors: list[tuple[str, str]],
    ) -> tuple[str, str] | None:
        """Non-blocking variant of commit: claim all-or-nothing.

        Returns None on success. On failure, returns the first (resource,
        actor) pair that was already held by a different order — caller can
        log it and back off until that pair frees. No partial reservations
        are made on failure.
        """
        for resource_id, actor_name in actors:
            owner = self._owner.get((resource_id, actor_name))
            if owner is not None and owner != order_id:
                return (resource_id, actor_name)
        # All free or already ours — claim them.
        self.commit(order_id, actors)
        return None

    def release(self, order_id: str) -> list[tuple[str, str]]:
        """Drop every reservation held by an order. Returns the freed pairs."""
        freed: list[tuple[str, str]] = []
        for key, owner in list(self._owner.items()):
            if owner == order_id:
                self._owner[key] = None
                freed.append(key)
                self._publish(key[0], key[1], order_id, occupied=False)
        if freed:
            print(f"[occupancy] order={order_id} released: {freed}")
        return freed

    def release_one(
        self, resource_id_short: str, actor_name: str, order_id: str
    ) -> bool:
        """Try to release a single (resource, actor) reservation.

        Refuses if the actor is still carrying cargo — releasing would let
        another order grab it while it still physically holds a part.

        Returns:
            True if the reservation was dropped, False if it was kept
            because the actor still has cargo or wasn't reserved by this order.
        """
        key = (resource_id_short, actor_name)
        if self._owner.get(key) != order_id:
            return False
        if self.has_cargo(resource_id_short, actor_name):
            print(
                f"[occupancy] not releasing {resource_id_short}/{actor_name}: "
                f"still carrying {self.cargo_of(resource_id_short, actor_name)}"
            )
            return False
        self._owner[key] = None
        self._publish(resource_id_short, actor_name, order_id, occupied=False)
        print(f"[occupancy] order={order_id} released: {key}")
        return True

    # ── Cargo mutations ─────────────────────────────────────────────────────

    def set_cargo(
        self, resource_id_short: str, actor_name: str, component_ref: str
    ) -> None:
        """Record that this actor is now physically carrying this component."""
        self._cargo[(resource_id_short, actor_name)] = component_ref
        self._publish_cargo(resource_id_short, actor_name, component_ref)
        print(f"[cargo]     {resource_id_short}/{actor_name} <- {component_ref}")

    def clear_cargo(self, resource_id_short: str, actor_name: str) -> None:
        """Record that this actor no longer carries anything."""
        if not self.has_cargo(resource_id_short, actor_name):
            return
        prev = self._cargo.pop((resource_id_short, actor_name), None)
        self._publish_cargo(resource_id_short, actor_name, None)
        print(f"[cargo]     {resource_id_short}/{actor_name} -> (empty) (was {prev})")

    def apply_cargo_transfers(
        self,
        transfers: "tuple[tuple[str, str, str | None], ...] | list[tuple[str, str, str | None]]",
    ) -> None:
        """Apply a step's `cargo_transfers` declaration in one call.

        Each entry is (resource_id, actor, new_cargo_or_None).
        """
        for resource_id, actor, new_cargo in transfers:
            if new_cargo is None:
                self.clear_cargo(resource_id, actor)
            else:
                self.set_cargo(resource_id, actor, new_cargo)

    # ── MQTT publish ────────────────────────────────────────────────────────

    def _suffix_for(self, resource_id_short: str, message_type) -> str | None:
        """Look up the topic suffix for a message type on a given resource.

        The suffix comes from each resource's Communication submodel, threaded
        through the controller's `topic_maps`. Returns None if the controller
        has no mapping (e.g. resource doesn't expose this message type).
        """
        if self._controller is None:
            return None
        topic_map = self._controller.topic_maps.get(resource_id_short, {})
        return topic_map.get(message_type)

    def _publish(
        self,
        resource_id_short: str,
        actor_name: str,
        order_id: str,
        occupied: bool,
    ) -> None:
        if self._controller is None or self._base_topic is None:
            return
        suffix = self._suffix_for(resource_id_short, MS.OccupancyMessage)
        if not suffix:
            return  # resource doesn't declare an OccupancySuffix — skip
        # OccupancyMessage carries no actor field, so the actor is in the topic.
        topic = f"{self._base_topic}/{resource_id_short}/{suffix}/{actor_name}"
        msg = MS.OccupancyMessage(
            timestamp=datetime.now(),
            job_id=order_id,           # using order_id as the job-level label here
            occupied=occupied,
            resource_id=resource_id_short,
            seq_no=None,
        )
        try:
            self._controller.client.publish(topic, msg.model_dump_json())
        except Exception as e:
            print(f"[occupancy] publish failed for {topic}: {e}")

    def _publish_cargo(
        self,
        resource_id_short: str,
        actor_name: str,
        component_ref: str | None,
    ) -> None:
        """Broadcast the current cargo state of one actor via CargoMessage."""
        if self._controller is None or self._base_topic is None:
            return
        suffix = self._suffix_for(resource_id_short, MS.CargoMessage)
        if not suffix:
            return  # resource doesn't declare a CargoSuffix — skip
        topic = f"{self._base_topic}/{resource_id_short}/{suffix}/{actor_name}"
        msg = MS.CargoMessage(
            timestamp=datetime.now(),
            resource_id=resource_id_short,
            component_reference=component_ref,
            seq_no=None,
        )
        try:
            self._controller.client.publish(topic, msg.model_dump_json())
        except Exception as e:
            print(f"[cargo] publish failed for {topic}: {e}")
