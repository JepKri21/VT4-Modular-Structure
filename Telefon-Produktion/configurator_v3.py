"""
Telefon Product Configurator v3

Template-driven with inventory management: extends v2 by integrating
SQL-based inventory tracking. The configurator now:
  1. Checks inventory before allowing configurations
  2. Only permits component variants that have stock
  3. Deducts from inventory when instances are created
  4. Provides inventory status and warnings

Template-driven: all instance file layouts are defined entirely in the Type
JSON files. The configurator loads a Type file, deep-copies it, and patches
only the fields that differ per instance (IDs, configured property values,
configurable BOM quantities, etc.).

Adding / removing a property, BOM component, or process step in a Type file
automatically flows through to every newly generated instance — no code
changes needed.
"""

import json
import copy
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from inventory_db import InventoryDatabase, ComponentInventory


# =============================================================================
# Asset Type Registry
#
# Each entry describes ONE product type and tells the configurator:
#   type_shell              – relative path to the Type AAS shell
#   type_submodels_dir      – relative dir containing the Type submodel files
#   type_submodel_prefix    – filename part before  "-Type-{Submodel}.json"
#   instance_shell_dir      – output dir for instance AAS shells
#   instance_submodels_dir  – output dir for instance submodel files
#   instance_file_prefix    – filename part before  "-{num}-{Submodel}.json"
#   registry_key            – key used in instance_registry.json
#   submodels               – ordered list of submodels to generate
#   properties_config_map   – {Property_idShort: config_dict_key}
#   bom_dynamic_quantities  – {BOM_component_idShort: config_dict_key}
#   inventory_id            – component ID used in inventory DB
#
# To add a new product type: add one entry here and create the matching Type
# JSON files. No other code changes are required.
# =============================================================================

ASSET_REGISTRY: Dict[str, Dict[str, Any]] = {
    "Bottom_Cover": {
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-Bottom_Cover-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels",
        "type_submodel_prefix": "Product-Component-AAU-Bottom_Cover",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Component_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Component_Instance_Submodels",
        "instance_file_prefix": "Product-Component-AAU-Bottom_Cover",
        "registry_key": "Bottom_Cover",
        "inventory_id": "Bottom_Cover",
        "submodels": ["Properties", "Documentation", "Bill_Of_Processes"],
        "properties_config_map": {
            "Material": "bottom_cover_material",
            "Color":    "bottom_cover_color",
            "Finish":   "bottom_cover_finish",
        },
        "bom_dynamic_quantities": {},
    },
    "Top_Cover": {
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-Top_Cover-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels",
        "type_submodel_prefix": "Product-Component-AAU-Top_Cover",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Component_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Component_Instance_Submodels",
        "instance_file_prefix": "Product-Component-AAU-Top_Cover",
        "registry_key": "Top_Cover",
        "inventory_id": "Top_Cover",
        "submodels": ["Properties", "Documentation", "Bill_Of_Processes"],
        "properties_config_map": {
            "Material": "top_cover_material",
            "Color":    "top_cover_color",
            "Finish":   "top_cover_finish",
        },
        "bom_dynamic_quantities": {},
    },
    "PCB": {
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-PCB-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels",
        "type_submodel_prefix": "Product-Component-AAU-PCB",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Component_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Component_Instance_Submodels",
        "instance_file_prefix": "Product-Component-AAU-PCB",
        "registry_key": "PCB",
        "inventory_id": "PCB",
        "submodels": ["Properties", "Documentation", "Bill_Of_Processes"],
        "properties_config_map": {},
        "bom_dynamic_quantities": {},
    },
    "Fuse": {
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-Fuse-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels",
        "type_submodel_prefix": "Product-Component-AAU-Fuse",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Component_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Component_Instance_Submodels",
        "instance_file_prefix": "Product-Component-AAU-Fuse",
        "registry_key": "Fuse",
        "inventory_id": "Fuse",
        "submodels": ["Properties", "Documentation", "Bill_Of_Processes"],
        "properties_config_map": {},
        "bom_dynamic_quantities": {},
    },
    "PCB_With_Fuse": {
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Sub_Assembly_Types/Product-Sub_Assembly-AAU-PCB_With_Fuse-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Sub_Assembly_Type_Submodels",
        "type_submodel_prefix": "Product-Sub_Assembly-AAU-PCB_With_Fuse",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Sub_Assembly_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Sub_Assembly_Instance_Submodels",
        "instance_file_prefix": "Product-Sub_Assembly-AAU-PCB_With_Fuse",
        "registry_key": "PCB_With_Fuse",
        "inventory_id": "PCB_With_Fuse",
        "submodels": ["Properties", "Documentation", "Bill_Of_Materials", "Bill_Of_Processes"],
        "properties_config_map": {
            "Nr_Fuses": "number_of_fuses",
        },
        "bom_dynamic_quantities": {
            "Fuse": "number_of_fuses",
        },
    },
    "Housing_With_PCB": {
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Sub_Assembly_Types/Product-Sub_Assembly-AAU-Housing_With_PCB-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Sub_Assembly_Type_Submodels",
        "type_submodel_prefix": "Product-Sub_Assembly-AAU-Housing_With_PCB",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Sub_Assembly_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Sub_Assembly_Instance_Submodels",
        "instance_file_prefix": "Product-Sub_Assembly-AAU-Housing_With_PCB",
        "registry_key": "Housing_With_PCB",
        "inventory_id": "Housing_With_PCB",
        "submodels": ["Properties", "Documentation", "Bill_Of_Materials", "Bill_Of_Processes"],
        "properties_config_map": {
            "Material":  "bottom_cover_material",
            "Color":     "bottom_cover_color",
            "Finish":    "bottom_cover_finish",
            "Nr_Fuses":  "number_of_fuses",
        },
        "bom_dynamic_quantities": {},
    },
    "Telefon": {
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Final_Product_Types/Product-Final_Product-AAU-Telefon-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Final_Product_Type_Submodels",
        "type_submodel_prefix": "Product-Final_Product-Telefon-Telefon_Pro_Max",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Final_Product_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Final_Product_Instance_Submodels",
        "instance_file_prefix": "Product-Final_Product-Telefon-Telefon_Pro_Max",
        "registry_key": "Telefon_Pro_Max",
        "inventory_id": "Telefon",
        "submodels": ["Properties", "Documentation", "Bill_Of_Materials", "Bill_Of_Processes"],
        "properties_config_map": {
            "Material":  "bottom_cover_material",
            "Color":     "bottom_cover_color",
            "Nr_Fuses":  "number_of_fuses",
        },
        "bom_dynamic_quantities": {},
    },
}


# =============================================================================
# Configurator class with Inventory Management
# =============================================================================

class TelefonConfiguratorV3:
    """
    Template-driven Telefon configurator with inventory management.

    Extends v2 by integrating SQL-based inventory tracking. The configurator
    now checks inventory availability before creating instances and deducts
    from inventory when instances are created.
    """

    def __init__(self, base_path: str, db_path: Optional[str] = None):
        self.base_path = Path(base_path)
        self.registry_path = self.base_path / "instance_registry.json"
        self.config_template_path = (
            self.base_path
            / "JSON_Submodels"
            / "Product_Submodels_JSON"
            / "Final_Product_Submodels"
            / "Product-Final_Product-Telefon-Telefon_Pro_Max-Configuration_Template.json"
        )
        
        # Initialize inventory database
        if db_path is None:
            db_path = str(self.base_path / "inventory.db")
        self.inventory = InventoryDatabase(db_path)
        
        self.registry = self._load_registry()
        self.config_template = self._load_config_template()

    # -------------------------------------------------------------------------
    # File I/O helpers
    # -------------------------------------------------------------------------

    def _load_registry(self) -> Dict[str, Any]:
        with open(self.registry_path, encoding="utf-8") as f:
            return json.load(f)

    def _save_registry(self):
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(self.registry, f, indent=2, ensure_ascii=False)

    def _load_config_template(self) -> Dict[str, Any]:
        with open(self.config_template_path, encoding="utf-8") as f:
            return json.load(f)

    def _load_type_shell(self, asset_key: str) -> Dict[str, Any]:
        """Load the Type AAS shell for the given asset type key."""
        path = self.base_path / ASSET_REGISTRY[asset_key]["type_shell"]
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _load_type_submodel(self, asset_key: str, submodel_name: str) -> Dict[str, Any]:
        """
        Load a Type submodel file by asset key and submodel name.
        Filename convention: {type_submodel_prefix}-Type-{submodel_name}.json
        """
        cfg = ASSET_REGISTRY[asset_key]
        filename = f"{cfg['type_submodel_prefix']}-Type-{submodel_name}.json"
        path = self.base_path / cfg["type_submodels_dir"] / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Type submodel not found: {path}\n"
                f"Expected for asset '{asset_key}', submodel '{submodel_name}'."
            )
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _save_json(self, rel_dir: str, filename: str, data: Dict[str, Any]) -> Path:
        """Write data as JSON to base_path / rel_dir / filename."""
        out_path = self.base_path / rel_dir / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return out_path

    # -------------------------------------------------------------------------
    # Inventory validation methods
    # -------------------------------------------------------------------------

    def _build_variant_spec(self, asset_key: str, config: Dict[str, Any]) -> str:
        """
        Build a variant specification string from configuration values.

        Args:
            asset_key: Component type identifier
            config: Configuration dictionary

        Returns:
            Variant spec string (e.g., "Material: PLA-31212, Color: Red")
        """
        # Special case for Fuses - use standard rating spec
        if asset_key == "Fuse":
            return "Standard Rating"
        
        cfg = ASSET_REGISTRY[asset_key]
        config_map = cfg.get("properties_config_map", {})
        
        parts = []
        for prop_name, config_key in config_map.items():
            value = config.get(config_key)
            if value:
                parts.append(f"{prop_name}: {value}")
        
        return ", ".join(parts) if parts else "Standard Configuration"

    def validate_configuration_availability(
        self, config: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate that all components in the configuration have inventory available.

        Args:
            config: Configuration dictionary

        Returns:
            Tuple of (is_valid: bool, messages: List[str])
        """
        messages = []
        is_valid = True

        # Define which components are used in Telefon configuration
        # This maps configuration keys to component types
        component_checks = [
            ("Bottom_Cover", self._build_variant_spec("Bottom_Cover", config)),
            ("Top_Cover", self._build_variant_spec("Top_Cover", config)),
            ("PCB", self._build_variant_spec("PCB", config)),
        ]

        print("\n🔍 Checking inventory availability...\n")

        for component_id, variant_spec in component_checks:
            available, current_qty = self.inventory.check_availability(
                component_id, variant_spec, required_quantity=1
            )

            if available:
                messages.append(f"  ✓ {component_id}: {current_qty} in stock")
            else:
                messages.append(f"  ❌ {component_id} ({variant_spec}): OUT OF STOCK")
                is_valid = False

        # Check Fuses - need required_quantity of any fuse variant
        num_fuses = config.get("number_of_fuses", 1)
        if num_fuses > 0:
            # For fuses, check if any variant has enough stock
            fuse_variants = self.inventory.get_all_inventory_by_component("Fuse")
            fuse_available = False
            total_fuses_available = 0
            
            for fuse_variant in fuse_variants:
                if fuse_variant.quantity >= num_fuses:
                    fuse_available = True
                    total_fuses_available = max(total_fuses_available, fuse_variant.quantity)
                    break
            
            if fuse_available:
                messages.append(f"  ✓ Fuse: {total_fuses_available} x {num_fuses} needed in stock")
            else:
                messages.append(f"  ❌ Fuse: Cannot find {num_fuses} units of any fuse variant")
                is_valid = False

        for msg in messages:
            print(msg)

        return is_valid, messages

    def get_available_configurations(self) -> Dict[str, List[str]]:
        """
        Get all currently available configuration combinations based on inventory.

        Returns:
            Dictionary mapping component types to available variants
        """
        available = {}

        for component_id in ["Bottom_Cover", "Top_Cover", "PCB", "Fuse"]:
            items = self.inventory.get_all_inventory_by_component(component_id)
            available[component_id] = [
                item.variant_spec for item in items if item.quantity > 0
            ]

        return available

    def print_available_options(self):
        """Print all currently available configuration options."""
        available = self.get_available_configurations()

        print("\n" + "="*80)
        print("📋 AVAILABLE CONFIGURATION OPTIONS (Based on Current Inventory)")
        print("="*80)

        for component_id, variants in available.items():
            print(f"\n{component_id}:")
            if variants:
                for variant in variants:
                    inventory = self.inventory.get_inventory(component_id, variant)
                    qty = inventory.quantity if inventory else 0
                    print(f"  ✓ {variant:<50} | Qty: {qty:>4}")
            else:
                print(f"  ❌ No stock available")

        print("\n" + "="*80 + "\n")

    # -------------------------------------------------------------------------
    # Core transformation: Type JSON  →  Instance JSON
    # -------------------------------------------------------------------------

    def _type_to_instance(self, doc: Dict, instance_num: str) -> Dict:
        """
        Convert a deep-copied Type AAS document to an Instance document.

        All AAS IDs in Type files follow the convention:
            .../ProductName/Type[/SubmodelName]

        This method replaces every occurrence of '/Type/' and '/Type"' in the
        serialised JSON with '/{instance_num}/' and '/{instance_num}"',
        which updates the shell id, globalAssetId, all submodel references,
        and the submodel id itself in one pass.

        The semanticId URLs are never affected because they never contain '/Type/'.
        """
        text = json.dumps(doc)
        text = text.replace("/Type/", f"/{instance_num}/")
        text = text.replace('/Type"', f'/{instance_num}"')
        return json.loads(text)

    def _patch_shell(self, shell: Dict, asset_key: str) -> Dict:
        """
        After _type_to_instance, fix the shell-specific fields:
          - assetKind  : "Type" → "Instance"
          - idShort    : strip the trailing "_Type" suffix added by convention
        """
        shell["assetInformation"]["assetKind"] = "Instance"
        shell["idShort"] = asset_key
        return shell

    def _patch_properties(
        self,
        submodel: Dict,
        config: Dict[str, Any],
        config_map: Dict[str, str],
    ) -> Dict:
        """
        Walk List_Of_Properties and set 'value' for every property whose
        idShort appears in config_map, taking the value from config.
        """
        for element in submodel.get("submodelElements", []):
            if element.get("idShort") == "List_Of_Properties":
                for prop in element.get("value", []):
                    prop_id = prop.get("idShort")
                    if prop_id in config_map:
                        config_key = config_map[prop_id]
                        val = config.get(config_key)
                        if val is not None:
                            prop["value"] = str(val)
        return submodel

    def _patch_documentation(self, submodel: Dict, instance_num: str) -> Dict:
        """
        Set Instance_Number and Created_Date in Documentation.
        """
        patch = {
            "Instance_Number": instance_num,
            "Created_Date": datetime.now().strftime("%Y-%m-%d"),
        }
        for element in submodel.get("submodelElements", []):
            if element.get("idShort") == "List_Of_Properties":
                for prop in element.get("value", []):
                    prop_id = prop.get("idShort")
                    if prop_id in patch:
                        prop["value"] = patch[prop_id]
        return submodel

    def _patch_bom(
        self,
        submodel: Dict,
        config: Dict[str, Any],
        bom_dynamic_quantities: Dict[str, str],
    ) -> Dict:
        """
        Update Bill_Of_Materials quantities based on configuration.
        """
        for element in submodel.get("submodelElements", []):
            if element.get("idShort") == "List_Of_Components":
                for component in element.get("value", []):
                    comp_id = component.get("idShort")
                    if comp_id in bom_dynamic_quantities:
                        config_key = bom_dynamic_quantities[comp_id]
                        qty = config.get(config_key)
                        if qty is not None:
                            for prop in component.get("value", []):
                                if prop.get("idShort") == "Quantity":
                                    prop["value"] = str(qty)
        return submodel

    def _expand_pcb_with_fuse_bop(self, submodel: Dict, fuse_ids: List[str]) -> Dict:
        """
        Expand Bill_Of_Processes for PCB_With_Fuse based on number of fuses.
        """
        # This is a placeholder - implement based on your actual BOP structure
        return submodel

    # -------------------------------------------------------------------------
    # Generic instance creation with inventory deduction
    # -------------------------------------------------------------------------

    def _create_asset_instance(
        self,
        asset_key: str,
        instance_num: str,
        config: Dict[str, Any],
        fuse_ids: Optional[List[str]] = None,
    ) -> Tuple[bool, str]:
        """
        Create one complete asset instance (shell + all submodels) by loading
        the Type files and patching them for the given instance number.

        Deducts from inventory on successful creation.

        Returns:
            Tuple of (success: bool, instance_id: str)
        """
        cfg = ASSET_REGISTRY[asset_key]

        # --- Shell ---
        shell = self._type_to_instance(
            copy.deepcopy(self._load_type_shell(asset_key)), instance_num
        )
        shell = self._patch_shell(shell, asset_key)

        shell_filename = f"{cfg['instance_file_prefix']}-{instance_num}.json"
        self._save_json(cfg["instance_shell_dir"], shell_filename, shell)
        instance_id: str = shell["id"]

        # --- Submodels ---
        for submodel_name in cfg["submodels"]:
            sm = self._type_to_instance(
                copy.deepcopy(self._load_type_submodel(asset_key, submodel_name)),
                instance_num,
            )

            if submodel_name == "Properties" and cfg["properties_config_map"]:
                sm = self._patch_properties(sm, config, cfg["properties_config_map"])

            elif submodel_name == "Documentation":
                sm = self._patch_documentation(sm, instance_num)

            elif submodel_name == "Bill_Of_Materials" and cfg["bom_dynamic_quantities"]:
                sm = self._patch_bom(sm, config, cfg["bom_dynamic_quantities"])

            elif submodel_name == "Bill_Of_Processes" and asset_key == "PCB_With_Fuse":
                if fuse_ids:
                    sm = self._expand_pcb_with_fuse_bop(sm, fuse_ids)

            sm_filename = f"{cfg['instance_file_prefix']}-{instance_num}-{submodel_name}.json"
            self._save_json(cfg["instance_submodels_dir"], sm_filename, sm)

        # --- Deduct from inventory ---
        # Special handling for Fuses - can use any variant
        if asset_key == "Fuse":
            # When creating individual fuse instances, use "Standard Rating"
            variant_spec = "Standard Rating"
            # Find a fuse variant with stock and deduct from it
            fuse_variants = self.inventory.get_all_inventory_by_component("Fuse")
            success = False
            for fuse_variant in fuse_variants:
                if fuse_variant.quantity > 0:
                    success, new_qty = self.inventory.update_inventory(
                        asset_key, fuse_variant.variant_spec, -1,
                        notes=f"Created fuse instance {instance_num}"
                    )
                    if success:
                        print(f"  ✓ Inventory deducted: Fuse ({fuse_variant.variant_spec}) → {new_qty} remaining")
                        break
            if not success:
                print(f"  ⚠ Warning: Could not deduct from inventory for Fuse")
        else:
            variant_spec = self._build_variant_spec(asset_key, config)
            success, new_qty = self.inventory.update_inventory(
                asset_key, variant_spec, -1,
                notes=f"Created instance {instance_num}"
            )

            if success:
                print(f"  ✓ Inventory deducted: {asset_key} ({variant_spec}) → {new_qty} remaining")
            else:
                print(f"  ⚠ Warning: Could not deduct from inventory for {asset_key}")

        # --- Registry ---
        self._update_registry(cfg["registry_key"], instance_num, config, instance_id)

        print(f"  ✓ Created {asset_key} instance: {instance_num}")
        return True, instance_id

    # -------------------------------------------------------------------------
    # Registry helpers
    # -------------------------------------------------------------------------

    def get_next_instance_number(self, product_type: str) -> str:
        """Return the next zero-padded instance number for a product type."""
        if product_type not in self.registry["product_types"]:
            self.registry["product_types"][product_type] = {
                "last_instance_number": 0,
                "instances": [],
            }
        next_num = self.registry["product_types"][product_type]["last_instance_number"] + 1
        return f"{next_num:03d}"

    def _update_registry(
        self,
        product_type: str,
        instance_num: str,
        config: Dict[str, Any],
        instance_id: str,
    ):
        if product_type not in self.registry["product_types"]:
            self.registry["product_types"][product_type] = {
                "last_instance_number": 0,
                "instances": [],
            }
        self.registry["product_types"][product_type]["last_instance_number"] = int(instance_num)
        self.registry["product_types"][product_type]["instances"].append({
            "instance_number": instance_num,
            "instance_id": instance_id,
            "created_date": datetime.now().strftime("%Y-%m-%d"),
            "configuration": config,
            "notes": "Created by configurator_v3",
        })
        self.registry["last_updated"] = datetime.now().strftime("%Y-%m-%d")
        self._save_registry()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def validate_configuration(self, config: Dict[str, Any]) -> tuple:
        """Validate a configuration against the Configuration_Template rules."""
        is_valid = True
        errors = []

        # Check required keys
        required_keys = [
            "bottom_cover_material", "bottom_cover_color", "bottom_cover_finish",
            "top_cover_material", "top_cover_color", "top_cover_finish",
            "number_of_fuses"
        ]
        for key in required_keys:
            if key not in config:
                is_valid = False
                errors.append(f"Missing configuration key: {key}")

        # Validate fuse count
        fuses = config.get("number_of_fuses", 0)
        if not isinstance(fuses, int) or fuses < 1 or fuses > 3:
            is_valid = False
            errors.append("Number of fuses must be 1, 2, or 3")

        return is_valid, errors

    def create_telefon_instance(self, config: Dict[str, Any]) -> bool:
        """
        Create a complete Telefon product instance.

        Args:
            config: Configuration dictionary with all required keys

        Returns:
            True if successful, False otherwise
        """
        # Validate configuration
        is_valid, errors = self.validate_configuration(config)
        if not errors:
            print("✓ Configuration valid")
        else:
            print("❌ Configuration invalid:")
            for error in errors:
                print(f"  - {error}")
            return False

        # Check inventory availability
        available, messages = self.validate_configuration_availability(config)
        if not available:
            print("\n❌ Cannot create instance: insufficient inventory")
            print("Use '--print-available' to see available options")
            return False

        print("\n✓ Inventory available, proceeding with instance creation...\n")

        # Generate instance numbers
        telefon_instance_num = self.get_next_instance_number("Telefon_Pro_Max")
        bottom_cover_instance_num = self.get_next_instance_number("Bottom_Cover")
        top_cover_instance_num = self.get_next_instance_number("Top_Cover")
        pcb_instance_num = self.get_next_instance_number("PCB")

        fuse_ids = []
        for i in range(config.get("number_of_fuses", 1)):
            fuse_instance_num = self.get_next_instance_number("Fuse")
            fuse_id, _ = self._create_asset_instance("Fuse", fuse_instance_num, config)
            fuse_ids.append(fuse_id)

        print()

        # Create sub-assemblies
        self._create_asset_instance("Bottom_Cover", bottom_cover_instance_num, config)
        self._create_asset_instance("Top_Cover", top_cover_instance_num, config)
        self._create_asset_instance("PCB", pcb_instance_num, config, fuse_ids)

        print()

        # Create final product
        self._create_asset_instance("Telefon", telefon_instance_num, config, fuse_ids)

        print(f"\n✓ Successfully created Telefon instance: {telefon_instance_num}\n")
        return True

    def generate_random_configuration(self) -> Dict[str, Any]:
        """
        Generate a random valid configuration based on available inventory.
        """
        available = self.get_available_configurations()

        # Get first available option for each component type
        bottom_covers = available.get("Bottom_Cover", [])
        top_covers = available.get("Top_Cover", [])
        pcbs = available.get("PCB", [])
        fuses = available.get("Fuse", [])

        if not bottom_covers or not top_covers:
            print("❌ Cannot generate random configuration: insufficient inventory")
            return {}

        # Parse material, color, finish from variant specs
        def parse_variant(variant_spec: str) -> tuple:
            parts = {part.split(": ")[0]: part.split(": ")[1] for part in variant_spec.split(", ") if ": " in part}
            return parts.get("Material", "PLA-31212"), parts.get("Color", "Red"), parts.get("Finish", "Glossy")

        bottom_material, bottom_color, bottom_finish = parse_variant(random.choice(bottom_covers))
        top_material, top_color, top_finish = parse_variant(random.choice(top_covers))

        min_fuses = 1
        fuse_count = max(min_fuses, random.randint(1, 3))

        return {
            "bottom_cover_material": bottom_material,
            "bottom_cover_color":    bottom_color,
            "bottom_cover_finish":   bottom_finish,
            "top_cover_material":    top_material,
            "top_cover_color":       top_color,
            "top_cover_finish":      top_finish,
            "number_of_fuses":       fuse_count,
        }

    def generate_random_instances(self, count: int):
        """Generate multiple random Telefon instances from available inventory."""
        print(f"\n=== Generating {count} Random Telefon Instances ===\n")
        successful = 0
        failed = 0

        for i in range(count):
            config = self.generate_random_configuration()
            if not config:
                print(f"Instance {i + 1}/{count}: ⚠ Skipped (no available configuration)")
                failed += 1
                continue

            print(f"Instance {i + 1}/{count}:")
            if self.create_telefon_instance(config):
                successful += 1
            else:
                failed += 1

        print(f"✓ Generated {successful} instances, {failed} failed/skipped\n")

    def reset_registry(self, confirm: bool = False, delete_instances: bool = False) -> bool:
        """
        Reset the instance registry to its initial empty state.

        Args:
            confirm:          Skip the interactive confirmation prompt.
            delete_instances: Also delete all generated instance JSON files.
        """
        if not confirm:
            print("\n⚠️  WARNING: This will reset the instance registry to initial state.")
            if delete_instances:
                print("⚠️  WARNING: All instance JSON files will be PERMANENTLY DELETED!")
            else:
                print("All instance tracking data will be lost (existing JSON files remain).")
            print()
            if input("Are you sure you want to continue? (yes/no): ").strip().lower() != "yes":
                print("Registry reset cancelled.")
                return False

        initial_registry: Dict[str, Any] = {
            "description": "Registry tracking all created product instances for ID management",
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "product_types": {},
        }

        for asset_key, cfg in ASSET_REGISTRY.items():
            reg_key = cfg["registry_key"]
            if reg_key not in initial_registry["product_types"]:
                initial_registry["product_types"][reg_key] = {
                    "last_instance_number": 0,
                    "instances": [],
                }

        if delete_instances:
            print("\nDeleting instance files...")
            deleted_count = 0

            shell_dirs = {cfg["instance_shell_dir"] for cfg in ASSET_REGISTRY.values()}
            submodel_dirs = {cfg["instance_submodels_dir"] for cfg in ASSET_REGISTRY.values()}

            for rel_dir in shell_dirs | submodel_dirs:
                folder = self.base_path / rel_dir
                if folder.exists():
                    for file in folder.glob("*.json"):
                        file.unlink()
                        deleted_count += 1

            print(f"  ✓ Deleted {deleted_count} instance files")

        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(initial_registry, f, indent=2, ensure_ascii=False)

        self.registry = self._load_registry()
        print("\n✓ Instance registry has been reset to initial state.\n")
        return True


# =============================================================================
# CLI entry point
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Telefon Product Configurator v3 (with Inventory)")
    parser.add_argument("--config",              type=str, help="Path to a configuration JSON file")
    parser.add_argument("--interactive",         action="store_true", help="Interactive configuration mode")
    parser.add_argument("--reset-registry",      action="store_true", help="Reset instance registry")
    parser.add_argument("--delete-instances",    action="store_true", help="Delete instance files on reset")
    parser.add_argument("--generate-random",     type=int, metavar="COUNT", help="Generate COUNT random instances")
    parser.add_argument("--print-inventory",     action="store_true", help="Print inventory summary")
    parser.add_argument("--print-available",     action="store_true", help="Print available configurations")
    parser.add_argument("--init-sample-inventory", action="store_true", help="Initialize with sample inventory")
    args = parser.parse_args()

    workspace_path = Path(__file__).parent
    configurator = TelefonConfiguratorV3(str(workspace_path))

    if args.init_sample_inventory:
        from inventory_db import initialize_sample_inventory
        initialize_sample_inventory(configurator.inventory)
        return

    if args.print_inventory:
        configurator.inventory.print_inventory_summary()
        return

    if args.print_available:
        configurator.print_available_options()
        return

    if args.reset_registry:
        configurator.reset_registry(delete_instances=args.delete_instances)
        return

    if args.generate_random:
        if args.generate_random < 1:
            print("Error: COUNT must be at least 1")
            return
        configurator.generate_random_instances(args.generate_random)
        return

    if args.config:
        with open(args.config, encoding="utf-8") as f:
            config = json.load(f)
        configurator.create_telefon_instance(config)
        return

    if args.interactive:
        print("\n=== Telefon Configurator v3 — Interactive Mode ===\n")

        # First show available options
        configurator.print_available_options()

        config: Dict[str, Any] = {}

        print("Bottom Cover Configuration:")
        config["bottom_cover_material"] = input("  Material [PLA-31212]: ") or "PLA-31212"
        config["bottom_cover_color"]    = input("  Color [Red]: ")                 or "Red"
        config["bottom_cover_finish"]   = input("  Finish [Glossy]: ")             or "Glossy"

        print("\nTop Cover Configuration:")
        config["top_cover_material"] = input("  Material [PLA-31212]: ") or "PLA-31212"
        config["top_cover_color"]    = input("  Color [Red]: ")              or "Red"
        config["top_cover_finish"]   = input("  Finish [Glossy]: ")          or "Glossy"

        print("\nFuse Configuration:")
        config["number_of_fuses"] = int(input("  Number of fuses [1]: ") or "1")

        configurator.create_telefon_instance(config)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
