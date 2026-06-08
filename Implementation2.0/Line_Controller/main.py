"""Line Controller entry point.

All logic lives in dedicated modules; main() just wires them together and
hands a work order to the Scheduler.

PREREQUISITES — start these four resource scripts first (so they upload
their shells/submodels to BaSyx and subscribe to MQTT):
    Implementation2.0/ProductAndResourceImplementations/Drilling_Station/DrillingStationImplementation.py
    Implementation2.0/ProductAndResourceImplementations/Storage_Station/StorageStationImplementation.py
    Implementation2.0/ProductAndResourceImplementations/Transport_Station/TransportStationImplementation.py
    Implementation2.0/ProductAndResourceImplementations/ProductionLine1/ProductionLine1Implementation.py

See ARCHITECTURE.md for what the modules do and how they fit together.
"""

from __future__ import annotations

"""
STEPS TO GO FROM HERE:
1. I Think that this Line Controller Main.py script should be held clean, and all functions should be moved to other scripts and imported. I believe that handle_job_result() and handle_state should be in resource_manager or something else.

2. I need to figure out how this works. It is all kind of overwhelming at the moment, and I need to be able to tell the group what has been added.

3. When a Process from the BoP has been targeted as COMPLETE, the Line Controller should continue to the next step. It should look at the next ready step and generate pre_process_steps if the component is not at the target position and so on.

4. When all steps has been completed in the BoP, the final product should be stored somewhere, or there should at least be taken some kind of action to remove it from the station where the final process is performed, and the workorder should be complete. 

Something we haven't looked into yet is that when a process has been performed, before completing the task, the AAS instance of the product should be updated with a component reference to the specifically used component/ingredient in that process for tracability. 

Also, we haven't yet figured out how it would handle multiple orders at the same time (thinking about scaling the production line to use many resources with more storage stations, drilling and so on.)

The pre_process_steps should also be defined in a way that are modular, so that when a new process is to be performed, then it must figure out where the required component is stored, and if it is not at the station, it must figure out the steps needed to get it to the station, and if handoff is required. Where would be the best place to define this? Maybe it should just be those predefined steps actually, I can't really imagine if they are different for assembly stations, since they would require multiple components?

"""


import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Make the shared ClassesAndBuilderMethods importable. Use insert(0, ...) so
# our project root wins over whatever cwd / PYTHONPATH happen to be.
_IMPL_DIR = str(Path(__file__).resolve().parent.parent)
if _IMPL_DIR not in sys.path:
    sys.path.insert(0, _IMPL_DIR)

from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS

from workorder_handler import WorkOrderHandler
from resource_manager import ResourceManager
from capability_matcher import CapabilityMatcher
from MQTTClientControllerV2 import MQTTClientController
from controller_alarms import ControllerAlarmPublisher
from order_recovery import OrderRecovery
from transport_planner import TransportPlanner, load_line_config_from_aas
from pre_process_planner import PreProcessPlanner
from job_tracker import JobTracker
from occupancy_manager import OccupancyManager
from product_property_matcher import ProductMatcher
from scheduler import Scheduler
from orchestration_snapshot import run_snapshot_publisher


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

BROKER = "localhost"
MQTT_PORT = 1883
BASE_TOPIC = "AAUSmartLab/ProductionLine1"
CLIENT_ID = "LineController"

AAS_BROKER = "localhost"
AAS_PORT = "8081"
AAS_SERVER_BASE = f"http://{AAS_BROKER}:{AAS_PORT}"
RESOURCE_URL = "https://aausmartlab.org/Shells/Resources"

SCRIPT_DIR = Path(__file__).resolve().parent
# WORKORDER_PATH = SCRIPT_DIR / "WorkOrderExampleComplex.json"
# WORKORDER_PATH = SCRIPT_DIR / "WorkOrderExampleComplex-Jeppes_Bærbar.json"
# WORKORDER_PATH = SCRIPT_DIR / "CorrectWorkorder.json"
WORKORDER_PATH = SCRIPT_DIR / "WorkOrder.json"
# If True, load WORKORDER_PATH once at startup and submit it as the first
# order. Useful for dev/testing without an active MES. Live MES orders on
# MES_TOPIC are accepted in either mode.
SUBMIT_FILE_ON_STARTUP = False

# MES publishes new work orders here. The payload is the workorder JSON
# (same schema as the local *.json files).
MES_TOPIC = "AAUSmartLab/ProductionLine1/MES/WorkOrder"

# The ProductionLine shell on the AAS server is the source of truth for the
# line configuration. The local LineConfiguration.json is no longer read.
LINE_SHELL_PREFIX = "https://aausmartlab.org/Shells/Resources/ProductionLine/"

# ─────────────────────────────────────────────────────────────────────────────
# Message Handlers
#
# Flat V2-style handlers. Each takes (controller, message, topic_info) and
# writes into controller.shared_handler_variable. Layout after a run:
#   {
#     "state":      {shell_iri: {actor: PackMLState}},
#     "inventory":  {shell_iri: {inventory_name: InventoryData}},
#     "job_result": {shell_iri: {actor: JobResultMessage}},
#   }
#
# Other modules read from there:
#   - JobTracker.wait_for(job_id) scans "job_result"
#   - Scheduler's wait_for_idle reads "state"
#   - ProductMatcher's index is rebuilt from "inventory" inside the handler
# ─────────────────────────────────────────────────────────────────────────────

# Module-level ProductMatcher — initialized in main(), referenced by the
# inventory handler. Same pattern as MQTTClientControllerV2 keeps `pm` global.
_product_matcher: ProductMatcher | None = None


def handle_state_message(controller: MQTTClientController, message, topic_info):
    resource_suffix = topic_info["resource_suffix"]
    actor_id = topic_info.get("actor_id", "default")
    resource_shell_id = controller.topic_to_shell_id[resource_suffix]

    # Reachability + last_seen go onto the controller/RM directly.
    controller.RM.resource_shell_ids[resource_shell_id] = controller.classify_reachability(message)
    controller.last_seen[resource_suffix] = datetime.now()

    # Per-actor PackML state lives in the shared dict.
    state_store = controller.shared_handler_variable.setdefault("state", {})
    state_store.setdefault(resource_shell_id, {})[actor_id] = message.state

    state_str = message.state.value if hasattr(message.state, "value") else str(message.state)
    print(f"[STATE]     {resource_suffix}/{actor_id} -> {state_str}")


def handle_job_result_message(controller: MQTTClientController, message, topic_info):
    resource_suffix = topic_info["resource_suffix"]
    actor_id = topic_info.get("actor_id", "default")
    resource_shell_id = controller.topic_to_shell_id[resource_suffix]

    job_store = controller.shared_handler_variable.setdefault("job_result", {})
    job_store.setdefault(resource_shell_id, {})[actor_id] = message

    print(
        f"[JOBRESULT] {message.job_id}  result={message.result.value} "
        f"quality={message.quality.value}"
    )


def handle_inventory_level_message(controller: MQTTClientController, message, topic_info):
    resource_suffix = topic_info["resource_suffix"]
    resource_shell_id = controller.topic_to_shell_id[resource_suffix]

    inv_store = controller.shared_handler_variable.setdefault("inventory", {})
    inv_store[resource_shell_id] = message.inventory

    # Keep the ProductMatcher index fresh.
    if _product_matcher is not None:
        _product_matcher.inventory_indexer.rebuild_index(inv_store)

    print(f"[INVENTORY] {resource_suffix} updated")


def handle_occupancy_message(controller: MQTTClientController, message, topic_info):
    """Mirror the controller's own OccupancyMessage broadcasts into the
    shared dict so observers can read the per-actor occupation map.

    Layout:  shared_handler_variable["occupancy"][shell_iri][actor] = OccupancyMessage
    """
    resource_suffix = topic_info["resource_suffix"]
    actor_id = topic_info.get("actor_id", "default")
    resource_shell_id = controller.topic_to_shell_id[resource_suffix]

    occ_store = controller.shared_handler_variable.setdefault("occupancy", {})
    occ_store.setdefault(resource_shell_id, {})[actor_id] = message

    print(
        f"[OCCUPANCY] {resource_suffix}/{actor_id} occupied={message.occupied} "
        f"job_id={message.job_id}"
    )


def handle_cargo_message(controller: MQTTClientController, message, topic_info):
    """Mirror CargoMessage broadcasts into the shared dict.

    Layout:  shared_handler_variable["cargo"][shell_iri][actor] = component_reference (str or None)
    """
    resource_suffix = topic_info["resource_suffix"]
    actor_id = topic_info.get("actor_id", "default")
    resource_shell_id = controller.topic_to_shell_id[resource_suffix]

    cargo_store = controller.shared_handler_variable.setdefault("cargo", {})
    cargo_store.setdefault(resource_shell_id, {})[actor_id] = message.component_reference

    print(
        f"[CARGO]     {resource_suffix}/{actor_id} -> "
        f"{message.component_reference or '(empty)'}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    global _product_matcher

    # Load line config first so we can filter resource discovery to only the
    # resources actually configured on this line (skips template shells).
    # Source of truth is the ProductionLine shell on the AAS server.
    line_config = load_line_config_from_aas(AAS_SERVER_BASE, LINE_SHELL_PREFIX)
    transport_planner = TransportPlanner(line_config)
    pre_process_planner = PreProcessPlanner(transport_planner)
    print(f"[init] line resources in config: {list(line_config.locations)}")

    # AAS-driven resource discovery, filtered by the line config.
    rm = ResourceManager(MQTT_PORT, BASE_TOPIC, AAS_BROKER, AAS_PORT, RESOURCE_URL)
    rm.update_resource_availablility(
        allowed_iris={loc.resource_iri for loc in line_config.locations.values()}
    )
    matcher = CapabilityMatcher(rm)

    # ProductMatcher — module-level so the flat inventory handler can refresh it.
    _product_matcher = ProductMatcher(AAS_BROKER, AAS_PORT)

    # MQTT controller + flat V2 handlers
    controller = MQTTClientController(BROKER, MQTT_PORT, CLIENT_ID, BASE_TOPIC, rm)
    controller.register_handler(MS.StateMessage, handle_state_message)
    controller.register_handler(MS.JobResultMessage, handle_job_result_message)
    controller.register_handler(MS.InventoryLevelMessage, handle_inventory_level_message)
    controller.register_handler(MS.OccupancyMessage, handle_occupancy_message)
    controller.register_handler(MS.CargoMessage, handle_cargo_message)
    controller.start_mqtt_connection()
    await asyncio.sleep(2)  # let on_connect run update_information() + subscribe

    # Hand the controller the running loop so its CMD ACK handler (which
    # fires on paho's MQTT thread) can resolve asyncio futures safely.
    controller.set_event_loop(asyncio.get_running_loop())

    # Attach the controller-side alarm publisher so RR-related failures
    # (CMD_NO_ACK, RESOURCE_OFFLINE, NO_ALTERNATIVE, ...) reach the MES
    # via AAUSmartLab/<line_id>/Controller/Alarms.
    controller.alarm_publisher = ControllerAlarmPublisher(controller)

    # Runtime managers that need the controller
    job_tracker = JobTracker(controller)
    occupancy = OccupancyManager(controller=controller, base_topic=BASE_TOPIC)

    # Per-process queue of incoming work orders. The MES subscription drops
    # WorkOrder dicts onto this queue from paho's network thread; the main
    # async loop drains it.
    loop = asyncio.get_running_loop()
    order_queue: asyncio.Queue[dict] = asyncio.Queue()

    def on_mes_workorder(client, userdata, msg):
        try:
            order = json.loads(msg.payload.decode())
        except json.JSONDecodeError as exc:
            print(f"[MES] malformed WorkOrder payload: {exc}")
            return
        order_id = order.get("OrderId", "<unknown>")
        print(f"[MES] received WorkOrder {order_id}")
        # paho callbacks fire on the MQTT network thread; bounce into the
        # asyncio loop before touching the queue.
        loop.call_soon_threadsafe(order_queue.put_nowait, order)

    controller.client.message_callback_add(MES_TOPIC, on_mes_workorder)
    # QoS 1 + persistent session (set in MQTTClientControllerV2.__init__)
    # is what makes the broker queue WorkOrders for us while we're offline.
    controller.client.subscribe(MES_TOPIC, qos=1)
    print(f"[init] subscribed to MES topic: {MES_TOPIC}")

    # Optional dev convenience: submit a local file as the first order.
    if SUBMIT_FILE_ON_STARTUP and WORKORDER_PATH.exists():
        print(f"[init] loading work order from {WORKORDER_PATH.name}")
        with open(WORKORDER_PATH) as f:
            order_queue.put_nowait(json.load(f))

    # Recovery owns restart vs abort decisions on detectable failures.
    recovery = OrderRecovery(
        capability_matcher=matcher,
        occupancy=occupancy,
        alarm_publisher=controller.alarm_publisher,
    )

    # Single scheduler shared across all orders.
    scheduler = Scheduler(
        controller=controller,
        resource_manager=rm,
        matcher=matcher,
        pre_process_planner=pre_process_planner,
        transport_planner=transport_planner,
        job_tracker=job_tracker,
        product_matcher=_product_matcher,
        occupancy=occupancy,
        aas_server_base=AAS_SERVER_BASE,
        recovery=recovery,
    )

    # Operator clear-stuck-cargo: publish
    #   { "resource_id": "...", "actor_name": "..." }
    # to AAUSmartLab/<line>/Controller/ClearStuckCargo to free a stuck
    # actor after the physical part has been removed.
    CLEAR_STUCK_TOPIC = f"{BASE_TOPIC}/Controller/ClearStuckCargo"

    def on_clear_stuck(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            resource_id = payload["resource_id"]
            actor_name = payload["actor_name"]
        except (json.JSONDecodeError, KeyError) as exc:
            print(f"[ClearStuckCargo] malformed payload: {exc}")
            return
        cleared = occupancy.clear_stuck(resource_id, actor_name)
        if cleared and controller.alarm_publisher is not None:
            controller.alarm_publisher.clear(
                category=MS.AlarmCategory.STUCK_CARGO,
                resource_id=resource_id,
                message=f"{resource_id}/{actor_name} cleared by operator",
            )

    controller.client.message_callback_add(CLEAR_STUCK_TOPIC, on_clear_stuck)
    controller.client.subscribe(CLEAR_STUCK_TOPIC)
    print(f"[init] subscribed to operator topic: {CLEAR_STUCK_TOPIC}")

    # Periodic orchestration snapshot for the MES Production Monitoring UI.
    # Retained publish so a late-joining subscriber sees the current picture.
    asyncio.create_task(run_snapshot_publisher(scheduler, controller, BASE_TOPIC))
    print(f"[init] orchestration snapshot publisher running -> "
          f"{BASE_TOPIC}/Orchestration/Snapshot")

    print("[init] waiting for work orders on MQTT…")

    async def _run_one(order: dict) -> None:
        handler = WorkOrderHandler()
        handler.load_workorder(order)
        order_id = order.get("OrderId", "<unknown>")
        print(f"\n[ingest] starting work order {order_id}")
        handler.print_process_list()
        try:
            await scheduler.run_order(handler)
        except Exception as exc:
            print(f"[ingest] order {order_id} failed: {exc}")
            return
        print(f"\n=== Final process list for {order_id} ===")
        handler.print_process_list()

    # Drain the queue and spawn each order concurrently. Multiple orders run
    # in parallel; OccupancyManager + Scheduler's instance reservations
    # prevent them from double-booking shuttles, actors, or inventory items.
    while True:
        order = await order_queue.get()
        asyncio.create_task(_run_one(order))


if __name__ == "__main__":
    asyncio.run(main())
