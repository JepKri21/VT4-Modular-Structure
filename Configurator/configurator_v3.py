"""
Telefon Product Configurator v3

Two-phase approach:
  Phase 1 (Configuration): Validate against inventory, create order (no instances yet)
  Phase 2 (Assembly): Pick component instances, assemble product, fill traceability

This separates configuration (what is ALLOWED) from assembly (what is AVAILABLE).
"""

import json
import sqlite3
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from inventory_db import _create_tables


# =============================================================================
# Configuration
# =============================================================================

# Path to the inventory database
INVENTORY_DB = "inventory.db"

# Asset registry (same as v2)
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
        "bom_dynamic_quantities": {},
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
        "bom_dynamic_quantities": {},
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
        "bom_dynamic_quantities": {},
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
        "bom_dynamic_quantities": {},
    },
    # --- Sub-assemblies: produced during assembly, never consumed from raw inventory ---
    "PCB_With_Fuse": {
        "is_component": False,
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Sub_Assembly_Types/Product-Sub_Assembly-AAU-PCB_With_Fuse-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Sub_Assembly_Type_Submodels",
        "type_submodel_prefix": "Product-Sub_Assembly-AAU-PCB_With_Fuse",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Sub_Assembly_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Sub_Assembly_Instance_Submodels",
        "instance_file_prefix": "Product-Sub_Assembly-AAU-PCB_With_Fuse",
        "registry_key": "PCB_With_Fuse",
        "submodels": ["Properties", "Documentation", "Bill_Of_Materials", "Bill_Of_Processes"],
        "properties_config_map": {"Nr_Fuses": "number_of_fuses"},
        "bom_dynamic_quantities": {},
    },
    "Housing_With_PCB": {
        "is_component": False,
        "type_shell": "JSON_Shells/Product_Shells_JSON/Types/Sub_Assembly_Types/Product-Sub_Assembly-AAU-Housing_With_PCB-Type.json",
        "type_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Types/Sub_Assembly_Type_Submodels",
        "type_submodel_prefix": "Product-Sub_Assembly-AAU-Housing_With_PCB",
        "instance_shell_dir": "JSON_Shells/Product_Shells_JSON/Instances/Sub_Assembly_Instances",
        "instance_submodels_dir": "JSON_Submodels/Product_Submodels_JSON/Instances/Sub_Assembly_Instance_Submodels",
        "instance_file_prefix": "Product-Sub_Assembly-AAU-Housing_With_PCB",
        "registry_key": "Housing_With_PCB",
        "submodels": ["Properties", "Documentation", "Bill_Of_Materials", "Bill_Of_Processes"],
        "properties_config_map": {
            "Material": "bottom_cover_material",
            "Color": "bottom_cover_color",
            "Finish": "bottom_cover_finish",
            "Nr_Fuses": "number_of_fuses",
        },
        "bom_dynamic_quantities": {},
    },
    "Telefon": {
        "is_component": False,  # output product — not consumed from inventory
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
        "bom_dynamic_quantities": {},
    },
}


# =============================================================================
# Example Orders (for testing — all configs use components from SHOPPING_LIST)
# =============================================================================

# Each entry is a config dict that can be passed to create_configuration_order().
# All material/color/finish values match exactly what the shopping list produces.
EXAMPLE_ORDERS: List[Dict[str, Any]] = [
    # 1 — Matching covers, PLA Red Glossy, 1 fuse
    {
        "bottom_cover_material": "PLA-31212", "bottom_cover_color": "Red",   "bottom_cover_finish": "Glossy",
        "top_cover_material":    "PLA-31212", "top_cover_color":    "Red",   "top_cover_finish":    "Glossy",
        "number_of_fuses": 1,
    },
    # 2 — Matching covers, PLA Blue Glossy, 2 fuses
    {
        "bottom_cover_material": "PLA-31212", "bottom_cover_color": "Blue",  "bottom_cover_finish": "Glossy",
        "top_cover_material":    "PLA-31212", "top_cover_color":    "Blue",  "top_cover_finish":    "Glossy",
        "number_of_fuses": 2,
    },
    # 3 — Matching covers, PLA Black Matte, 1 fuse
    {
        "bottom_cover_material": "PLA-31212", "bottom_cover_color": "Black", "bottom_cover_finish": "Matte",
        "top_cover_material":    "PLA-31212", "top_cover_color":    "Black", "top_cover_finish":    "Matte",
        "number_of_fuses": 1,
    },
    # 4 — Mixed covers, ABS Black Textured bottom / PLA White Matte top, 3 fuses
    {
        "bottom_cover_material": "ABS-5500",  "bottom_cover_color": "Black", "bottom_cover_finish": "Textured",
        "top_cover_material":    "PLA-31212", "top_cover_color":    "White", "top_cover_finish":    "Matte",
        "number_of_fuses": 3,
    },
    # 5 — Mixed covers, PLA White Matte bottom / ABS White Glossy top, 2 fuses
    {
        "bottom_cover_material": "PLA-31212", "bottom_cover_color": "White", "bottom_cover_finish": "Matte",
        "top_cover_material":    "ABS-5500",  "top_cover_color":    "White", "top_cover_finish":    "Glossy",
        "number_of_fuses": 2,
    },
]


# =============================================================================
# Database helpers
# =============================================================================

def _get_connection(db_path: str) -> sqlite3.Connection:
    """Return a database connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# =============================================================================
# Phase 1: Configuration (Create Order)
# =============================================================================

class TelefonConfiguratorV3:
    """
    Two-phase Telefon configurator.
    
    Phase 1: create_configuration_order() — validates config, checks inventory, creates order
    Phase 2: (handled by assembly_manager.py) — picks instances and assembles
    """

    def __init__(self, base_path: str, db_path: str = INVENTORY_DB):
        self.base_path = Path(base_path)
        self.db_path = db_path
        self.config_template_path = (
            self.base_path
            / "JSON_Submodels"
            / "Product_Submodels_JSON"
            / "Final_Product_Submodels"
            / "Product-Final_Product-Telefon-Telefon_Pro_Max-Configuration_Template.json"
        )
        self.config_template = self._load_config_template()

    def _load_config_template(self) -> Dict[str, Any]:
        with open(self.config_template_path, encoding="utf-8") as f:
            return json.load(f)

    def _get_model_numbers_for_config(self, config: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate the model numbers needed for a configuration by reading every
        Type-Documentation file listed in ASSET_REGISTRY that has a
        Model_Number_Configuration/Template element.

        Returns dict: {component_type: model_number}
        """
        model_numbers = {}

        for asset_key, cfg in ASSET_REGISTRY.items():
            if not cfg.get("is_component", False):
                continue  # skip output products (Telefon)
            doc_path = (
                self.base_path
                / cfg["type_submodels_dir"]
                / f"{cfg['type_submodel_prefix']}-Type-Documentation.json"
            )
            if not doc_path.exists():
                continue

            with open(doc_path, encoding="utf-8") as f:
                doc = json.load(f)

            template = None
            for elem in doc.get("submodelElements", []):
                if elem.get("idShort") == "Model_Number_Configuration":
                    for child in elem.get("value", []):
                        if child.get("idShort") == "Template":
                            template = child.get("value")

            if template:
                model_num = re.sub(
                    r"\{(\w+)\}",
                    lambda m: str(config.get(m.group(1), m.group(0))),
                    template,
                )
                model_numbers[asset_key] = model_num
            else:
                # Fallback: read fixed Model_Number directly (e.g. Fuse has no template)
                for elem in doc.get("submodelElements", []):
                    if elem.get("idShort") == "Model_Number":
                        fixed_model = elem.get("value")
                        if fixed_model:
                            model_numbers[asset_key] = fixed_model
                        break

        return model_numbers

    def _get_available_options(self) -> Dict[str, Dict[str, int]]:
        """
        Query inventory to find all available configuration options.
        Returns: {
            "bottom_cover_materials": {"PLA-31212": qty, "ABS-5500": qty, ...},
            "bottom_cover_colors": {"Red": qty, "Black": qty, ...},
            "bottom_cover_finishes": {"Glossy": qty, "Matte": qty, ...},
            "top_cover_materials": {...},
            "top_cover_colors": {...},
            "top_cover_finishes": {...},
            "fuse_counts": {1: qty, 2: qty, 3: qty, ...}
        }
        
        Only includes options where qty_available > 0.
        """
        conn = _get_connection(str(self.base_path / self.db_path))
        _create_tables(conn)
        
        available = {
            "bottom_cover_materials": {},
            "bottom_cover_colors": {},
            "bottom_cover_finishes": {},
            "bottom_cover_combos": {},   # (material, color, finish) -> qty
            "top_cover_materials": {},
            "top_cover_colors": {},
            "top_cover_finishes": {},
            "top_cover_combos": {},       # (material, color, finish) -> qty
            "fuse_counts": {},
        }

        # Get all bottom cover options: BC-{material}-{color}-{finish}
        rows = conn.execute(
            "SELECT model_number, qty_available FROM inventory_stock "
            "WHERE model_number LIKE 'BC-%' AND qty_available > 0"
        ).fetchall()
        for row in rows:
            # BC-ABS-5500-Black-Matte
            parts = row["model_number"].split("-")
            if len(parts) >= 4:
                material = f"{parts[1]}-{parts[2]}"  # ABS-5500
                color = parts[3]  # Black
                finish = parts[4] if len(parts) > 4 else "Glossy"
                qty = row["qty_available"]
                available["bottom_cover_materials"][material] = available["bottom_cover_materials"].get(material, 0) + qty
                available["bottom_cover_colors"][color] = available["bottom_cover_colors"].get(color, 0) + qty
                available["bottom_cover_finishes"][finish] = available["bottom_cover_finishes"].get(finish, 0) + qty
                combo = (material, color, finish)
                available["bottom_cover_combos"][combo] = available["bottom_cover_combos"].get(combo, 0) + qty

        # Get all top cover options: TC-{material}-{color}-{finish}
        rows = conn.execute(
            "SELECT model_number, qty_available FROM inventory_stock "
            "WHERE model_number LIKE 'TC-%' AND qty_available > 0"
        ).fetchall()
        for row in rows:
            # TC-PLA-31212-Red-Glossy
            parts = row["model_number"].split("-")
            if len(parts) >= 4:
                material = f"{parts[1]}-{parts[2]}"  # PLA-31212
                color = parts[3]  # Red
                finish = parts[4] if len(parts) > 4 else "Glossy"
                qty = row["qty_available"]
                available["top_cover_materials"][material] = available["top_cover_materials"].get(material, 0) + qty
                available["top_cover_colors"][color] = available["top_cover_colors"].get(color, 0) + qty
                available["top_cover_finishes"][finish] = available["top_cover_finishes"].get(finish, 0) + qty
                combo = (material, color, finish)
                available["top_cover_combos"][combo] = available["top_cover_combos"].get(combo, 0) + qty

        # Get available fuse counts from individual Fuse components (model FUSE-AAU)
        fuse_row = conn.execute(
            "SELECT qty_available FROM inventory_stock "
            "WHERE model_number = 'FUSE-AAU' AND qty_available > 0"
        ).fetchone()
        total_fuses = fuse_row["qty_available"] if fuse_row else 0
        # A product can use 1..N fuses — show all valid counts given current stock (max 5)
        for n in range(1, min(total_fuses + 1, 6)):
            available["fuse_counts"][n] = total_fuses

        conn.close()
        return available

    def validate_configuration(self, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate a configuration against the Configuration_Template rules."""
        errors = []

        # Check required fields
        required = ["bottom_cover_material", "bottom_cover_color", "bottom_cover_finish",
                   "top_cover_material", "top_cover_color", "top_cover_finish", "number_of_fuses"]
        for field in required:
            if field not in config:
                errors.append(f"Missing required field: {field}")

        # Material/finish compatibility
        for elem in self.config_template.get("submodelElements", []):
            if elem.get("idShort") == "Configuration_Rules":
                for rule in elem.get("value", []):
                    if rule.get("idShort") == "Material_Finish_Compatibility":
                        incompatible = []
                        for incompat in rule.get("value", []):
                            material = finish = None
                            for prop in incompat.get("value", []):
                                if prop.get("idShort") == "Incompatible_Material":
                                    material = prop.get("value")
                                elif prop.get("idShort") == "Incompatible_Finish":
                                    finish = prop.get("value")
                            if material and finish:
                                incompatible.append((material, finish))

                        if ("bottom_cover_material" in config and "bottom_cover_finish" in config):
                            if (config["bottom_cover_material"], config["bottom_cover_finish"]) in incompatible:
                                errors.append(f"Invalid: {config['bottom_cover_material']} cannot be {config['bottom_cover_finish']}")

        return len(errors) == 0, errors

    def check_inventory(self, config: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if required model numbers are in stock.
        Returns: (all_available: bool, inventory_status: dict)
        """
        from inventory_db import _create_tables

        model_numbers = self._get_model_numbers_for_config(config)

        conn = _get_connection(str(self.base_path / self.db_path))
        _create_tables(conn)  # ensure tables exist even on first run
        inventory_status = {}
        all_available = True

        for comp_type, model_num in model_numbers.items():
            qty_needed = config.get("number_of_fuses", 1) if comp_type == "Fuse" else 1
            row = conn.execute(
                "SELECT qty_available FROM inventory_stock WHERE model_number = ?",
                (model_num,),
            ).fetchone()

            available = row["qty_available"] if row else 0
            inventory_status[comp_type] = {
                "model_number": model_num,
                "qty_available": available,
                "qty_needed": qty_needed,
                "in_stock": available >= qty_needed,
            }

            if available < qty_needed:
                all_available = False

        conn.close()
        return all_available, inventory_status

    def create_configuration_order(self, config: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        PHASE 1: Validate configuration, check inventory, RESERVE instances, and create an order.
        
        Instances are reserved during configuration to prevent race conditions where two orders
        could both think the same component is available. Once reserved, assembly is guaranteed
        to succeed (unless DB is corrupted).

        Returns: (order_id, order_details)
        """
        from assembly_manager import AssemblyManager
        
        # Validate config
        is_valid, errors = self.validate_configuration(config)
        if not is_valid:
            raise ValueError(f"Invalid configuration: {', '.join(errors)}")

        # Check inventory
        in_stock, inventory_status = self.check_inventory(config)
        if not in_stock:
            unavailable = [f"{st['model_number']}" for st in inventory_status.values() if not st["in_stock"]]
            raise ValueError(f"Not in stock: {', '.join(unavailable)}")

        # Get model numbers
        model_numbers = self._get_model_numbers_for_config(config)

        # Open DB connection for order creation + instance reservation (single transaction)
        conn = _get_connection(str(self.base_path / self.db_path))
        _create_tables(conn)
        
        # Expand Fuse into individual slots (Fuse_1, Fuse_2, ...) so each fuse
        # gets a distinct reserved instance from inventory
        model_numbers_for_reservation = {}
        for comp_type, model_num in model_numbers.items():
            if comp_type == "Fuse":
                for i in range(1, config.get("number_of_fuses", 1) + 1):
                    model_numbers_for_reservation[f"Fuse_{i}"] = model_num
            else:
                model_numbers_for_reservation[comp_type] = model_num

        # Find and reserve instances (this is the key difference from Phase 1 without reservations)
        print("\nReserving component instances for this order...")
        asm = AssemblyManager(str(self.base_path))
        try:
            available_instances = asm.find_available_instances(model_numbers_for_reservation, conn)
        except Exception as e:
            conn.close()
            raise ValueError(f"Cannot reserve instances: {e}")

        # Reserve all instances (update status to 'reserved')
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for comp_type, inst in available_instances.items():
            conn.execute(
                "UPDATE inventory_items SET status = 'reserved', last_updated = ? WHERE instance_id = ?",
                (now, inst["instance_id"]),
            )
            print(f"  ✓ Reserved {comp_type}: {inst['model_number']} (instance {inst['instance_number']})")

        # Get next order number
        last_order = conn.execute(
            "SELECT order_id FROM configuration_orders ORDER BY order_id DESC LIMIT 1"
        ).fetchone()
        
        order_num = 1
        if last_order:
            order_id_str = last_order["order_id"]
            if order_id_str.startswith("ORD-"):
                try:
                    order_num = int(order_id_str.split("-")[1]) + 1
                except (IndexError, ValueError):
                    order_num = 1
        
        order_id = f"ORD-{order_num:03d}"

        # Create order with reserved instances stored
        conn.execute("""
            INSERT INTO configuration_orders (
                order_id, product_type, configuration, model_numbers_needed,
                reserved_instances, status, created_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            order_id,
            "Telefon_Pro_Max",
            json.dumps(config),
            json.dumps(model_numbers),
            json.dumps(available_instances),  # Store reserved instances
            "pending",
            now,
        ))
        conn.commit()
        conn.close()

        order_details = {
            "order_id": order_id,
            "product_type": "Telefon_Pro_Max",
            "configuration": config,
            "model_numbers_needed": model_numbers,
            "reserved_instances": available_instances,  # Now reserved!
            "inventory_status": inventory_status,
            "created_date": now,
        }

        print(f"\n✓ Configuration order created: {order_id}")
        print(f"  Product Type: Telefon_Pro_Max")
        print(f"  Status: pending (waiting for assembly)")
        print(f"  Model Numbers Needed:")
        for comp_type, model_num in model_numbers.items():
            print(f"    - {comp_type}: {model_num}")

        return order_id, order_details

    def reset_registry(self, delete_instances: bool = False) -> bool:
        """
        Reset the v3 order registry:
          - Clears configuration_orders and assembly_log tables.
          - Restores any 'reserved' inventory items back to 'available'.
          - Optionally deletes all generated instance JSON files and clears
            inventory_items / inventory_stock (model_catalog is preserved).
        """
        print("\n⚠️  WARNING: This will clear all configuration orders and assembly history.")
        if delete_instances:
            print("⚠️  WARNING: All instance JSON files will be PERMANENTLY DELETED!")
            print("             inventory_items and inventory_stock will also be cleared.")
        else:
            print("   Existing instance JSON files are kept; only DB order records are removed.")
        print()
        if input("Are you sure you want to continue? (yes/no): ").strip().lower() != "yes":
            print("Registry reset cancelled.")
            return False

        conn = _get_connection(str(self.base_path / self.db_path))
        _create_tables(conn)

        # Release any reserved items back to available
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        released = conn.execute(
            "UPDATE inventory_items SET status = 'available', last_updated = ? WHERE status = 'reserved'",
            (now,),
        ).rowcount
        if released:
            print(f"  ✓ Released {released} reserved inventory item(s) back to 'available'")

        # Clear order tables
        conn.execute("DELETE FROM assembly_log")
        conn.execute("DELETE FROM configuration_orders")
        print("  ✓ Cleared configuration_orders and assembly_log")

        if delete_instances:
            # Delete instance JSON files
            from inventory_db import INSTANCE_SUBMODEL_DIRS
            instance_shell_dirs = [
                cfg["instance_shell_dir"]
                for cfg in ASSET_REGISTRY.values()
            ]
            instance_submodel_dirs = list(INSTANCE_SUBMODEL_DIRS)
            deleted_count = 0
            for rel_dir in set(instance_shell_dirs) | set(instance_submodel_dirs):
                folder = self.base_path / rel_dir
                if folder.exists():
                    for file in folder.glob("*.json"):
                        file.unlink()
                        deleted_count += 1
            print(f"  ✓ Deleted {deleted_count} instance JSON file(s)")

            # Clear inventory tables (preserve model_catalog)
            conn.execute("DELETE FROM inventory_items")
            conn.execute("DELETE FROM inventory_stock")
            print("  ✓ Cleared inventory_items and inventory_stock (model_catalog preserved)")

        conn.commit()
        conn.close()

        print("\n✓ Registry reset complete. All order numbers will start from ORD-001 for new orders.\n")
        return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Telefon Product Configurator v3")
    parser.add_argument("--config", type=str, help="Path to a configuration JSON file")
    parser.add_argument("--interactive", action="store_true", help="Interactive configuration mode")
    parser.add_argument("--list-orders", action="store_true", help="List pending orders")
    parser.add_argument("--reset-registry", action="store_true", help="Clear all configuration orders and assembly history")
    parser.add_argument("--delete-instances", action="store_true", help="Also delete instance JSON files and clear inventory (use with --reset-registry)")
    parser.add_argument("--example-orders", action="store_true", help="Create all example test orders from the built-in EXAMPLE_ORDERS list")
    args = parser.parse_args()

    workspace_path = Path(__file__).parent
    configurator = TelefonConfiguratorV3(str(workspace_path))

    if args.reset_registry:
        configurator.reset_registry(delete_instances=args.delete_instances)
        return

    if args.example_orders:
        print("\n" + "=" * 70)
        print("  EXAMPLE ORDERS — Creating test configuration orders")
        print("=" * 70)
        print(f"  {len(EXAMPLE_ORDERS)} orders to create\n")
        created = []
        failed = []
        for i, config in enumerate(EXAMPLE_ORDERS, 1):
            label = (
                f"BC={config['bottom_cover_material']}/{config['bottom_cover_color']}/{config['bottom_cover_finish']} "
                f"TC={config['top_cover_material']}/{config['top_cover_color']}/{config['top_cover_finish']} "
                f"Fuses={config['number_of_fuses']}"
            )
            print(f"  [{i}/{len(EXAMPLE_ORDERS)}] {label}")
            try:
                order_id, _ = configurator.create_configuration_order(config)
                created.append(order_id)
                print(f"    ✓ Created {order_id}")
            except (ValueError, Exception) as e:
                failed.append((i, str(e)))
                print(f"    ✗ Skipped: {e}")
        print("\n" + "=" * 70)
        print(f"  ✓ Created : {len(created)} order(s): {', '.join(created)}")
        if failed:
            print(f"  ✗ Failed  : {len(failed)} order(s) (insufficient stock or validation error)")
        print("=" * 70)
        print("\nAssemble all at once:")
        for oid in created:
            print(f"  python assembly_manager.py --assemble {oid}")
        print("\nOr step-by-step (per station):")
        for oid in created:
            print(f"  python assembly_manager.py --assemble-step1 {oid}")
            print(f"  python assembly_manager.py --assemble-step2 {oid}")
            print(f"  python assembly_manager.py --assemble-step3 {oid}")
        print()
        return

    if args.list_orders:
        conn = _get_connection(str(workspace_path / INVENTORY_DB))
        orders = conn.execute(
            "SELECT order_id, product_type, status, created_date FROM configuration_orders ORDER BY created_date DESC"
        ).fetchall()
        conn.close()

        if not orders:
            print("No configuration orders found.")
            return

        print("\n" + "=" * 80)
        print("  CONFIGURATION ORDERS")
        print("=" * 80)
        print(f"  {'Order ID':<15} {'Product Type':<20} {'Status':<15} {'Created':<19}")
        print("-" * 80)
        for order in orders:
            print(
                f"  {order['order_id']:<15} {order['product_type']:<20} "
                f"{order['status']:<15} {order['created_date']:<19}"
            )
        print("=" * 80 + "\n")
        return

    if args.config:
        with open(args.config, encoding="utf-8") as f:
            config = json.load(f)
        try:
            order_id, details = configurator.create_configuration_order(config)
            print(f"\nUse assembly_manager.py to assemble this order:\n  python assembly_manager.py --assemble {order_id}\n")
        except ValueError as e:
            print(f"Error: {e}")
        return

    if args.interactive:
        print("\n=== Telefon Configurator v3 — Interactive Configuration ===\n")
        
        # Get available options from inventory
        available = configurator._get_available_options()
        
        if not available["bottom_cover_materials"] or not available["top_cover_materials"] or not available["fuse_counts"]:
            print("Error: Not enough stock. Available options:")
            print(f"  Bottom Cover Materials: {list(available['bottom_cover_materials'].keys()) or 'NONE'}")
            print(f"  Top Cover Materials: {list(available['top_cover_materials'].keys()) or 'NONE'}")
            print(f"  Fuse Counts: {list(available['fuse_counts'].keys()) or 'NONE'}")
            return
        
        config = {}

        def cascade_pick(label: str, combos: dict, prefix: str) -> tuple:
            """Prompt user for material → color → finish, cascade-filtering each step."""
            # Step 1: Material
            materials = sorted(set(mat for (mat, col, fin) in combos))
            while True:
                mat_str = "/".join(materials)
                default = materials[0]
                chosen = input(f"  Material ({mat_str}) [{default}]: ").strip() or default
                if chosen in materials:
                    break
                print(f"  ✗ '{chosen}' not available. Choose from: {mat_str}")
            # Step 2: Color filtered by chosen material
            colors = sorted(set(col for (mat, col, fin) in combos if mat == chosen))
            chosen_mat = chosen
            while True:
                col_str = "/".join(colors)
                default = colors[0]
                chosen = input(f"  Color ({col_str}) [{default}]: ").strip() or default
                if chosen in colors:
                    break
                print(f"  ✗ '{chosen}' not available for {chosen_mat}. Choose from: {col_str}")
            # Step 3: Finish filtered by chosen material + color
            finishes = sorted(set(fin for (mat, col, fin) in combos if mat == chosen_mat and col == chosen))
            chosen_col = chosen
            while True:
                fin_str = "/".join(finishes)
                default = finishes[0]
                chosen = input(f"  Finish ({fin_str}) [{default}]: ").strip() or default
                if chosen in finishes:
                    break
                print(f"  ✗ '{chosen}' not available for {chosen_mat}/{chosen_col}. Choose from: {fin_str}")
            return chosen_mat, chosen_col, chosen

        # Bottom Cover Configuration — cascade filter
        print("Bottom Cover Configuration (Available in Stock):")
        bc_mat, bc_col, bc_fin = cascade_pick(
            "Bottom Cover", available["bottom_cover_combos"], "bottom_cover"
        )
        config["bottom_cover_material"] = bc_mat
        config["bottom_cover_color"] = bc_col
        config["bottom_cover_finish"] = bc_fin

        print("\nPCB Component (Standard):")
        print("  Model: PCB-AAU (fixed standard component)")

        # Top Cover Configuration — cascade filter
        print("\nTop Cover Configuration (Available in Stock):")
        tc_mat, tc_col, tc_fin = cascade_pick(
            "Top Cover", available["top_cover_combos"], "top_cover"
        )
        config["top_cover_material"] = tc_mat
        config["top_cover_color"] = tc_col
        config["top_cover_finish"] = tc_fin

        # PCB with Fuse Assembly Configuration - only show available fuse counts
        print("\nPCB with Fuse Assembly Configuration (Available in Stock):")
        fuse_counts = sorted(available["fuse_counts"].keys())
        default_fuses = fuse_counts[0] if fuse_counts else 1
        fuse_str = "/".join(map(str, fuse_counts))
        config["number_of_fuses"] = int(input(f"  Number of fuses ({fuse_str}) [{default_fuses}]: ") or default_fuses)

        try:
            order_id, details = configurator.create_configuration_order(config)
            print(f"\nUse assembly_manager.py to assemble this order:\n  python assembly_manager.py --assemble {order_id}\n")
        except ValueError as e:
            print(f"Error: {e}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
