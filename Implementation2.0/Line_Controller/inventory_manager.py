"""Tracks which storage resource currently holds which component instances.

Storage stations publish `InventoryLevelMessage` (one per station) listing all
items currently in their inventories. The Line Controller asks each station
for that on startup via an InfoRequest, then keeps it fresh as further
inventory messages arrive.

`find_storage_for(component_ref)` returns the storage IRIs that hold a match
for the work order's `ComponentReference`. Matching mirrors the storage
station's own `find_positions` logic: an exact-instance IRI matches verbatim,
or a type-prefix IRI matches any instance under it.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS

from resource_manager import ResourceManager


class InventoryManager:
    """Per-storage IRI -> list of component IRIs currently held."""

    def __init__(self) -> None:
        self.inventories: dict[str, list[str]] = {}

    def update(self, storage_iri: str, all_items: list[str]) -> None:
        self.inventories[storage_iri] = list(all_items)

    def find_storage_for(self, component_ref: str) -> list[tuple[str, str]]:
        """Return [(storage_iri, matched_item_iri)] for storages holding this component.

        `component_ref` can be a type IRI (e.g. .../Component/Bottom_Cover) or a
        specific instance IRI (e.g. .../Bottom_Cover/Bottom_Cover-BC001). The
        first matching item per storage is returned — we don't try to balance.
        """
        results = []
        for storage_iri, items in self.inventories.items():
            for item in items:
                if item == component_ref or item.startswith(component_ref + "/"):
                    results.append((storage_iri, item))
                    break
        return results

    def make_handler(self):
        """Build the MQTT InventoryLevelMessage handler closure.

        The InventoryLevelMessage schema nests as
            inventory[<inventory_name>].storage[<position>].component_id
        We flatten that into the list of currently-held item IRIs so
        `find_storage_for` can scan it directly.
        """
        def handle(controller, message: MS.InventoryLevelMessage, topic_info) -> None:
            resource_suffix = topic_info.get("resource_suffix")
            shell_iri = controller.topic_to_shell_id.get(resource_suffix)
            if shell_iri is None:
                return
            items: list[str] = []
            for inv in message.inventory.values():
                for slot in inv.storage.values():
                    if slot.component_id:
                        items.append(slot.component_id)
            self.update(shell_iri, items)
            print(f"[inventory] {resource_suffix}: {len(items)} item(s) catalogued")
        return handle


def request_inventory_update(controller, rm: ResourceManager) -> None:
    """Send InfoRequest for InventoryLevel to every resource that exposes Retrieve.

    Each such resource (a storage station) will publish its
    `InventoryLevelMessage` in response. The InventoryManager handler catches
    those and populates its lookup table.
    """
    for iri, _topic, _actors in rm.find_skill_offering("Retrieve"):
        resource_suffix = ResourceManager.topic_id_for_iri(iri)
        topic_map = controller.topic_maps.get(resource_suffix, {})
        inv_suffix = topic_map.get(MS.InventoryLevelMessage)
        if not inv_suffix:
            print(f"[warn] no InventoryLevelSuffix for {resource_suffix}; skipping")
            continue
        msg = MS.RequestMessage(
            timestamp=datetime.now(),
            requested_topic_update=f"{controller.base_topic}/{resource_suffix}/{inv_suffix}",
            resource_id=resource_suffix,
            seq_no=None,
        )
        controller.publish_message(iri, msg)
        print(f"[init] requested InventoryLevel from {resource_suffix}")
