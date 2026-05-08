from workorder_handler import WorkOrderHandler, StepStates
from resource_manager import ResourceManager
from capability_matcher import CapabilityMatcher

import json
from pathlib import Path


AAS_BROKER = "localhost"
AAS_PORT = "8081"
MQTT_PORT = 1883
BASE_TOPIC = "AAUSmartLab/ProductionLine1"
RESOURCE_URL = "https://aausmartlab.org/Shells/Resources"


def main():

    # 1 Load Workorder from MES
    script_dir = Path(__file__).parent
    file_path = script_dir / "WorkOrderExampleComplex.json"

    with open(file_path) as f:
        order = json.load(f)

    handler = WorkOrderHandler()
    handler.load_workorder(order)

    # 2 Resource manager + matcher (resource manager pulls live shells from the AAS server)
    resource_manager = ResourceManager(MQTT_PORT, BASE_TOPIC, AAS_BROKER, AAS_PORT, RESOURCE_URL)
    resource_manager.update_resource_availablility()
    matcher = CapabilityMatcher(resource_manager)

    # 3 Get the ready process steps
    ready_steps = handler.get_ready_steps()

    # 4 Match each step to viable resources, then pick first available
    print("\n=== MATCHING RESULTS ===")

    for step in ready_steps:

        info = handler.get_step_execution_info(step["step_id"])

        print(f"\nStep: {step['step_id']}")
        print(f"  Capability:     {info['CapabilityReference']}")
        print(f"  Component:      {info['ComponentReference']}")
        print(f"  Material:       {info['Material']}")

        candidates = matcher.match(info)

        if not candidates:
            print("  -> No matching resource")
            continue

        for c in candidates:
            print(f"  -> Candidate: {c['resource_id']}  (skill: {c['skill_name']})")

        # First-match scheduling for now; will move into scheduler.py later.
        chosen = candidates[0]
        handler.update_step(step["step_id"], "ASSIGNED", resource=chosen["resource_id"])
        print(f"  >> Assigned to: {chosen['resource_id']}")

    # Simulate a step to be complete
    handler.update_step("1x1", StepStates.COMPLETED)

    # Read the new and updated step
    ready_steps = handler.get_ready_steps()

    for step in ready_steps:

        info = handler.get_step_execution_info(step["step_id"])

        print(f"\nStep: {step['step_id']}")
        print(f"  Capability:     {info['CapabilityReference']}")
        print(f"  Component:      {info['ComponentReference']}")
        print(f"  Material:       {info['Material']}")

        candidates = matcher.match(info)

        if not candidates:
            print("  -> No matching resource")
            continue

        for c in candidates:
            print(f"  -> Candidate: {c['resource_id']}  (skill: {c['skill_name']})")

        # First-match scheduling for now; will move into scheduler.py later.
        chosen = candidates[0]
        handler.update_step(step["step_id"], "ASSIGNED", resource=chosen["resource_id"])
        print(f"  >> Assigned to: {chosen['resource_id']}")

if __name__ == "__main__":
    main()
