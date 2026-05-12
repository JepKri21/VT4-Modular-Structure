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
    """In-memory ledger:  (resource_id_short, actor_name)  ->  order_id  (or None)."""

    OCCUPANCY_SUFFIX = "Occupancy"

    def __init__(self, controller=None, base_topic: str | None = None) -> None:
        """Args:
            controller: MQTT client used to publish `OccupancyMessage`. May be
                None for unit-test use; in that case publishing is skipped.
            base_topic: prefix like "AAUSmartLab/ProductionLine1". Needed when
                controller is set.
        """
        self._owner: dict[tuple[str, str], str | None] = {}
        self._controller = controller
        self._base_topic = base_topic

    # ── Queries ─────────────────────────────────────────────────────────────

    def is_occupied(self, resource_id_short: str, actor_name: str) -> bool:
        return self._owner.get((resource_id_short, actor_name)) is not None

    def owner_of(self, resource_id_short: str, actor_name: str) -> str | None:
        return self._owner.get((resource_id_short, actor_name))

    def all_occupied(self) -> list[tuple[str, str, str]]:
        """Snapshot of (resource_id, actor_name, order_id) for everything currently held."""
        return [
            (r, a, o) for (r, a), o in self._owner.items() if o is not None
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
    ) -> None:
        """Release a single (resource, actor) that was held for this order."""
        key = (resource_id_short, actor_name)
        if self._owner.get(key) != order_id:
            return
        self._owner[key] = None
        self._publish(resource_id_short, actor_name, order_id, occupied=False)
        print(f"[occupancy] order={order_id} released: {key}")

    # ── MQTT publish ────────────────────────────────────────────────────────

    def _publish(
        self,
        resource_id_short: str,
        actor_name: str,
        order_id: str,
        occupied: bool,
    ) -> None:
        if self._controller is None or self._base_topic is None:
            return
        shell_iri = self._controller.topic_to_shell_id.get(resource_id_short)
        if shell_iri is None:
            return
        # OccupancyMessage doesn't carry an actor name, so we encode it in the topic.
        topic = (
            f"{self._base_topic}/{resource_id_short}/"
            f"{self.OCCUPANCY_SUFFIX}/{actor_name}"
        )
        msg = MS.OccupancyMessage(
            timestamp=datetime.now(),
            job_id=order_id,           # we use order_id as the job_id label here
            occupied=occupied,
            resource_id=resource_id_short,
            seq_no=None,
        )
        try:
            self._controller.client.publish(topic, msg.model_dump_json())
        except Exception as e:
            print(f"[occupancy] publish failed for {topic}: {e}")
