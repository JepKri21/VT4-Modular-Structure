import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from BaSyx_AAS_Generator.instance_generator_class import AASInstanceBuilder



DrillingStationInventory = AASInstanceBuilder(
        "Inventory",
        "https://aausmartlab.org/Shells/Resources/Drilling-12345678/Inventory"
    )

root = DrillingStationInventory.get()

inventory_1 = DrillingStationInventory.add_collection(
    root,
    "Inventory1"
)

inventory_1_specifications = DrillingStationInventory.add_collection(
    inventory_1,
    "Specifications"
)

DrillingStationInventory.add_property(
    inventory_1_specifications,
    "InventorySize",
    "xs:integer",
    0
)

supported_components = DrillingStationInventory.add_collection(
    inventory_1,
    "Supported_Components",
)


