"""Periodic orchestration snapshot for the Production Monitoring UI.

Publishes a single JSON document to
    AAUSmartLab/<line>/Orchestration/Snapshot
that summarises everything the React app needs to render the live page:
the order queue, the per-actor lanes, and the instance reservations.

Derived entirely from existing in-memory state — no new sources of truth.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scheduler import Scheduler
    from MQTTClientControllerV2 import MQTTClientController


SNAPSHOT_SUFFIX = "Orchestration/Snapshot"
DEFAULT_PERIOD_S = 1.0


def build_snapshot(scheduler: "Scheduler", controller: "MQTTClientController") -> dict:
    """Build one snapshot dict from current Scheduler + Controller state."""
    state_store = controller.shared_handler_variable.get("state", {}) or {}

    # ── Orders ──────────────────────────────────────────────────────────────
    orders = []
    for order_id, handler in list(scheduler._active_orders.items()):
        wo = handler.workorder or {}
        steps = (handler.execution_plan or {}).get("steps", [])
        steps_out = []
        for s in steps:
            state = s.get("state")
            steps_out.append({
                "step_id": s.get("step_id"),
                "name": s.get("name"),
                "ingredient": s.get("ingredient"),
                "capability": s.get("required_capability"),
                "precedence": s.get("precedence"),
                "state": state.value if hasattr(state, "value") else str(state),
                "assigned_resource": s.get("assigned_resource"),
            })
        current = next(
            (s for s in steps_out if s["state"] == "IN_PROGRESS"),
            next((s for s in steps_out if s["state"] in ("ASSIGNED", "PENDING")), None),
        )
        orders.append({
            "order_id": order_id,
            "product_reference": wo.get("ProductReference"),
            "priority": wo.get("Priority"),
            "issued_at": wo.get("IssueDate"),
            "current_step": current["step_id"] if current else None,
            "steps": steps_out,
        })

    # ── Lanes (one per actor that ever announced state) ─────────────────────
    lanes = []
    for shell_iri, by_actor in state_store.items():
        topic = controller.shell_id_to_topic.get(shell_iri, shell_iri.rsplit("/", 1)[-1])
        for actor_name, packml_state in (by_actor or {}).items():
            lanes.append({
                "resource_iri": shell_iri,
                "resource_id": topic,
                "actor_name": actor_name,
                "packml_state": (
                    packml_state.value if hasattr(packml_state, "value") else str(packml_state)
                ),
                "owner_order": scheduler.occupancy.owner_of(topic, actor_name),
                "cargo": scheduler.occupancy.cargo_of(topic, actor_name),
                "stuck": scheduler.occupancy.is_stuck(topic, actor_name),
            })

    # ── Reservations (instance IRI → order) ─────────────────────────────────
    reservations = [
        {"instance_iri": iri, "owner_order": owner}
        for iri, owner in scheduler._reserved_instances.items()
    ]

    return {
        "schema_version": "1.0",
        "timestamp": datetime.now().isoformat(),
        "orders": orders,
        "lanes": lanes,
        "reservations": reservations,
    }


async def run_snapshot_publisher(
    scheduler: "Scheduler",
    controller: "MQTTClientController",
    base_topic: str,
    period_s: float = DEFAULT_PERIOD_S,
) -> None:
    """Publish a snapshot every `period_s` seconds. Runs forever; cancel
    the task to stop. Publish is retained so a subscriber that joins late
    immediately sees the current picture."""
    topic = f"{base_topic}/{SNAPSHOT_SUFFIX}"
    while True:
        try:
            snapshot = build_snapshot(scheduler, controller)
            controller.client.publish(topic, json.dumps(snapshot, default=str), retain=True)
        except Exception as exc:
            print(f"[snapshot] publish failed: {exc}")
        await asyncio.sleep(period_s)
