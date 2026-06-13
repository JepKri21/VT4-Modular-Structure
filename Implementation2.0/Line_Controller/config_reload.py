"""Live line-reconfiguration coordinator (Phases 1 + 2).

When the ProductionLine `LineConfiguration` on the AAS server changes, an
external editor (the webstore configurator) publishes a ping on
`AAUSmartLab/<line>/Controller/ReloadConfig`. The controller re-pulls the config
and applies it to the running scheduler without a restart:

    ping -> re-pull config -> re-infer transport graph -> add/subscribe new
    resources (gated until first contact) -> remove/drain departed resources
    -> re-poll inventory.

Removal lifecycle:
  - A resource removed from the config that is **idle** is dropped immediately.
  - A resource removed while **in use** by an order enters `draining`: it stays
    subscribed and routable for that order (excluded from new assignments) until
    it goes idle, at which point `finalize_drained()` drops + unsubscribes it.
    While draining it is kept in the planner's *effective* topology so the
    owning order's routing still resolves.

Concurrency: `request_reload()` and `finalize_drained()` both run on the asyncio
loop thread (the MQTT handler bounces into it; the sweep is driven by the
snapshot loop). Neither `await`s partway through a mutation, so they can't
interleave with a scheduler planning pass (synchronous on the same loop). Pings
arriving mid-reload are coalesced into one follow-up pass.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS
from transport_planner import LineConfig, load_line_config_from_aas
from resource_manager import ResourceManager

if TYPE_CHECKING:
    from transport_planner import TransportPlanner
    from scheduler import Scheduler
    from MQTTClientControllerV2 import MQTTClientController
    from product_property_matcher import ProductMatcher
    from occupancy_manager import OccupancyManager
    from controller_alarms import ControllerAlarmPublisher


class ConfigReloader:
    """Owns the live re-pull + apply of the LineConfiguration."""

    def __init__(
        self,
        *,
        aas_server_base: str,
        line_shell_prefix: str,
        transport_planner: "TransportPlanner",
        scheduler: "Scheduler",
        resource_manager: ResourceManager,
        controller: "MQTTClientController",
        product_matcher: "ProductMatcher",
        occupancy: "OccupancyManager",
        alarm_publisher: "ControllerAlarmPublisher | None" = None,
    ) -> None:
        self._aas_server_base = aas_server_base
        self._line_shell_prefix = line_shell_prefix
        self._planner = transport_planner
        self._scheduler = scheduler
        self._rm = resource_manager
        self._controller = controller
        self._product_matcher = product_matcher
        self._occupancy = occupancy
        self._alarms = alarm_publisher

        # Last pulled config WITHOUT the draining-resource merges. The planner's
        # live config may additionally carry draining resources (see
        # _build_effective); this is the clean baseline to rebuild from.
        self._base_config: LineConfig = transport_planner.config

        self._pending = False
        self._task: asyncio.Task | None = None
        # Bumped on every successful apply. Currently informational; the R1
        # commit-point guard in the scheduler checks the registry directly.
        self.epoch = 0

    # ── Public API ───────────────────────────────────────────────────────────

    def request_reload(self) -> None:
        """Request a reload. Coalesces concurrent requests into one pass.

        Must be called on the event loop thread.
        """
        self._pending = True
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    def finalize_drained(self) -> None:
        """Drop any draining resource that has gone idle. Cheap; safe to call
        every tick (driven by the snapshot loop). Runs on the loop thread."""
        if not self._rm._draining:
            return
        finalized: list[str] = []
        for iri in list(self._rm._draining):
            suffix = ResourceManager.topic_id_for_iri(iri)
            if self._is_resource_active(iri):
                continue
            self._rm.remove_resource(iri)          # also discards from _draining
            self._controller.unsubscribe_resource(suffix)
            self._controller.forget_resource(iri)  # clear stale lane/state
            finalized.append(iri)

        if not finalized:
            return
        # Rebuild the topology from the clean baseline plus whatever is still
        # draining; the finalized resources fall out for good.
        effective = self._build_effective(
            self._base_config, self._rm._draining, source=self._planner.config
        )
        self._planner.reload(effective)
        self._scheduler.locations = effective.locations
        # A finalized resource may have been a shuttle, so transport capacity
        # could have dropped — and the inventory registry must forget it.
        self._product_matcher.rebuild_inventory_registry(effective.locations)
        self.publish_capacity()
        print(
            "[reload] finalized drained resource(s): "
            f"{[ResourceManager.topic_id_for_iri(i) for i in finalized]}"
        )

    def publish_capacity(self) -> None:
        """Publish the line's transport capacity (retained) so the MES
        dispatcher can size how many orders to release.

        Capacity = the number of Transport actors on the line. On a no-handoff
        line a shuttle is held from a part's first Retrieve to its final Store,
        so the Transport-actor count is the true ceiling on simultaneous orders.
        Retained so a late-joining dispatcher still sees the current value.
        """
        from datetime import datetime

        capacity = sum(
            len(actors)
            for _iri, _topic, actors in self._rm.find_skill_offering("Transport")
        )
        line_id = self._controller.base_topic.rsplit("/", 1)[-1]
        topic = f"{self._controller.base_topic}/Controller/Capacity"
        msg = MS.LineCapacityMessage(
            timestamp=datetime.now(),
            line_id=line_id,
            max_concurrent=capacity,
            seq_no=None,
        )
        try:
            self._controller.client.publish(
                topic, msg.model_dump_json(), qos=1, retain=True
            )
            print(f"[capacity] published max_concurrent={capacity} -> {topic}")
        except Exception as exc:  # noqa: BLE001 - publish failure must not crash reload
            print(f"[capacity] publish failed: {exc}")

    # ── Internals ────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        # Drain the pending flag in a loop so a ping that lands mid-reload still
        # triggers exactly one more pass (and no more).
        while self._pending:
            self._pending = False
            try:
                self._apply_reload()
            except Exception as exc:  # noqa: BLE001 - reload must never crash the loop
                print(f"[reload] FAILED, keeping previous config: {exc}")
                if self._alarms is not None:
                    self._alarms.publish(
                        category=MS.AlarmCategory.CONFIG_RELOAD_FAILED,
                        severity=MS.AlarmSeverity.ERROR,
                        message=f"Line config reload failed: {exc}",
                    )

    def _apply_reload(self) -> None:
        """Pull the new config and apply it. Blocking; runs on the loop thread.

        Fallible work (pull, parse, uniqueness check) happens before any state
        is mutated, so a bad reload leaves the running config untouched.
        """
        # 1. Pull + parse (fallible). Raises on AAS error / malformed submodel.
        new_config = load_line_config_from_aas(
            self._aas_server_base, self._line_shell_prefix
        )

        # 2. R7 — reject suffix collisions before touching anything. Topics key
        #    off the last IRI path segment, so two resources sharing a suffix
        #    would collide onto one shell.
        suffix_to_iri: dict[str, str] = {}
        for iri in new_config.locations:
            suffix = ResourceManager.topic_id_for_iri(iri)
            if suffix in suffix_to_iri and suffix_to_iri[suffix] != iri:
                raise ValueError(
                    f"duplicate topic suffix '{suffix}' for {iri} and "
                    f"{suffix_to_iri[suffix]} — resources need unique idShorts"
                )
            suffix_to_iri[suffix] = iri

        old_config = self._planner.config  # effective config currently in use
        new_iris = set(new_config.locations)
        # Departed = was in the previous *base* line, now gone. (Draining
        # resources that are still gone are re-evaluated below.)
        gone = (set(self._base_config.locations) | self._rm._draining) - new_iris

        # 3. A resource that came BACK into the config is live again.
        for iri in new_iris & set(self._rm._draining):
            self._rm._draining.discard(iri)

        # 4. Classify each departed resource: active -> drain, idle -> drop now.
        dropped_now: list[str] = []
        draining_new: list[str] = []
        for iri in gone:
            suffix = ResourceManager.topic_id_for_iri(iri)
            if self._is_resource_active(iri):
                self._rm.mark_draining(iri)
                draining_new.append(iri)
            else:
                self._rm.remove_resource(iri)
                self._controller.unsubscribe_resource(suffix)
                self._controller.forget_resource(iri)  # clear stale lane/state
                dropped_now.append(iri)

        # 5. Build the effective topology: the new config plus any resource
        #    still draining (so the owning order's routing keeps resolving).
        effective = self._build_effective(
            new_config, self._rm._draining, source=old_config
        )
        self._planner.reload(effective)
        self._base_config = new_config
        self._scheduler.locations = effective.locations

        # 6. Discover newly configured shells (gated until first contact).
        added = self._rm.update_resource_availablility(
            allowed_iris=new_iris, mark_new_pending=True
        )

        # 7. Build topic maps + subscribe new namespaces.
        self._controller.refresh_subscriptions()

        # 8. Rebuild the inventory registry (which resources have an Inventory
        #    submodel + which types each supports) so scoped lookups route
        #    correctly after the config change. This also re-indexes every
        #    component, so it serves as the inventory reload for the new line.
        self._product_matcher.rebuild_inventory_registry(effective.locations)

        # 9. Republish transport capacity — a reload may have added or removed
        #    shuttles, changing how many orders the line can run at once.
        self.publish_capacity()

        self.epoch += 1
        print(
            f"[reload] applied epoch={self.epoch} "
            f"added={[ResourceManager.topic_id_for_iri(i) for i in added]} "
            f"dropped={[ResourceManager.topic_id_for_iri(i) for i in dropped_now]} "
            f"draining={[ResourceManager.topic_id_for_iri(i) for i in draining_new]} "
            f"total_in_config={len(new_iris)}"
        )

    def _is_resource_active(self, iri: str) -> bool:
        """True if a resource is still doing work and must not be yanked.

        Two signals, because they cover different resource kinds:
        - occupancy ledger: a resource whose actor is *reserved* or carrying
          cargo (shuttles, custody holders).
        - PackML state: a resource performing an *in-place* operation (e.g. a
          drill working on a part still held by a shuttle) is never reserved in
          the occupancy ledger, so we also treat any non-idle actor state as
          active. Without this, an actively-drilling station looks idle and gets
          dropped mid-job, freezing its last state in the UI.
        """
        suffix = ResourceManager.topic_id_for_iri(iri)
        if self._occupancy.is_resource_busy(suffix):
            return True
        states = self._controller.shared_handler_variable.get("state", {}).get(iri, {})
        for st in list(states.values()):
            label = getattr(st, "value", str(st))
            if label not in ("IDLE", "STOPPED", "ABORTED"):
                return True
        return False

    @staticmethod
    def _build_effective(
        base: LineConfig, draining: set[str], source: LineConfig
    ) -> LineConfig:
        """Effective topology = `base` plus the entries of any still-draining
        resource, pulled from `source`. This keeps a draining resource fully
        routable (position + connection points) for the order finishing on it,
        while it stays out of the base config used for new orders.
        """
        if not draining:
            return base

        locations = dict(base.locations)
        iri_to_id = dict(base.iri_to_id)
        for iri in draining:
            if iri in source.locations:
                locations[iri] = source.locations[iri]
                iri_to_id[iri] = source.iri_to_id.get(
                    iri, ResourceManager.topic_id_for_iri(iri)
                )

        seen = {cp.id_short for cp in base.connection_points}
        connection_points = list(base.connection_points)
        for cp in source.connection_points:
            if cp.id_short in seen:
                continue
            if any(cr.resource_iri in draining for cr in cp.connected):
                connection_points.append(cp)
                seen.add(cp.id_short)

        return LineConfig(
            locations=locations,
            iri_to_id=iri_to_id,
            connection_points=tuple(connection_points),
        )
