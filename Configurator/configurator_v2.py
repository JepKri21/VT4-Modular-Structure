"""
Telefon Product Configurator v2

Template-driven: all instance file layouts are defined entirely in the Type
JSON files.  The configurator loads a Type file, deep-copies it, and patches
only the fields that differ per instance (IDs, configured property values,
configurable BOM quantities, etc.).

Adding / removing a property, BOM component, or process step in a Type file
automatically flows through to every newly generated instance — no code
changes needed.
"""

import json
import copy
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


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
#                              The configurator sets the value of each listed
#                              property from the corresponding config key.
#   bom_dynamic_quantities  – {BOM_component_idShort: config_dict_key}
#                              The configurator overwrites the Quantity of each
#                              listed BOM component from the corresponding key.
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
        "submodels": ["Properties", "Documentation", "Bill_Of_Materials", "Bill_Of_Processes"],
        "properties_config_map": {
            "Nr_Fuses": "number_of_fuses",
        },
        # The BOP for this type is special: steps are expanded per fuse instance.
        # See _expand_pcb_with_fuse_bop().
        "bom_dynamic_quantities": {
            "Fuse": "number_of_fuses",  # BOM component idShort → config key
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
# Configurator class
# =============================================================================

class TelefonConfiguratorV2:
    """
    Template-driven Telefon configurator.

    Every instance file is generated by:
      1. Loading the corresponding Type JSON file
      2. Deep-copying it
      3. Patching only the fields that change per instance

    Layout changes belong in the Type files, not in this code.
    """

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.registry_path = self.base_path / "instance_registry.json"
        self.config_template_path = (
            self.base_path
            / "JSON_Submodels"
            / "Product_Submodels_JSON"
            / "Final_Product_Submodels"
            / "Product-Final_Product-Telefon-Telefon_Pro_Max-Configuration_Template.json"
        )
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
        # e.g. "Bottom_Cover_Type" → "Bottom_Cover"
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

        Properties not listed in config_map keep their Type default value.
        Adding a new property to the Type file requires no code change here;
        only add it to properties_config_map in ASSET_REGISTRY if it is
        configurable.
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

    def _patch_documentation(
        self,
        submodel: Dict,
        instance_num: str,
        config: Dict[str, Any] = None,
    ) -> Dict:
        """
        Set Instance_Number, Model_Number, and Created_Date in Documentation.

        If the Type defines a Model_Number_Configuration collection, this method
        reads the material-to-code mapping from it and auto-generates Model_Number.
        The Model_Number_Configuration is then removed from the instance so only
        real data appears in the output.

        Adding or changing model number codes only requires editing the Type JSON —
        no code changes needed here.
        """
        if config is None:
            config = {}

        patch = {
            "Instance_Number": instance_num,
            "Created_Date": datetime.now().strftime("%Y-%m-%d"),
        }

        # Read Model_Number_Configuration from the Type if present
        elements = submodel.get("submodelElements", [])
        model_num_cfg = next(
            (e for e in elements if e.get("idShort") == "Model_Number_Configuration"),
            None,
        )

        if model_num_cfg and config:
            cfg_children = {e["idShort"]: e for e in model_num_cfg.get("value", [])}

            # Template approach: "{number_of_fuses}" → config value substitution
            template_elem = cfg_children.get("Template")
            if template_elem:
                model_number = re.sub(
                    r"\{(\w+)\}",
                    lambda m: str(config.get(m.group(1), m.group(0))),
                    template_elem["value"],
                )
                patch["Model_Number"] = model_number

            # Material code lookup approach: Material_ID → short code
            else:
                material_key_elem = cfg_children.get("Material_Config_Key")
                material_codes_col = cfg_children.get("Material_Codes")

                if material_key_elem and material_codes_col:
                    material_value = config.get(material_key_elem["value"], "")
                    for entry in material_codes_col.get("value", []):
                        entry_props = {p["idShort"]: p["value"] for p in entry.get("value", [])}
                        if entry_props.get("Material_ID") == material_value:
                            code = entry_props.get("Code", "")
                            if code:
                                patch["Model_Number"] = code
                            break

            # Remove the configuration directive — it belongs in the Type only
            submodel["submodelElements"] = [
                e for e in elements if e.get("idShort") != "Model_Number_Configuration"
            ]

        for elem in submodel.get("submodelElements", []):
            if elem.get("idShort") in patch:
                elem["value"] = patch[elem["idShort"]]
        return submodel

    def _patch_bom(
        self,
        submodel: Dict,
        config: Dict[str, Any],
        dynamic_quantities: Dict[str, str],
    ) -> Dict:
        """
        Patch configurable component quantities in the Bill_Of_Materials.

        The Type BOM lists every component with a Quantity and an
        Is_Configurable flag.  For components listed in dynamic_quantities,
        the Quantity is overwritten with the runtime value from config.

        Example: {"Fuse": "number_of_fuses"} → reads config["number_of_fuses"]
                 and writes it as Quantity for the "Fuse" BOM component.

        Adding or removing BOM components only requires editing the Type BOM
        and, if they are configurable, adding them to bom_dynamic_quantities.
        """
        for element in submodel.get("submodelElements", []):
            if element.get("idShort") == "Components":
                for comp in element.get("value", []):
                    comp_name = comp.get("idShort")
                    if comp_name in dynamic_quantities:
                        config_key = dynamic_quantities[comp_name]
                        new_qty = config.get(config_key)
                        if new_qty is not None:
                            for prop in comp.get("value", []):
                                if prop.get("idShort") == "Quantity":
                                    prop["value"] = str(new_qty)
                                    break
        return submodel

    def _expand_pcb_with_fuse_bop(
        self, submodel: Dict, fuse_ids: List[str]
    ) -> Dict:
        """
        Special handler for PCB_With_Fuse Bill_Of_Processes.

        The Type BOP contains ONE Assemble step as a template.  At instance
        time we need one step per actual fuse, with:
          - Process_Id incremented  (Assemble_1, Assemble_2, …)
          - The generic Fuse type URL in Execution_Constraints replaced by
            the real fuse instance ID

        The structure of the step (semanticId, Parameters, etc.) comes
        entirely from the Type — only the dynamic data is injected here.
        """
        list_of_processes = next(
            (e for e in submodel.get("submodelElements", [])
             if e.get("idShort") == "List_Of_Processes"),
            None,
        )
        if not list_of_processes:
            return submodel

        # Locate the Assemble template and the Fuse type URL within it
        assemble_template = next(
            (s for s in list_of_processes.get("value", [])
             if s.get("idShort") == "Assemble"),
            None,
        )
        if not assemble_template:
            return submodel

        fuse_type_url: Optional[str] = None
        for sub in assemble_template.get("value", []):
            if sub.get("idShort") == "Execution_Constraints":
                for constraint in sub.get("value", []):
                    val = constraint.get("value", "")
                    if "/Fuse" in val:
                        fuse_type_url = val
                        break

        # Build one step per fuse instance
        expanded = []
        for i, fuse_id in enumerate(fuse_ids):
            step = copy.deepcopy(assemble_template)
            for sub in step.get("value", []):
                if sub.get("idShort") == "Process_Id":
                    sub["value"] = f"Assemble_{i + 1}"
                elif sub.get("idShort") == "Execution_Constraints":
                    for constraint in sub.get("value", []):
                        if fuse_type_url and constraint.get("value") == fuse_type_url:
                            constraint["value"] = fuse_id
                            break
            expanded.append(step)

        list_of_processes["value"] = expanded
        return submodel

    # -------------------------------------------------------------------------
    # Generic instance creation  (the heart of v2)
    # -------------------------------------------------------------------------

    def _create_asset_instance(
        self,
        asset_key: str,
        instance_num: str,
        config: Dict[str, Any],
        fuse_ids: Optional[List[str]] = None,
    ) -> str:
        """
        Create one complete asset instance (shell + all submodels) by loading
        the Type files and patching them for the given instance number.

        Returns the instance AAS shell ID string.
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
                sm = self._patch_documentation(sm, instance_num, config)

            elif submodel_name == "Bill_Of_Materials" and cfg["bom_dynamic_quantities"]:
                sm = self._patch_bom(sm, config, cfg["bom_dynamic_quantities"])

            elif submodel_name == "Bill_Of_Processes" and asset_key == "PCB_With_Fuse":
                if fuse_ids:
                    sm = self._expand_pcb_with_fuse_bop(sm, fuse_ids)

            sm_filename = f"{cfg['instance_file_prefix']}-{instance_num}-{submodel_name}.json"
            self._save_json(cfg["instance_submodels_dir"], sm_filename, sm)

        # --- Registry ---
        self._update_registry(cfg["registry_key"], instance_num, config, instance_id)

        print(f"  ✓ Created {asset_key} instance: {instance_num}")
        return instance_id

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
            "notes": "Created by configurator_v2",
        })
        self.registry["last_updated"] = datetime.now().strftime("%Y-%m-%d")
        self._save_registry()
        print(f"  ✓ Updated instance registry")

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def validate_configuration(self, config: Dict[str, Any]) -> tuple:
        """Validate a configuration against the Configuration_Template rules."""
        errors = []

        configurable_components = None
        for elem in self.config_template.get("submodelElements", []):
            if elem.get("idShort") == "Configurable_Components":
                configurable_components = elem
                break

        if not configurable_components:
            errors.append("Configuration template missing Configurable_Components")
            return False, errors

        config_rules = {}
        material_finish_incompatible = []

        for submodel_element in self.config_template.get("submodelElements", []):
            if submodel_element.get("idShort") == "Configuration_Rules":
                for rule in submodel_element.get("value", []):
                    rule_id = rule.get("idShort")
                    if rule_id == "Material_Finish_Compatibility":
                        for incompatibility in rule.get("value", []):
                            material = None
                            finish = None
                            for prop in incompatibility.get("value", []):
                                if prop.get("idShort") == "Incompatible_Material":
                                    material = prop.get("value")
                                elif prop.get("idShort") == "Incompatible_Finish":
                                    finish = prop.get("value")
                            if material and finish:
                                material_finish_incompatible.append((material, finish))
                    else:
                        config_rules[rule_id] = rule.get("value")

        if "bottom_cover_material" in config and "bottom_cover_finish" in config:
            combo = (config["bottom_cover_material"], config["bottom_cover_finish"])
            if combo in material_finish_incompatible:
                errors.append(f"Invalid combination: {combo[0]} cannot be {combo[1]}")

        if "top_cover_material" in config and "top_cover_finish" in config:
            combo = (config["top_cover_material"], config["top_cover_finish"])
            if combo in material_finish_incompatible:
                errors.append(f"Invalid combination: {combo[0]} cannot be {combo[1]}")

        min_fuses = int(config_rules.get("Minimum_Fuses", 1))
        max_fuses = int(config_rules.get("Maximum_Fuses", 3))

        if "number_of_fuses" in config:
            fuse_count = config["number_of_fuses"]
            if not isinstance(fuse_count, int) or fuse_count < min_fuses or fuse_count > max_fuses:
                errors.append(
                    f"Invalid number_of_fuses: {fuse_count}. "
                    f"Must be between {min_fuses} and {max_fuses}"
                )

        return len(errors) == 0, errors

    def create_telefon_instance(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a complete Telefon product instance — shell + submodels for every
        component, sub-assembly, and the final product.

        Args:
            config: dict with keys:
                bottom_cover_material, bottom_cover_color, bottom_cover_finish,
                top_cover_material, top_cover_color, top_cover_finish,
                number_of_fuses

        Returns:
            dict mapping part names to their created instance IDs.
        """
        is_valid, errors = self.validate_configuration(config)
        if not is_valid:
            raise ValueError(f"Invalid configuration: {', '.join(errors)}")

        instance_num = self.get_next_instance_number("Telefon_Pro_Max")
        print(f"\n=== Creating Telefon Instance {instance_num} ===")
        print(f"Configuration: {json.dumps(config, indent=2)}")

        created: Dict[str, Any] = {}

        # 1. Components — all share the same instance_num as the Telefon
        created["Bottom_Cover"] = self._create_asset_instance("Bottom_Cover", instance_num, config)
        created["Top_Cover"]    = self._create_asset_instance("Top_Cover",    instance_num, config)
        created["PCB"]          = self._create_asset_instance("PCB",          instance_num, config)

        # 2. Fuses — each fuse gets its own sequential instance number
        fuse_ids: List[str] = []
        for _ in range(config.get("number_of_fuses", 1)):
            fuse_num = self.get_next_instance_number("Fuse")
            fuse_id  = self._create_asset_instance("Fuse", fuse_num, config)
            fuse_ids.append(fuse_id)
        created["Fuses"] = fuse_ids

        # 3. Sub-assemblies
        created["PCB_With_Fuse"] = self._create_asset_instance(
            "PCB_With_Fuse", instance_num, config, fuse_ids=fuse_ids
        )
        created["Housing_With_PCB"] = self._create_asset_instance(
            "Housing_With_PCB", instance_num, config
        )

        # 4. Final product
        created["Telefon"] = self._create_asset_instance("Telefon", instance_num, config)

        print(f"\n✓ Successfully created Telefon instance {instance_num}")
        print(f"  Instance ID: {created['Telefon']}")
        return created

    def generate_random_configuration(self) -> Dict[str, Any]:
        """Generate a random valid configuration from the Configuration_Template."""
        configurable_components = None
        config_rules_element = None

        for element in self.config_template["submodelElements"]:
            if element["idShort"] == "Configurable_Components":
                configurable_components = element["value"]
            elif element["idShort"] == "Configuration_Rules":
                config_rules_element = element["value"]

        bottom_cover_options = next(
            (c for c in configurable_components if c["idShort"] == "Bottom_Cover_Options"),
            None,
        )

        materials: List[str] = []
        colors:    List[str] = []
        finishes:  List[str] = []
        material_finish_incompatible: List[tuple] = []

        for option in bottom_cover_options["value"]:
            if option["idShort"] == "Available_Materials":
                for mat_col in option["value"]:
                    for prop in mat_col["value"]:
                        if prop["idShort"] == "Material_ID":
                            materials.append(prop["value"])
                            break
            elif option["idShort"] == "Available_Colors":
                colors = [p["value"] for p in option["value"]]
            elif option["idShort"] == "Available_Finishes":
                finishes = [p["value"] for p in option["value"]]

        min_fuses = 1
        max_fuses = 3
        covers_must_match = False

        for rule in config_rules_element:
            if rule["idShort"] == "Minimum_Fuses":
                min_fuses = int(rule["value"])
            elif rule["idShort"] == "Maximum_Fuses":
                max_fuses = int(rule["value"])
            elif rule["idShort"] == "Covers_Must_Match":
                covers_must_match = (
                    rule["value"].lower() == "true"
                    if isinstance(rule["value"], str)
                    else rule["value"]
                )
            elif rule["idShort"] == "Material_Finish_Compatibility":
                for incompatibility in rule.get("value", []):
                    material = finish = None
                    for prop in incompatibility.get("value", []):
                        if prop.get("idShort") == "Incompatible_Material":
                            material = prop.get("value")
                        elif prop.get("idShort") == "Incompatible_Finish":
                            finish = prop.get("value")
                    if material and finish:
                        material_finish_incompatible.append((material, finish))

        for _ in range(100):
            bottom_material = random.choice(materials)
            bottom_finish   = random.choice(finishes)
            if (bottom_material, bottom_finish) in material_finish_incompatible:
                continue

            should_match = covers_must_match or (random.random() < 0.4)

            if should_match:
                top_material = bottom_material
                top_finish   = bottom_finish
                bottom_color = top_color = random.choice(colors)
            else:
                top_material = random.choice(materials)
                top_finish   = random.choice(finishes)
                if (top_material, top_finish) in material_finish_incompatible:
                    continue
                bottom_color = random.choice(colors)
                top_color    = random.choice(colors)

            return {
                "bottom_cover_material": bottom_material,
                "bottom_cover_color":    bottom_color,
                "bottom_cover_finish":   bottom_finish,
                "top_cover_material":    top_material,
                "top_cover_color":       top_color,
                "top_cover_finish":      top_finish,
                "number_of_fuses":       random.randint(min_fuses, max_fuses),
            }

        # Fallback (should never be reached with reasonable config data)
        return {
            "bottom_cover_material": materials[0],
            "bottom_cover_color":    colors[0],
            "bottom_cover_finish":   finishes[0],
            "top_cover_material":    materials[0],
            "top_cover_color":       colors[0],
            "top_cover_finish":      finishes[0],
            "number_of_fuses":       min_fuses,
        }

    def generate_random_instances(self, count: int):
        """Generate multiple random Telefon instances."""
        print(f"\n=== Generating {count} Random Telefon Instances ===\n")
        for i in range(count):
            config = self.generate_random_configuration()
            print(f"Instance {i + 1}/{count}:")
            self.create_telefon_instance(config)
            print()
        print(f"✓ Successfully generated {count} random instances\n")

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

        # Build initial product_types from ASSET_REGISTRY
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

            # Collect unique instance dirs from ASSET_REGISTRY
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
        print("\n✓ Instance registry has been reset to initial state.")
        print("  All instance numbers will start from 001 for new instances.\n")
        return True


# =============================================================================
# CLI entry point
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Telefon Product Configurator v2")
    parser.add_argument("--config",          type=str, help="Path to a configuration JSON file")
    parser.add_argument("--interactive",     action="store_true", help="Interactive configuration mode")
    parser.add_argument("--reset-registry",  action="store_true", help="Reset instance registry")
    parser.add_argument("--delete-instances",action="store_true", help="Delete instance files on reset")
    parser.add_argument("--generate-random", type=int, metavar="COUNT", help="Generate COUNT random instances")
    args = parser.parse_args()

    workspace_path = Path(__file__).parent
    configurator = TelefonConfiguratorV2(str(workspace_path))

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
        print("\n=== Telefon Configurator v2 — Interactive Mode ===\n")
        config: Dict[str, Any] = {}

        print("Bottom Cover Configuration:")
        config["bottom_cover_material"] = input("  Material (PLA-31212/ABS-5500/PETG-7700) [PLA-31212]: ") or "PLA-31212"
        config["bottom_cover_color"]    = input("  Color (Red/Blue/Black/White/Green) [Red]: ")            or "Red"
        config["bottom_cover_finish"]   = input("  Finish (Glossy/Matte/Textured) [Glossy]: ")            or "Glossy"

        print("\nTop Cover Configuration:")
        config["top_cover_material"] = input("  Material (PLA-31212/ABS-5500/PETG-7700) [PLA-31212]: ") or "PLA-31212"
        config["top_cover_color"]    = input("  Color (Red/Blue/Black/White/Green) [Red]: ")            or "Red"
        config["top_cover_finish"]   = input("  Finish (Glossy/Matte/Textured) [Glossy]: ")            or "Glossy"

        print("\nFuse Configuration:")
        config["number_of_fuses"] = int(input("  Number of fuses (1/2/3) [1]: ") or "1")

        configurator.create_telefon_instance(config)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
