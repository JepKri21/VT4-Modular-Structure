import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from BaSyx_AAS_Generator.instance_generator_class import AASInstanceBuilder



StorageStationInventory = AASInstanceBuilder(
        "Inventory",
        "https://aausmartlab.org/Shells/Resources/Storage-12345678/Inventory"
    )

root = StorageStationInventory.get()

#================================ Inventory 1 ===================================


inventory_1 = StorageStationInventory.add_collection(
    root,
    "Inventory1"
)

inventory_1_specifications = StorageStationInventory.add_collection(
    inventory_1,
    "Specifications"
)

StorageStationInventory.add_property(
    inventory_1_specifications,
    "InventorySize",
    "xs:integer",
    10
)

inventory_1_supported_components = StorageStationInventory.add_collection(
    inventory_1,
    "Supported_Components",
)


StorageStationInventory.add_property(
    inventory_1_supported_components,
    "Component1",
    "xs:string",
    "Bottom_Cover"    
)


#================================ Inventory 1 ===================================


inventory_2 = StorageStationInventory.add_collection(
    root,
    "Inventory2"
)

inventory_2_specifications = StorageStationInventory.add_collection(
    inventory_2,
    "Specifications"
)

StorageStationInventory.add_property(
    inventory_2_specifications,
    "InventorySize",
    "xs:integer",
    10
)

inventory_2_supported_components = StorageStationInventory.add_collection(
    inventory_2,
    "Supported_Components",
)


StorageStationInventory.add_property(
    inventory_2_supported_components,
    "Component1",
    "xs:string",
    "Bottom_Cover_Drilled"
)
