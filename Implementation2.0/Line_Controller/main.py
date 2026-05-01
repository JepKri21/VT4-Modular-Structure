from workorder_handler import WorkOrderHandler
from resource_manager import ResourceManager
from capability_matcher import CapabilityMatcher

import json
from pathlib import Path

def main():

    # 1 Load Workorder from MES:
    script_dir = Path(__file__).parent
    file_path = script_dir / "WorkOrderExampleComplex.json"

    with open(file_path) as f:
        order = json.load(f)

    handler = WorkOrderHandler()
    handler.load_workorder(order)

    # 2 Get resources
    # EXAMPLE RESOURCE FOR NOW: 
    # Should also be matched on if required_capability == offered_capability["semanticId"]:
    resources = [
    {
        "id": "Drill_1",
        "capabilities": [
            "https://aausmartlab.org/Submodels/Capability/Drilling"
        ]
    },
    {
        "id": "Assembler_1",
        "capabilities": [
            "https://aausmartlab.org/Submodels/Capability/Assemble"
        ]
    }
]
    resource_manager = ResourceManager(resources)
    matcher = CapabilityMatcher(resource_manager)

    # 3 Get the ready process steps
    ready_steps = handler.get_ready_steps()

    # 4 print the matches that can handle capability
    print("\n=== MATCHING RESULTS ===")

    for step in ready_steps:

        info = handler.get_step_execution_info(step["step_id"])

        capability = info["CapabilityReference"]   # ✔ correct key
        params = info["Parameters"]

        print(f"\nStep: {step['step_id']}")
        print(f"Required capability: {capability}")

        # OPTION A (simple direct matching)
        matches = resource_manager.find_by_capability(capability)

        # OPTION B (future proper matcher)
        # matches = matcher.match(step, capability_model)

        if matches:
            for m in matches:
                print(f"→ Match: {m['id']}")
        else:
            print("→ No matching resource")


if __name__ == "__main__":
    main()