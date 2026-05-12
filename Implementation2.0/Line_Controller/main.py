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

# Make the shared ClassesAndBuilderMethods importable. Use insert(0, ...) so
# our project root wins over whatever cwd / PYTHONPATH happen to be.
_IMPL_DIR = str(Path(__file__).resolve().parent.parent)
if _IMPL_DIR not in sys.path:
    sys.path.insert(0, _IMPL_DIR)

from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS

from workorder_handler import WorkOrderHandler
from resource_manager import ResourceManager, make_state_handler
from capability_matcher import CapabilityMatcher
from MQTTClientControllerV2 import MQTTClientController
from transport_planner import TransportPlanner, load_line_config_from_file
from pre_process_planner import PreProcessPlanner
from job_tracker import JobTracker
from inventory_manager import InventoryManager
from occupancy_manager import OccupancyManager
from scheduler import Scheduler


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
WORKORDER_PATH = SCRIPT_DIR / "WorkOrderExampleComplex.json"
LINE_CONFIG_PATH = (
    SCRIPT_DIR.parent
    / "ProductAndResourceImplementations"
    / "ProductionLine1"
    / "LineConfiguration.json"
)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    # Load work order
    print(f"[init] loading work order from {WORKORDER_PATH.name}")
    with open(WORKORDER_PATH) as f:
        order = json.load(f)
    handler = WorkOrderHandler()
    handler.load_workorder(order)
    handler.print_process_list()

    # AAS-driven resource discovery
    rm = ResourceManager(MQTT_PORT, BASE_TOPIC, AAS_BROKER, AAS_PORT, RESOURCE_URL)
    rm.update_resource_availablility()
    matcher = CapabilityMatcher(rm)

    # Planners
    line_config = load_line_config_from_file(LINE_CONFIG_PATH)
    transport_planner = TransportPlanner(line_config)
    pre_process_planner = PreProcessPlanner(transport_planner)
    print(f"[init] line resources in config: {list(line_config.locations)}")

    # Runtime managers
    job_tracker = JobTracker()
    inventory = InventoryManager()

    # MQTT controller + handlers (occupancy needs the controller to publish)
    controller = MQTTClientController(BROKER, MQTT_PORT, CLIENT_ID, BASE_TOPIC, rm)
    controller.register_handler(MS.StateMessage, make_state_handler(rm))
    controller.register_handler(MS.JobResultMessage, job_tracker.make_handler())
    controller.register_handler(MS.InventoryLevelMessage, inventory.make_handler())
    controller.start_mqtt_connection()
    await asyncio.sleep(2)  # let on_connect run update_information() + subscribe

    occupancy = OccupancyManager(controller=controller, base_topic=BASE_TOPIC)

    # Drive the order
    scheduler = Scheduler(
        controller=controller,
        resource_manager=rm,
        matcher=matcher,
        pre_process_planner=pre_process_planner,
        transport_planner=transport_planner,
        job_tracker=job_tracker,
        inventory=inventory,
        occupancy=occupancy,
        aas_server_base=AAS_SERVER_BASE,
    )
    await scheduler.run_order(handler)

    print("\n=== Final process list ===")
    handler.print_process_list()

    # Drain trailing State messages before we exit.
    await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
