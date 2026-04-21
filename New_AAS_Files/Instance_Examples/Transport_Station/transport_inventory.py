import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from BaSyx_AAS_Generator.instance_generator_class import AASInstanceBuilder



TransportStationInventory = AASInstanceBuilder(
        "Inventory",
        "https://aausmartlab.org/Shells/Resources/Transport-12345678/Inventory"
    )

root = TransportStationInventory.get()

inventory_1 = TransportStationInventory.add_collection(
    root,
    "Inventory1"
)

inventory_1_specifications = TransportStationInventory.add_collection(
    inventory_1,
    "Specifications"
)

TransportStationInventory.add_property(
    inventory_1_specifications,
    "InventorySize",
    "xs:integer",
    0
)

supported_components = TransportStationInventory.add_collection(
    inventory_1,
    "Supported_Components",
)


