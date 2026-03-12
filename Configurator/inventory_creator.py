"""
Inventory Creator for Telefon Components

Allows users to:
1. Select a component type (Bottom_Cover, Top_Cover, PCB, Fuse)
2. Specify quantity to add to inventory
3. Configure properties (Material, Color, Finish) for each instance
4. Generate JSON shell and submodel files for all instances

Generated files are saved in:
  - JSON_Shells/Product_Shells_JSON/Instances/Component_Instances/
  - JSON_Submodels/Product_Submodels_JSON/Instances/Component_Instance_Submodels/
"""

import json
import copy
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import base64

import requests
import inventory_db
from inventory_db import AAS_FILES_BASE


def _b64url(s: str) -> str:
    """Base64url-encode a string (no padding) for AAS REST path segments."""
    return base64.urlsafe_b64encode(s.encode()).rstrip(b"=").decode()


# =============================================================================
# AAS Server Configuration
# =============================================================================

PORT = "8081"
SERVER_BASE = f"http://localhost:{PORT}"
SUBMODEL_ENDPOINT = f"{SERVER_BASE}/submodels"
SHELL_ENDPOINT = f"{SERVER_BASE}/shells"


# =============================================================================
# Asset Type Registry (Component Types Only)
# =============================================================================

COMPONENT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "Bottom_Cover": {
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-Bottom_Cover-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels",
        "type_submodel_prefix": "Product-Component-AAU-Bottom_Cover",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Component_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Component_Instance_Submodels",
        "instance_file_prefix": "Product-Component-AAU-Bottom_Cover",
        "submodels": ["Properties", "Documentation", "Bill_Of_Processes"],
        "properties_config_map": {
            "Material": "bottom_cover_material",
            "Color": "bottom_cover_color",
            "Finish": "bottom_cover_finish",
        },
    },
    "Top_Cover": {
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-Top_Cover-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels",
        "type_submodel_prefix": "Product-Component-AAU-Top_Cover",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Component_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Component_Instance_Submodels",
        "instance_file_prefix": "Product-Component-AAU-Top_Cover",
        "submodels": ["Properties", "Documentation", "Bill_Of_Processes"],
        "properties_config_map": {
            "Material": "top_cover_material",
            "Color": "top_cover_color",
            "Finish": "top_cover_finish",
        },
    },
    "PCB": {
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-PCB-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels",
        "type_submodel_prefix": "Product-Component-AAU-PCB",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Component_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Component_Instance_Submodels",
        "instance_file_prefix": "Product-Component-AAU-PCB",
        "submodels": ["Properties", "Documentation", "Bill_Of_Processes"],
        "properties_config_map": {},
    },
    "Fuse": {
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Component_Types/Product-Component-AAU-Fuse-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Component_Type_Submodels",
        "type_submodel_prefix": "Product-Component-AAU-Fuse",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Component_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Component_Instance_Submodels",
        "instance_file_prefix": "Product-Component-AAU-Fuse",
        "submodels": ["Properties", "Documentation", "Bill_Of_Processes"],
        "properties_config_map": {},
    },
}


# =============================================================================
# Standard Shopping List
# =============================================================================

# Each entry: (component_type, quantity, config_values)
# Edit this list to define your standard stock mix.
SHOPPING_LIST: List[Tuple[str, int, Dict[str, str]]] = [
    # ── Bottom Covers ────────────────────────────────────────────────────────
    ("Bottom_Cover", 2, {"Material": "PLA-31212",  "Color": "Red",   "Finish": "Glossy"}),
    ("Bottom_Cover", 2, {"Material": "PLA-31212",  "Color": "Blue",  "Finish": "Glossy"}),
    ("Bottom_Cover", 2, {"Material": "PLA-31212",  "Color": "Black", "Finish": "Matte"}),
    ("Bottom_Cover", 2, {"Material": "PLA-31212",  "Color": "White", "Finish": "Matte"}),
    ("Bottom_Cover", 1, {"Material": "ABS-5500",   "Color": "Black", "Finish": "Textured"}),
    ("Bottom_Cover", 1, {"Material": "ABS-5500",   "Color": "White", "Finish": "Glossy"}),
    ("Bottom_Cover", 1, {"Material": "PETG-7700",  "Color": "Green", "Finish": "Matte"}),
    # ── Top Covers ───────────────────────────────────────────────────────────
    ("Top_Cover",    2, {"Material": "PLA-31212",  "Color": "Red",   "Finish": "Glossy"}),
    ("Top_Cover",    2, {"Material": "PLA-31212",  "Color": "Blue",  "Finish": "Glossy"}),
    ("Top_Cover",    2, {"Material": "PLA-31212",  "Color": "Black", "Finish": "Matte"}),
    ("Top_Cover",    2, {"Material": "PLA-31212",  "Color": "White", "Finish": "Matte"}),
    ("Top_Cover",    1, {"Material": "ABS-5500",   "Color": "Black", "Finish": "Textured"}),
    ("Top_Cover",    1, {"Material": "ABS-5500",   "Color": "White", "Finish": "Glossy"}),
    ("Top_Cover",    1, {"Material": "PETG-7700",  "Color": "Green", "Finish": "Matte"}),
    # ── PCBs & Fuses ─────────────────────────────────────────────────────────
    ("PCB",          5, {}),
    ("Fuse",        20, {}),
]


# =============================================================================
# Utility Functions
# =============================================================================

def get_next_instance_number(component_type: str, registry: Dict) -> int:
    """
    Scan the instance directory to find the highest existing instance number
    for a component type and return the next available number.
    """
    instance_dir = AAS_FILES_BASE / registry[component_type]["instance_shell_dir"]
    if not instance_dir.exists():
        return 1
    
    prefix = registry[component_type]["instance_file_prefix"]
    max_num = 0
    
    for file in instance_dir.glob(f"{prefix}-*.json"):
        try:
            # Extract number from filename like "Product-Component-AAU-Bottom_Cover-001.json"
            filename = file.name
            num_part = filename.replace(prefix + "-", "").replace(".json", "")
            if num_part.isdigit():
                num = int(num_part)
                max_num = max(max_num, num)
        except:
            pass
    
    return max_num + 1


def load_type_files(component_type: str, registry: Dict) -> Dict[str, Any]:
    """
    Load the Type shell and all Type submodel files for a component.
    Returns a dict with 'shell' and 'submodels' keys.
    """
    config = registry[component_type]
    base_path = AAS_FILES_BASE
    
    # Load shell
    shell_path = base_path / config["type_shell"]
    with open(shell_path, 'r') as f:
        shell = json.load(f)
    
    # Load submodels
    submodels = {}
    submodels_dir = base_path / config["type_submodels_dir"]
    prefix = config["type_submodel_prefix"]
    
    for submodel_name in config["submodels"]:
        filename = f"{prefix}-Type-{submodel_name}.json"
        submodel_path = submodels_dir / filename
        with open(submodel_path, 'r') as f:
            submodels[submodel_name] = json.load(f)
    
    return {"shell": shell, "submodels": submodels}


def update_instance_ids(
    instance_data: Dict[str, Any],
    component_type: str,
    instance_num: int,
    base_url: str = "https://aausmartlab.com/Assets/Product/Component/AAU"
) -> None:
    """
    Update IDs in the instance data (shell + submodels) to reflect the
    instance number. Modifies instance_data in place.
    """
    # Map component type to URL-friendly name
    type_map = {
        "Bottom_Cover": "Bottom_Cover",
        "Top_Cover": "Top_Cover",
        "PCB": "PCB",
        "Fuse": "Fuse",
    }
    type_url = type_map[component_type]
    instance_str = f"{instance_num:03d}"
    
    # Update shell
    # Change assetKind from "Type" to "Instance"
    instance_data["shell"]["assetKind"] = "Instance"
    
    # Update idShort (remove "_Type" suffix if present)
    if instance_data["shell"]["idShort"].endswith("_Type"):
        instance_data["shell"]["idShort"] = instance_data["shell"]["idShort"][:-5]
    
    instance_data["shell"]["id"] = f"{base_url}/{type_url}/{instance_str}"
    instance_data["shell"]["assetInformation"]["assetKind"] = "Instance"
    instance_data["shell"]["assetInformation"]["globalAssetId"] = (
        f"https://aausmartlab.com/Assets/Product/AAU/{type_url}/{instance_str}"
    )
    
    # Update submodel references in shell
    for submodel_ref in instance_data["shell"]["submodels"]:
        old_id = submodel_ref["keys"][0]["value"]
        # Replace "/Type/" with "/{instance_str}/"
        new_id = old_id.replace("/Type/", f"/{instance_str}/")
        submodel_ref["keys"][0]["value"] = new_id
    
    # Update submodels
    for submodel_name, submodel in instance_data["submodels"].items():
        submodel["id"] = f"{base_url}/{type_url}/{instance_str}/{submodel_name}"


def update_documentation_submodel(
    doc_submodel: Dict[str, Any],
    instance_num: int,
    created_date: str,
    config_values: Dict[str, str] = None,
    properties_config_map: Dict[str, str] = None,
) -> None:
    """
    Update Documentation submodel with instance number, creation date, and
    auto-generated model number.

    If the Type defines a Model_Number_Configuration collection, this method
    reads the mapping from it and generates Model_Number. The collection is
    then removed from the instance — it belongs in the Type only.

    config_values uses property names as keys (e.g. {"Material": "PLA-31212"}).
    properties_config_map bridges them to the config keys used in templates
    (e.g. {"Material": "bottom_cover_material"}).
    """
    # Build reverse map: config_key -> value  (e.g. "bottom_cover_material" -> "PLA-31212")
    config_by_key: Dict[str, str] = {}
    if config_values and properties_config_map:
        for prop_name, config_key in properties_config_map.items():
            if prop_name in config_values:
                config_by_key[config_key] = config_values[prop_name]

    patch = {
        "Instance_Number": f"{instance_num:03d}",
        "Created_Date": created_date,
    }

    # Read Model_Number_Configuration from the Type JSON if present
    elements = doc_submodel.get("submodelElements", [])
    model_num_cfg = next(
        (e for e in elements if e.get("idShort") == "Model_Number_Configuration"),
        None,
    )

    if model_num_cfg:
        cfg_children = {e["idShort"]: e for e in model_num_cfg.get("value", [])}

        # Template approach: "{bottom_cover_material}" placeholders -> config value
        template_elem = cfg_children.get("Template")
        if template_elem:
            model_number = re.sub(
                r"\{(\w+)\}",
                lambda m: str(config_by_key.get(m.group(1), m.group(0))),
                template_elem["value"],
            )
            patch["Model_Number"] = model_number

        # Material code lookup approach: Material_ID -> short code
        else:
            material_key_elem = cfg_children.get("Material_Config_Key")
            material_codes_col = cfg_children.get("Material_Codes")

            if material_key_elem and material_codes_col:
                material_value = config_by_key.get(material_key_elem["value"], "")
                for entry in material_codes_col.get("value", []):
                    entry_props = {p["idShort"]: p["value"] for p in entry.get("value", [])}
                    if entry_props.get("Material_ID") == material_value:
                        code = entry_props.get("Code", "")
                        if code:
                            patch["Model_Number"] = code
                        break

        # Remove the configuration directive — it belongs in the Type only
        doc_submodel["submodelElements"] = [
            e for e in elements if e.get("idShort") != "Model_Number_Configuration"
        ]

    for elem in doc_submodel.get("submodelElements", []):
        if elem.get("idShort") in patch:
            elem["value"] = patch[elem["idShort"]]


def update_properties_submodel(
    props_submodel: Dict[str, Any],
    config_values: Dict[str, str]
) -> None:
    """
    Update configurable properties in the Properties submodel.
    config_values is a dict like {"Material": "ABS", "Color": "black", ...}
    """
    if not config_values:
        return
    
    # Navigate to the List_Of_Properties
    for element in props_submodel.get("submodelElements", []):
        if element.get("idShort") == "List_Of_Properties":
            value_list = element.get("value", [])
            for prop in value_list:
                prop_name = prop.get("idShort")
                if prop_name in config_values:
                    prop["value"] = config_values[prop_name]


def _post_or_put(endpoint: str, resource_id: str, data: Dict[str, Any]) -> requests.Response:
    """
    POST to create; if the server returns 409 (already exists), fall back to
    PUT /{base64url(id)} to update in place.
    """
    headers = {"Content-Type": "application/json"}
    response = requests.post(endpoint, json=data, headers=headers, timeout=10)
    if response.status_code == 409:
        put_url = f"{endpoint}/{_b64url(resource_id)}"
        response = requests.put(put_url, json=data, headers=headers, timeout=10)
    return response


def upload_instance_to_server(instance_data: Dict[str, Any]) -> None:
    """
    Upload the instance shell and all its submodels to the AAS server.
    Uses POST; falls back to PUT if the resource already exists (409).
    """
    # Upload submodels first so the shell reference resolves immediately
    for submodel_name, submodel_data in instance_data["submodels"].items():
        sm_id = submodel_data.get("id", "")
        try:
            response = _post_or_put(SUBMODEL_ENDPOINT, sm_id, submodel_data)
            if response.ok:
                print(f"  OK → submodel: {submodel_name}")
            else:
                print(f"  FAIL ({response.status_code}) → submodel: {submodel_name}")
                try:
                    print(f"    Server: {response.json()}")
                except Exception:
                    print(f"    Server: {response.text[:300]}")
        except requests.ConnectionError:
            print(f"  ERROR → could not connect to AAS server at {SERVER_BASE}")
            return

    # Upload shell
    shell_id = instance_data["shell"].get("id", "")
    try:
        response = _post_or_put(SHELL_ENDPOINT, shell_id, instance_data["shell"])
        if response.ok:
            print(f"  OK → shell: {shell_id}")
        else:
            print(f"  FAIL ({response.status_code}) → shell: {shell_id}")
            try:
                print(f"    Server: {response.json()}")
            except Exception:
                print(f"    Server: {response.text[:300]}")
    except requests.ConnectionError:
        print(f"  ERROR → could not connect to AAS server at {SERVER_BASE}")


def save_instance_files(
    instance_data: Dict[str, Any],
    component_type: str,
    instance_num: int,
    registry: Dict
) -> None:
    """
    Save the instance shell and submodel files to disk.
    """
    config = registry[component_type]
    instance_str = f"{instance_num:03d}"
    
    base_path = AAS_FILES_BASE
    
    # Ensure directories exist
    shell_dir = base_path / config["instance_shell_dir"]
    submodels_dir = base_path / config["instance_submodels_dir"]
    shell_dir.mkdir(parents=True, exist_ok=True)
    submodels_dir.mkdir(parents=True, exist_ok=True)
    
    # Save shell
    shell_filename = f"{config['instance_file_prefix']}-{instance_str}.json"
    shell_path = shell_dir / shell_filename
    with open(shell_path, 'w') as f:
        json.dump(instance_data["shell"], f, indent=2)
    
    print(f"  ✓ Saved shell: {shell_filename}")
    
    # Save submodels
    prefix = config["instance_file_prefix"]
    for submodel_name, submodel_data in instance_data["submodels"].items():
        submodel_filename = f"{prefix}-{instance_str}-{submodel_name}.json"
        submodel_path = submodels_dir / submodel_filename
        with open(submodel_path, 'w') as f:
            json.dump(submodel_data, f, indent=2)
        print(f"  ✓ Saved submodel: {submodel_filename}")


# =============================================================================
# User Interface
# =============================================================================

def display_menu() -> Tuple[str, int, Dict[str, str]]:
    """
    Display interactive menu for user to:
    1. Select a component type
    2. Specify quantity
    3. Configure any properties
    
    Returns (component_type, quantity, config_values)
    """
    print("\n" + "=" * 70)
    print("INVENTORY CREATOR - Component Instance Generator")
    print("=" * 70)
    
    # Step 1: Select component type
    print("\nAvailable Component Types:")
    component_list = list(COMPONENT_REGISTRY.keys())
    for i, comp_type in enumerate(component_list, 1):
        print(f"  {i}. {comp_type}")
    
    while True:
        try:
            choice = int(input("\nSelect component type (1-4): "))
            if 1 <= choice <= len(component_list):
                selected_type = component_list[choice - 1]
                break
            print("Invalid choice. Please try again.")
        except ValueError:
            print("Please enter a number.")
    
    print(f"\n✓ Selected: {selected_type}")
    
    # Step 2: Get quantity
    while True:
        try:
            quantity = int(input("\nHow many instances to create? "))
            if quantity > 0:
                break
            print("Quantity must be positive.")
        except ValueError:
            print("Please enter a valid number.")
    
    print(f"✓ Quantity: {quantity}")
    
    # Step 3: Get configurable properties
    config_values = {}
    config_map = COMPONENT_REGISTRY[selected_type]["properties_config_map"]
    
    if config_map:
        print(f"\n{selected_type} has the following configurable properties:")
        for prop_name in config_map.keys():
            while True:
                value = input(f"  {prop_name}: ").strip()
                if value:
                    config_values[prop_name] = value
                    break
                print(f"  {prop_name} cannot be empty.")
    else:
        print(f"\n{selected_type} has no configurable properties.")
    
    return selected_type, quantity, config_values


def confirm_and_create(component_type: str, quantity: int, config_values: Dict[str, str]) -> bool:
    """
    Display summary and ask for confirmation before creating instances.
    """
    print("\n" + "-" * 70)
    print("SUMMARY")
    print("-" * 70)
    print(f"Component Type:  {component_type}")
    print(f"Quantity:        {quantity}")
    if config_values:
        print(f"Configuration:   {config_values}")
    else:
        print(f"Configuration:   (default/none)")
    print("-" * 70)
    
    response = input("\nProceed with creation? (yes/no): ").strip().lower()
    return response in ['yes', 'y']


def create_inventory_items(component_type: str, quantity: int, config_values: Dict[str, str], upload: bool = True) -> None:
    """
    Main logic: Create and save the specified number of instances.
    If upload=True, each instance is also posted to the AAS server.
    """
    print(f"\nCreating {quantity} instances of {component_type}...\n")
    
    # Load type files once
    type_files = load_type_files(component_type, COMPONENT_REGISTRY)
    
    # Get current date for Created_Date field
    created_date = datetime.now().strftime("%Y-%m-%d")
    
    # Create each instance
    for i in range(quantity):
        # Get next instance number
        instance_num = get_next_instance_number(component_type, COMPONENT_REGISTRY)
        
        # Deep copy type files to create instance
        instance_data = {
            "shell": copy.deepcopy(type_files["shell"]),
            "submodels": copy.deepcopy(type_files["submodels"])
        }
        
        # Update IDs
        update_instance_ids(instance_data, component_type, instance_num)
        
        # Update Documentation submodel
        update_documentation_submodel(
            instance_data["submodels"]["Documentation"],
            instance_num,
            created_date,
            config_values,
            COMPONENT_REGISTRY[component_type]["properties_config_map"],
        )
        
        # Update Properties submodel with configured values
        if config_values:
            update_properties_submodel(
                instance_data["submodels"]["Properties"],
                config_values
            )
        
        # Save files
        print(f"Instance #{instance_num:03d}:")
        save_instance_files(instance_data, component_type, instance_num, COMPONENT_REGISTRY)

        # Upload to AAS server
        if upload:
            print(f"  Uploading to AAS server ({SERVER_BASE})...")
            upload_instance_to_server(instance_data)
        print()
    
    print("=" * 70)
    print(f"✓ Successfully created {quantity} instance(s) of {component_type}")
    print("=" * 70)

    # Sync newly created instances to the inventory database
    print("\nSyncing to inventory database...")
    inventory_db.sync(
        db_path=str(Path(__file__).parent / inventory_db.DEFAULT_DB_FILE),
        base_path=AAS_FILES_BASE,
    )


# =============================================================================
# Shopping List Runner
# =============================================================================

def run_shopping_list(shopping_list: List[Tuple[str, int, Dict[str, str]]] = None, upload: bool = True) -> None:
    """
    Create all components defined in the shopping list (or SHOPPING_LIST by
    default) without any interactive prompts.
    If upload=True, each instance is also posted to the AAS server.
    """
    if shopping_list is None:
        shopping_list = SHOPPING_LIST

    total_entries = len(shopping_list)
    total_units = sum(qty for _, qty, _ in shopping_list)

    print("\n" + "=" * 70)
    print("SHOPPING LIST — Standard Stock Creation")
    print("=" * 70)
    print(f"  Entries : {total_entries}")
    print(f"  Total   : {total_units} component instance(s)")
    print("=" * 70)
    print(f"  {'#':<4} {'Component Type':<16} {'Qty':>4}  Configuration")
    print("-" * 70)
    for i, (comp_type, qty, cfg) in enumerate(shopping_list, 1):
        cfg_str = ", ".join(f"{k}={v}" for k, v in cfg.items()) if cfg else "(default)"
        print(f"  {i:<4} {comp_type:<16} {qty:>4}  {cfg_str}")
    print("=" * 70)
    print()

    response = input("Proceed with creation? (yes/no): ").strip().lower()
    if response not in ("yes", "y"):
        print("Operation cancelled.")
        return

    print()
    created_total = 0
    for comp_type, qty, cfg in shopping_list:
        cfg_str = ", ".join(f"{k}={v}" for k, v in cfg.items()) if cfg else "default"
        print(f"\n── {comp_type} x{qty}  [{cfg_str}] ──")
        create_inventory_items(comp_type, qty, cfg, upload=upload)
        created_total += qty

    print("\n" + "=" * 70)
    print(f"✓ Shopping list complete — {created_total} instance(s) created and synced.")
    print("=" * 70 + "\n")


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point for the inventory creator."""
    import argparse
    parser = argparse.ArgumentParser(description="Inventory Creator — Component Instance Generator")
    parser.add_argument(
        "--shopping-list",
        action="store_true",
        help="Create the standard hardcoded shopping list of components without prompts",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip uploading created instances to the AAS server (save files only)",
    )
    args = parser.parse_args()

    upload = not args.no_upload

    try:
        if args.shopping_list:
            run_shopping_list(upload=upload)
            return

        component_type, quantity, config_values = display_menu()

        if confirm_and_create(component_type, quantity, config_values):
            create_inventory_items(component_type, quantity, config_values, upload=upload)
            print("\nDone! Your inventory items have been generated.")
        else:
            print("\nOperation cancelled.")
    
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
