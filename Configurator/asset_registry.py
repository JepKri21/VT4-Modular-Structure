"""
Shared Asset Registry — single source of truth for all product/component configurations.

Imported by configurator_v4.py, inventory_db.py, and assembly_manager_v4.py so that
adding or modifying a product only requires editing this one file.

Fields per entry:
  is_component          : True = physical inventory component, False = sub-assembly / final product
  type_shell            : relative path to the type shell JSON (from AAS_FILES_BASE)
  type_submodels_dir    : relative dir containing type submodel JSONs
  type_submodel_prefix  : filename prefix for type submodels
  instance_shell_dir    : relative dir for instance shell JSONs
  instance_submodels_dir: relative dir for instance submodel JSONs
  instance_file_prefix  : filename prefix for instance files
  registry_key          : key used in inventory_db REGISTRY_KEY_TO_TYPE_DOC
  submodels             : list of submodel names to create per instance
  properties_config_map : {AAS Property idShort → order config key}
                          used to fill Properties submodel values and derive required fields
  static_properties     : {AAS Property idShort → fixed value}  (optional)
  quantity_config_key   : order config key that controls how many instances to reserve
                          (optional; only on variable-quantity components like Fuse)
  options_count_key     : output key name for _get_available_options() count dict
                          (optional; only on quantity_config_key components)
"""

from typing import Any, Dict, List

ASSET_REGISTRY: Dict[str, Dict[str, Any]] = {
    "Bottom_Cover": {
        "is_component": True,
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-Bottom_Cover-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels",
        "type_submodel_prefix": "Product-Component-AAU-Bottom_Cover",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Component_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Component_Instance_Submodels",
        "instance_file_prefix": "Product-Component-AAU-Bottom_Cover",
        "registry_key": "Bottom_Cover",
        "submodels": ["Properties", "Documentation", "Bill_Of_Processes"],
        "properties_config_map": {
            "Material": "bottom_cover_material",
            "Color": "bottom_cover_color",
            "Finish": "bottom_cover_finish",
        },
    },
    "Top_Cover": {
        "is_component": True,
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-Top_Cover-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels",
        "type_submodel_prefix": "Product-Component-AAU-Top_Cover",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Component_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Component_Instance_Submodels",
        "instance_file_prefix": "Product-Component-AAU-Top_Cover",
        "registry_key": "Top_Cover",
        "submodels": ["Properties", "Documentation", "Bill_Of_Processes"],
        "properties_config_map": {
            "Material": "top_cover_material",
            "Color": "top_cover_color",
            "Finish": "top_cover_finish",
        },
    },
    "PCB": {
        "is_component": True,
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-PCB-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels",
        "type_submodel_prefix": "Product-Component-AAU-PCB",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Component_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Component_Instance_Submodels",
        "instance_file_prefix": "Product-Component-AAU-PCB",
        "registry_key": "PCB",
        "submodels": ["Properties", "Documentation", "Bill_Of_Processes"],
        "properties_config_map": {},
    },
    "Fuse": {
        "is_component": True,
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-Fuse-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels",
        "type_submodel_prefix": "Product-Component-AAU-Fuse",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Component_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Component_Instance_Submodels",
        "instance_file_prefix": "Product-Component-AAU-Fuse",
        "registry_key": "Fuse",
        "submodels": ["Properties", "Documentation", "Bill_Of_Processes"],
        "properties_config_map": {},
        # How many of this component to reserve per order (driven by a config field).
        "quantity_config_key": "number_of_fuses",
        # Output key name in _get_available_options() for the count options.
        "options_count_key": "fuse_counts",
    },
    "Bottom_Cover-PCB-Fuse": {
        "is_component": False,
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Sub_Assembly_Types/Product-Sub_Assembly-AAU-Bottom_Cover-PCB-Fuse-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Sub_Assembly_Type_Submodels",
        "type_submodel_prefix": "Product-Sub_Assembly-AAU-Bottom_Cover-PCB-Fuse",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Sub_Assembly_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Sub_Assembly_Instance_Submodels",
        "instance_file_prefix": "Product-Sub_Assembly-AAU-Bottom_Cover-PCB-Fuse",
        "registry_key": "Bottom_Cover-PCB-Fuse",
        "submodels": ["Properties", "Documentation", "Bill_Of_Materials", "Bill_Of_Processes"],
        "properties_config_map": {"Nr_Fuses": "number_of_fuses"},
    },
    "Bottom_Cover-PCB": {
        "is_component": False,
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Sub_Assembly_Types/Product-Sub_Assembly-AAU-Bottom_Cover-PCB-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Sub_Assembly_Type_Submodels",
        "type_submodel_prefix": "Product-Sub_Assembly-AAU-Bottom_Cover-PCB",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Sub_Assembly_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Sub_Assembly_Instance_Submodels",
        "instance_file_prefix": "Product-Sub_Assembly-AAU-Bottom_Cover-PCB",
        "registry_key": "Bottom_Cover-PCB",
        "submodels": ["Properties", "Documentation", "Bill_Of_Materials", "Bill_Of_Processes"],
        "properties_config_map": {
            "Material": "bottom_cover_material",
            "Color": "bottom_cover_color",
            "Finish": "bottom_cover_finish",
            "Nr_Fuses": "number_of_fuses",
        },
    },
    "Telefon": {
        "is_component": False,
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Final_Product_Types/Product-Final_Product-AAU-Telefon-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Final_Product_Type_Submodels",
        "type_submodel_prefix": "Product-Final_Product-Telefon-Telefon_Pro_Max",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Final_Product_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Final_Product_Instance_Submodels",
        "instance_file_prefix": "Product-Final_Product-Telefon-Telefon_Pro_Max",
        "registry_key": "Telefon_Pro_Max",
        "submodels": ["Properties", "Documentation", "Bill_Of_Materials", "Bill_Of_Processes"],
        "properties_config_map": {
            "Material": "bottom_cover_material",
            "Color": "bottom_cover_color",
            "Nr_Fuses": "number_of_fuses",
        },
        "static_properties": {
            "Length": "150",
            "Width": "70",
            "Height": "10",
        },
    },
}

# Which asset keys get shells created at order time (sub-assemblies + final product).
# Components are pre-existing inventory; only model-type reservations are created.
ORDER_TIME_SHELL_KEYS: List[str] = ["Bottom_Cover-PCB", "Bottom_Cover-PCB-Fuse", "Telefon"]
