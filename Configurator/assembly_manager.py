"""
Assembly Manager for Telefon Product Configurator v3

PHASE 2: Takes a pending configuration order and assembles it by:
  1. Finding available component instances matching the order's model numbers
  2. Reserving them
  3. Creating the final product instance
  4. Filling Assembly_Traceability with references to used components
  5. Updating instance statuses to 'consumed'
"""

import json
import re
import sqlite3
import copy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from inventory_db import _create_tables
from configurator_v3 import ASSET_REGISTRY


# =============================================================================
# Configuration
# =============================================================================

INVENTORY_DB = "inventory.db"


# =============================================================================
# Database helpers
# =============================================================================

def _get_connection(db_path: str) -> sqlite3.Connection:
    """Return a database connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# =============================================================================
# Assembly Manager
# =============================================================================

class AssemblyManager:
    """
    Manages the assembly phase: converts orders to product instances.
    """

    def __init__(self, base_path: str, db_path: str = INVENTORY_DB):
        self.base_path = Path(base_path)
        self.db_path = db_path

    def _load_type_shell(self, asset_key: str) -> Dict[str, Any]:
        """Load the Type AAS shell for the given asset type key."""
        path = self.base_path / ASSET_REGISTRY[asset_key]["type_shell"]
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _load_type_submodel(self, asset_key: str, submodel_name: str) -> Dict[str, Any]:
        """Load a Type submodel file by asset key and submodel name."""
        cfg = ASSET_REGISTRY[asset_key]
        filename = f"{cfg['type_submodel_prefix']}-Type-{submodel_name}.json"
        path = self.base_path / cfg["type_submodels_dir"] / filename
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _save_json(self, rel_dir: str, filename: str, data: Dict[str, Any]) -> Path:
        """Write data as JSON to base_path / rel_dir / filename."""
        out_path = self.base_path / rel_dir / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return out_path

    def _type_to_instance(self, doc: Dict, instance_num: str) -> Dict:
        """Convert a Type AAS document to an Instance document by replacing /Type/ with instance_num."""
        text = json.dumps(doc)
        text = text.replace("/Type/", f"/{instance_num}/")
        text = text.replace('/Type"', f'/{instance_num}"')
        return json.loads(text)

    def _patch_shell(self, shell: Dict, asset_key: str) -> Dict:
        """After _type_to_instance, fix the shell-specific fields."""
        shell["assetInformation"]["assetKind"] = "Instance"
        shell["idShort"] = asset_key
        return shell

    def _patch_documentation(self, submodel: Dict, instance_num: str, config: Dict = None) -> Dict:
        """Set Instance_Number, Created_Date and Model_Number in Documentation.
        Reads the model number template from Model_Number_Configuration (if present),
        substitutes config values, then removes the directive (belongs in Type only)."""
        elements = submodel.get("submodelElements", [])

        # Read and resolve model number template before removing the directive
        model_number = None
        for elem in elements:
            if elem.get("idShort") == "Model_Number_Configuration":
                for child in elem.get("value", []):
                    if child.get("idShort") == "Template" and config:
                        template = child.get("value", "")
                        model_number = re.sub(
                            r"\{(\w+)\}",
                            lambda m: str(config.get(m.group(1), m.group(0))),
                            template,
                        )
                break

        # Remove the configuration directive
        submodel["submodelElements"] = [
            elem for elem in elements
            if elem.get("idShort") != "Model_Number_Configuration"
        ]
        for elem in submodel.get("submodelElements", []):
            if elem.get("idShort") == "Instance_Number":
                elem["value"] = instance_num
            elif elem.get("idShort") == "Created_Date":
                elem["value"] = datetime.now().strftime("%Y-%m-%d")
            elif elem.get("idShort") == "Model_Number" and model_number:
                elem["value"] = model_number
        return submodel

    def _create_asset_instance(
        self,
        asset_key: str,
        instance_num: str,
        config: Dict = None,
    ) -> str:
        """
        Create one asset instance (shell + submodels) from a Type.
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

            if submodel_name == "Documentation":
                sm = self._patch_documentation(sm, instance_num, config)

            sm_filename = f"{cfg['instance_file_prefix']}-{instance_num}-{submodel_name}.json"
            self._save_json(cfg["instance_submodels_dir"], sm_filename, sm)

        return instance_id

    def _patch_assembly_traceability(
        self,
        submodel: Dict,
        order_id: str,
        assembly_date: str,
        used_components: Dict[str, Dict[str, str]],
    ) -> Dict:
        """
        Fill Assembly_Traceability with references to component instances.
        """
        for elem in submodel.get("submodelElements", []):
            if elem.get("idShort") == "Assembly_Traceability":
                for child in elem.get("value", []):
                    if child.get("idShort") == "Assembly_Date":
                        child["value"] = assembly_date
                    elif child.get("idShort") == "Configuration_Order_ID":
                        child["value"] = order_id
                    elif child.get("idShort") == "Used_Components":
                        for component_ref in child.get("value", []):
                            comp_type = component_ref.get("idShort")
                            if comp_type in used_components:
                                for prop in component_ref.get("value", []):
                                    prop_id = prop.get("idShort")
                                    if prop_id in used_components[comp_type]:
                                        prop["value"] = used_components[comp_type][prop_id]
        return submodel

    def _get_next_instance_num(self, asset_key: str) -> str:
        """Scan the instance shell directory and return the next available 3-digit instance number."""
        cfg = ASSET_REGISTRY[asset_key]
        instance_dir = self.base_path / cfg["instance_shell_dir"]
        prefix = cfg["instance_file_prefix"]
        max_num = 0
        if instance_dir.exists():
            for f in instance_dir.glob(f"{prefix}-???.json"):
                try:
                    max_num = max(max_num, int(f.stem.split("-")[-1]))
                except ValueError:
                    pass
        return f"{max_num + 1:03d}"

    def find_available_instances(
        self,
        model_numbers_needed: Dict[str, str],
        conn: sqlite3.Connection,
    ) -> Dict[str, Dict[str, str]]:
        """
        Find available component instances for each model number needed.
        Uses the provided connection so the caller holds the transaction lock,
        preventing another assembly from grabbing the same instances.
        Returns: {component_type: {instance_id, instance_number, model_number}}
        """
        available_instances = {}
        already_selected: set = set()  # Track instance_ids already picked to avoid duplicates

        for comp_type, model_num in model_numbers_needed.items():
            if already_selected:
                placeholders = ",".join("?" * len(already_selected))
                row = conn.execute(
                    f"SELECT instance_id, instance_number, model_number FROM inventory_items "
                    f"WHERE model_number = ? AND status = 'available' AND instance_id NOT IN ({placeholders}) LIMIT 1",
                    (model_num, *already_selected),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT instance_id, instance_number, model_number FROM inventory_items "
                    "WHERE model_number = ? AND status = 'available' LIMIT 1",
                    (model_num,),
                ).fetchone()

            if not row:
                raise Exception(
                    f"No available {comp_type} instance for model {model_num}. "
                    f"(Components may have been consumed by another order since this order was created.)"
                )

            available_instances[comp_type] = {
                "instance_id": row["instance_id"],
                "instance_number": row["instance_number"],
                "model_number": row["model_number"],
            }
            already_selected.add(row["instance_id"])

        return available_instances

    # =========================================================================
    # Prerequisite validation helpers
    # =========================================================================

    def _check_components_reserved(
        self,
        reserved: Dict,
        component_keys: List[str],
        conn: sqlite3.Connection,
    ) -> None:
        """
        Verify that each named component still has status='reserved' in the DB.
        Raises a descriptive exception if any are missing or already consumed.
        """
        errors = []
        for key in component_keys:
            inst = reserved.get(key)
            if not inst:
                errors.append(f"  ✗ {key}: not found in reserved instances")
                continue
            row = conn.execute(
                "SELECT status FROM inventory_items WHERE instance_id = ?",
                (inst["instance_id"],),
            ).fetchone()
            if not row:
                errors.append(
                    f"  ✗ {key} (instance {inst['instance_number']}): "
                    f"not found in inventory DB"
                )
            elif row["status"] != "reserved":
                errors.append(
                    f"  ✗ {key} (instance {inst['instance_number']}): "
                    f"status is '{row['status']}', expected 'reserved'"
                )
        if errors:
            raise Exception(
                "Cannot proceed — required components are not available:\n"
                + "\n".join(errors)
            )

    def _check_subassembly_files_exist(
        self,
        asset_key: str,
        instance_num: str,
    ) -> None:
        """
        Verify that the shell and all submodel JSON files for a sub-assembly
        instance actually exist on disk (created by a previous step).
        Raises a descriptive exception if any are missing.
        """
        cfg = ASSET_REGISTRY[asset_key]
        missing = []

        shell_path = (
            self.base_path
            / cfg["instance_shell_dir"]
            / f"{cfg['instance_file_prefix']}-{instance_num}.json"
        )
        if not shell_path.exists():
            missing.append(str(shell_path.name))

        for sm_name in cfg["submodels"]:
            sm_path = (
                self.base_path
                / cfg["instance_submodels_dir"]
                / f"{cfg['instance_file_prefix']}-{instance_num}-{sm_name}.json"
            )
            if not sm_path.exists():
                missing.append(str(sm_path.name))

        if missing:
            raise Exception(
                f"Cannot proceed — {asset_key} instance {instance_num} "
                f"files are missing on disk:\n"
                + "\n".join(f"  ✗ {f}" for f in missing)
            )

    # =========================================================================
    # Three-step assembly (each step corresponds to a physical assembly station)
    # =========================================================================

    def assemble_step1_housing(self, order_id: str) -> str:
        """
        ASSEMBLY STEP 1 — Station 1: Bottom_Cover + PCB → Housing_With_PCB.

        Consumes: Bottom_Cover, PCB
        Creates:  Housing_With_PCB sub-assembly instance
        Status transition: pending → step1_done
        Returns: Housing_With_PCB instance number
        """
        conn = _get_connection(str(self.base_path / self.db_path))
        _create_tables(conn)

        order = conn.execute(
            "SELECT * FROM configuration_orders WHERE order_id = ?", (order_id,)
        ).fetchone()
        if not order:
            conn.close()
            raise Exception(f"Order not found: {order_id}")
        if order["status"] != "pending":
            conn.close()
            raise Exception(
                f"Step 1 requires status 'pending'. Order {order_id} is '{order['status']}'."
            )

        reserved = json.loads(order["reserved_instances"])
        order_config = json.loads(order["configuration"])
        order_config["number_of_fuses"] = sum(1 for k in reserved if k.startswith("Fuse"))
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ── Prerequisite check ────────────────────────────────────────────────
        print(f"\nChecking prerequisites for Step 1 (order {order_id})...")
        self._check_components_reserved(reserved, ["Bottom_Cover", "PCB"], conn)
        print("  ✓ Bottom_Cover — reserved and available")
        print("  ✓ PCB          — reserved and available")

        print(f"\n── STEP 1 (Station 1): Housing_With_PCB — order {order_id} ──")
        print(f"  Bottom_Cover : {reserved['Bottom_Cover']['model_number']} "
              f"(instance {reserved['Bottom_Cover']['instance_number']})")
        print(f"  PCB          : {reserved['PCB']['model_number']} "
              f"(instance {reserved['PCB']['instance_number']})")

        hwp_num = self._get_next_instance_num("Housing_With_PCB")
        hwp_id = self._create_asset_instance("Housing_With_PCB", hwp_num, order_config)
        print(f"  ✓ Created Housing_With_PCB instance {hwp_num}: {hwp_id}")

        # Consume Bottom_Cover and PCB at this station
        for comp in ("Bottom_Cover", "PCB"):
            conn.execute(
                "UPDATE inventory_items SET status = 'consumed', last_updated = ? WHERE instance_id = ?",
                (now, reserved[comp]["instance_id"]),
            )
            print(f"  ✓ Consumed {comp} instance {reserved[comp]['instance_number']}")

        progress = {"housing_with_pcb_num": hwp_num, "housing_with_pcb_id": hwp_id}
        conn.execute(
            "UPDATE configuration_orders SET status = 'step1_done', assembly_progress = ? WHERE order_id = ?",
            (json.dumps(progress), order_id),
        )
        conn.commit()
        conn.close()

        print(f"\n✓ Step 1 complete — order {order_id} ready for Step 2.\n")
        return hwp_num

    def assemble_step2_pcb_fuse(self, order_id: str) -> str:
        """
        ASSEMBLY STEP 2 — Station 2: Housing_With_PCB + Fuses → PCB_With_Fuse.

        Consumes: all Fuse instances
        Creates:  PCB_With_Fuse sub-assembly instance
        Status transition: step1_done → step2_done
        Returns: PCB_With_Fuse instance number
        """
        conn = _get_connection(str(self.base_path / self.db_path))
        _create_tables(conn)

        order = conn.execute(
            "SELECT * FROM configuration_orders WHERE order_id = ?", (order_id,)
        ).fetchone()
        if not order:
            conn.close()
            raise Exception(f"Order not found: {order_id}")
        if order["status"] != "step1_done":
            conn.close()
            raise Exception(
                f"Step 2 requires status 'step1_done'. Order {order_id} is '{order['status']}'."
                " Run Step 1 first."
            )

        reserved = json.loads(order["reserved_instances"])
        order_config = json.loads(order["configuration"])
        progress = json.loads(order["assembly_progress"])
        fuse_keys = sorted(k for k in reserved if k.startswith("Fuse"))
        order_config["number_of_fuses"] = len(fuse_keys)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ── Prerequisite check ────────────────────────────────────────────────
        print(f"\nChecking prerequisites for Step 2 (order {order_id})...")
        self._check_subassembly_files_exist("Housing_With_PCB", progress["housing_with_pcb_num"])
        print(f"  ✓ Housing_With_PCB instance {progress['housing_with_pcb_num']} — files present")
        self._check_components_reserved(reserved, fuse_keys, conn)
        for fk in fuse_keys:
            print(f"  ✓ {fk} — reserved and available")

        print(f"\n── STEP 2 (Station 2): PCB_With_Fuse — order {order_id} ──")
        print(f"  Housing_With_PCB : instance {progress['housing_with_pcb_num']}")
        for fk in fuse_keys:
            print(f"  {fk:<16} : {reserved[fk]['model_number']} "
                  f"(instance {reserved[fk]['instance_number']})")

        pwf_num = self._get_next_instance_num("PCB_With_Fuse")
        pwf_id = self._create_asset_instance("PCB_With_Fuse", pwf_num, order_config)
        print(f"  ✓ Created PCB_With_Fuse instance {pwf_num}: {pwf_id}")

        # Consume all Fuses at this station
        for fk in fuse_keys:
            conn.execute(
                "UPDATE inventory_items SET status = 'consumed', last_updated = ? WHERE instance_id = ?",
                (now, reserved[fk]["instance_id"]),
            )
            print(f"  ✓ Consumed {fk} instance {reserved[fk]['instance_number']}")

        progress["pcb_with_fuse_num"] = pwf_num
        progress["pcb_with_fuse_id"] = pwf_id
        conn.execute(
            "UPDATE configuration_orders SET status = 'step2_done', assembly_progress = ? WHERE order_id = ?",
            (json.dumps(progress), order_id),
        )
        conn.commit()
        conn.close()

        print(f"\n✓ Step 2 complete — order {order_id} ready for Step 3.\n")
        return pwf_num

    def assemble_step3_final(self, order_id: str) -> str:
        """
        ASSEMBLY STEP 3 — Station 3: PCB_With_Fuse + Top_Cover → Final Telefon.

        Consumes: Top_Cover
        Creates:  Final Telefon product instance
        Status transition: step2_done → assembled
        Returns: product_instance_id
        """
        conn = _get_connection(str(self.base_path / self.db_path))
        _create_tables(conn)

        order = conn.execute(
            "SELECT * FROM configuration_orders WHERE order_id = ?", (order_id,)
        ).fetchone()
        if not order:
            conn.close()
            raise Exception(f"Order not found: {order_id}")
        if order["status"] != "step2_done":
            conn.close()
            raise Exception(
                f"Step 3 requires status 'step2_done'. Order {order_id} is '{order['status']}'."
                " Run Steps 1 and 2 first."
            )

        reserved = json.loads(order["reserved_instances"])
        progress = json.loads(order["assembly_progress"])
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ── Prerequisite check ────────────────────────────────────────────────
        print(f"\nChecking prerequisites for Step 3 (order {order_id})...")
        self._check_subassembly_files_exist("PCB_With_Fuse", progress["pcb_with_fuse_num"])
        print(f"  ✓ PCB_With_Fuse instance {progress['pcb_with_fuse_num']} — files present")
        self._check_components_reserved(reserved, ["Top_Cover"], conn)
        print("  ✓ Top_Cover    — reserved and available")

        print(f"\n── STEP 3 (Station 3): Final Telefon — order {order_id} ──")
        print(f"  PCB_With_Fuse : instance {progress['pcb_with_fuse_num']}")
        print(f"  Top_Cover     : {reserved['Top_Cover']['model_number']} "
              f"(instance {reserved['Top_Cover']['instance_number']})")

        assembled_count = conn.execute(
            "SELECT COUNT(*) FROM configuration_orders WHERE status = 'assembled'"
        ).fetchone()[0]
        product_instance_num = f"{assembled_count + 1:03d}"

        print(f"\nCreating final product instance {product_instance_num}...")
        product_instance_id = self._create_asset_instance("Telefon", product_instance_num)
        print(f"  ✓ Created instance: {product_instance_id}")

        # Fill Assembly_Traceability
        cfg = ASSET_REGISTRY["Telefon"]
        doc_file = (
            self.base_path
            / cfg["instance_submodels_dir"]
            / f"{cfg['instance_file_prefix']}-{product_instance_num}-Documentation.json"
        )
        with open(doc_file, encoding="utf-8") as f:
            documentation = json.load(f)
        documentation = self._patch_assembly_traceability(
            documentation, order_id, now, reserved
        )
        with open(doc_file, "w", encoding="utf-8") as f:
            json.dump(documentation, f, indent=2, ensure_ascii=False)
        print("  ✓ Filled Assembly_Traceability")

        # Consume Top_Cover at this station
        conn.execute(
            "UPDATE inventory_items SET status = 'consumed', last_updated = ? WHERE instance_id = ?",
            (now, reserved["Top_Cover"]["instance_id"]),
        )
        print(f"  ✓ Consumed Top_Cover instance {reserved['Top_Cover']['instance_number']}")

        conn.execute(
            "UPDATE configuration_orders SET status = 'assembled', assembled_date = ?, "
            "assembly_progress = ? WHERE order_id = ?",
            (now, json.dumps(progress), order_id),
        )
        conn.commit()
        conn.close()

        print(f"\n✓ Step 3 complete — order {order_id} fully assembled.")
        print(f"  Product Instance ID: {product_instance_id}")
        print(f"  Assembly Date: {now}\n")
        return product_instance_id

    # =========================================================================
    # Convenience: run all 3 steps in sequence
    # =========================================================================

    def assemble_from_order(self, order_id: str) -> str:
        """
        Run all 3 assembly steps in sequence (stations 1 → 2 → 3).
        Equivalent to running --assemble-step1, --assemble-step2, --assemble-step3 in order.
        Returns: product_instance_id
        """
        self.assemble_step1_housing(order_id)
        self.assemble_step2_pcb_fuse(order_id)
        return self.assemble_step3_final(order_id)

    def list_pending_orders(self) -> List[Dict]:
        """List all orders that still need assembly work (pending or in progress)."""
        conn = _get_connection(str(self.base_path / self.db_path))
        orders = conn.execute(
            "SELECT * FROM configuration_orders "
            "WHERE status IN ('pending', 'step1_done', 'step2_done') ORDER BY created_date"
        ).fetchall()
        conn.close()
        return [dict(order) for order in orders]

    def list_all_orders(self) -> List[Dict]:
        """List all orders."""
        conn = _get_connection(str(self.base_path / self.db_path))
        orders = conn.execute(
            "SELECT * FROM configuration_orders ORDER BY created_date DESC"
        ).fetchall()
        conn.close()

        return [dict(order) for order in orders]


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Assembly Manager for Configurator v3")
    parser.add_argument("--list-pending", action="store_true", help="List orders pending or in-progress")
    parser.add_argument("--list-all", action="store_true", help="List all orders")
    parser.add_argument("--assemble", type=str, metavar="ORDER_ID",
                        help="Run all 3 assembly steps in sequence for an order")
    parser.add_argument("--assemble-step1", type=str, metavar="ORDER_ID",
                        help="Step 1 — Station 1: Bottom_Cover + PCB → Housing_With_PCB")
    parser.add_argument("--assemble-step2", type=str, metavar="ORDER_ID",
                        help="Step 2 — Station 2: Housing_With_PCB + Fuses → PCB_With_Fuse")
    parser.add_argument("--assemble-step3", type=str, metavar="ORDER_ID",
                        help="Step 3 — Station 3: PCB_With_Fuse + Top_Cover → Final Telefon")
    args = parser.parse_args()

    workspace_path = Path(__file__).parent
    manager = AssemblyManager(str(workspace_path))

    # Step labels for display
    STEP_LABEL = {
        "pending":    "Awaiting Step 1",
        "step1_done": "Awaiting Step 2",
        "step2_done": "Awaiting Step 3",
        "assembled":  "Assembled",
        "cancelled":  "Cancelled",
    }

    if args.list_pending:
        orders = manager.list_pending_orders()
        if not orders:
            print("No pending or in-progress orders.")
            return
        print("\n" + "=" * 100)
        print("  ORDERS IN PROGRESS")
        print("=" * 100)
        print(f"  {'Order ID':<15} {'Product Type':<20} {'Next Action':<22} {'Created':<19}")
        print("-" * 100)
        for order in orders:
            label = STEP_LABEL.get(order["status"], order["status"])
            print(f"  {order['order_id']:<15} {order['product_type']:<20} {label:<22} {order['created_date']:<19}")
        print("=" * 100 + "\n")
        return

    if args.list_all:
        orders = manager.list_all_orders()
        if not orders:
            print("No orders found.")
            return
        print("\n" + "=" * 120)
        print("  ALL CONFIGURATION ORDERS")
        print("=" * 120)
        print(
            f"  {'Order ID':<15} {'Product Type':<20} {'Status':<22} "
            f"{'Created':<19} {'Assembled':<19}"
        )
        print("-" * 120)
        for order in orders:
            label = STEP_LABEL.get(order["status"], order["status"])
            assembled = order["assembled_date"] if order["assembled_date"] else ""
            print(
                f"  {order['order_id']:<15} {order['product_type']:<20} "
                f"{label:<22} {order['created_date']:<19} {assembled:<19}"
            )
        print("=" * 120 + "\n")
        return

    if args.assemble_step1:
        try:
            manager.assemble_step1_housing(args.assemble_step1)
        except Exception as e:
            print(f"Error: {e}")
        return

    if args.assemble_step2:
        try:
            manager.assemble_step2_pcb_fuse(args.assemble_step2)
        except Exception as e:
            print(f"Error: {e}")
        return

    if args.assemble_step3:
        try:
            manager.assemble_step3_final(args.assemble_step3)
        except Exception as e:
            print(f"Error: {e}")
        return

    if args.assemble:
        try:
            manager.assemble_from_order(args.assemble)
        except Exception as e:
            print(f"Error: {e}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
