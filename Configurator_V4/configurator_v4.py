"""
Telefon Product Configurator v4 — Phase 1: Order Placement

Key differences from v3:
  - ALL sub-assembly and final product shells are created when the order is placed.
  - Component shells already exist in physical inventory; we reserve them by
    model-type quantity (no specific instance is locked at order time).
  - BOM submodels are created with empty Instance_Reference fields; these are
    filled in during the assembly phase when the actual physical unit is used.
  - The final product (Telefon) Documentation submodel includes an Order_Reference.
  - At assembly time any available component of the correct model type can be used,
    or a specific instance_id can be provided (e.g. from a barcode or RFID scan).
"""

import json
import sqlite3
import re
import copy
import base64
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from inventory_db import (
    _create_tables, _get_connection, _rebuild_stock,
    _reserve_model_types, CONFIGURATOR_BASE, DEFAULT_DB_FILE,
)
from asset_registry import ASSET_REGISTRY, ORDER_TIME_SHELL_KEYS


# =============================================================================
# AAS Server defaults
# =============================================================================

DEFAULT_SERVER_BASE = "http://localhost:8081"


def _b64url(s: str) -> str:
    """Base64url-encode a string (no padding) for AAS REST path segments."""
    return base64.urlsafe_b64encode(s.encode()).rstrip(b"=").decode()


# =============================================================================
# Configurator class
# =============================================================================

class TelefonConfiguratorV4:
    """
    Phase 1 configurator.

    create_order(config) → (order_id, details):
      1. Validate configuration
      2. Check model-type stock
      3. Create Housing_With_PCB, PCB_With_Fuse, and Telefon shells upfront
         - BOMs have empty Instance_Reference fields (filled during assembly)
         - Telefon Documentation has Order_Reference
      4. Reserve model-type quantities (Bottom_Cover, Top_Cover, PCB, Fuse×N)
      5. Persist order to DB
    """

    def __init__(
        self,
        base_path: str = None,
        db_path: str = None,
        upload: bool = True,
        server_base: str = DEFAULT_SERVER_BASE,
    ):
        self.base_path = Path(base_path) if base_path else CONFIGURATOR_BASE
        self.db_path = db_path or DEFAULT_DB_FILE
        self.upload = upload
        self.server_base = server_base
        self._config_template = self._load_config_template()

    # -------------------------------------------------------------------------
    # AAS Server upload
    # -------------------------------------------------------------------------

    def _upload_to_server(self, shell: Dict, submodels: Dict[str, Dict]) -> None:
        """
        POST submodels then shell to the AAS server.
        These are brand-new resources created at order time, so POST is correct.
        """
        if not self.upload:
            return
        submodel_endpoint = f"{self.server_base}/submodels"
        shell_endpoint = f"{self.server_base}/shells"
        for sm_name, sm_data in submodels.items():
            try:
                r = requests.post(
                    submodel_endpoint, json=sm_data,
                    headers={"Content-Type": "application/json"}, timeout=5,
                )
                print(f"  {'OK' if r.ok else f'FAIL ({r.status_code})'} → server submodel: {sm_name}")
            except requests.ConnectionError:
                print(f"  ERROR → could not connect to AAS server at {self.server_base}")
                return
        try:
            r = requests.post(
                shell_endpoint, json=shell,
                headers={"Content-Type": "application/json"}, timeout=5,
            )
            print(f"  {'OK' if r.ok else f'FAIL ({r.status_code})'} → server shell: {shell.get('id', '')}")
        except requests.ConnectionError:
            print(f"  ERROR → could not connect to AAS server at {self.server_base}")

    # -------------------------------------------------------------------------
    # Configuration template
    # -------------------------------------------------------------------------

    def _load_config_template(self) -> Dict[str, Any]:
        path = (
            self.base_path
            / "JSON_Submodels"
            / "Product_Submodels_JSON"
            / "Final_Product_Submodels"
            / "Product-Final_Product-Telefon-Telefon_Pro_Max-Configuration_Template.json"
        )
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    # -------------------------------------------------------------------------
    # Model number derivation  (same logic as v3)
    # -------------------------------------------------------------------------

    def _get_model_numbers_for_config(self, config: Dict[str, Any]) -> Dict[str, str]:
        """Return {component_type: model_number} for all components in the config."""
        model_numbers = {}
        for asset_key, cfg in ASSET_REGISTRY.items():
            if not cfg.get("is_component", False):
                continue
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
                model_numbers[asset_key] = re.sub(
                    r"\{(\w+)\}",
                    lambda m: str(config.get(m.group(1), m.group(0))),
                    template,
                )
            else:
                for elem in doc.get("submodelElements", []):
                    if elem.get("idShort") == "Model_Number":
                        fixed = elem.get("value")
                        if fixed:
                            model_numbers[asset_key] = fixed
                        break

        return model_numbers

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    def validate_configuration(self, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        errors = []

        # Collect required config fields from all properties_config_maps in ASSET_REGISTRY.
        # Sub-assembly maps (e.g. Housing_With_PCB) share the same config keys as components,
        # so the union of all values covers the full required set.
        required: set = {
            config_key
            for cfg in ASSET_REGISTRY.values()
            for config_key in cfg.get("properties_config_map", {}).values()
        }
        for field in required:
            if field not in config:
                errors.append(f"Missing required field: {field}")

        for elem in self._config_template.get("submodelElements", []):
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

                        # Check compatibility for every component that has both Material and Finish.
                        for asset_cfg in ASSET_REGISTRY.values():
                            prop_map = asset_cfg.get("properties_config_map", {})
                            mat_key = prop_map.get("Material")
                            fin_key = prop_map.get("Finish")
                            if mat_key and fin_key and mat_key in config and fin_key in config:
                                if (config[mat_key], config[fin_key]) in incompatible:
                                    errors.append(
                                        f"Invalid: {config[mat_key]} cannot be {config[fin_key]}"
                                    )

        return len(errors) == 0, errors

    def check_inventory(self, config: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Check effective available stock (inventory_items minus pending model-type reservations).
        Returns (all_available, {component_type: status_dict}).
        """
        model_numbers = self._get_model_numbers_for_config(config)
        conn = _get_connection(self.db_path)
        _create_tables(conn)
        _rebuild_stock(conn)   # ensures model_type_reservations are factored in

        inventory_status = {}
        all_available = True

        for comp_type, model_num in model_numbers.items():
            qty_cfg_key = ASSET_REGISTRY.get(comp_type, {}).get("quantity_config_key")
            qty_needed = config.get(qty_cfg_key, 1) if qty_cfg_key else 1
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

    def _get_available_options(self) -> Dict[str, Any]:
        """
        Return available configuration options, driven entirely by ASSET_REGISTRY.

        For each is_component entry:
          - If it has a quantity_config_key + options_count_key, emit a count dict
            (e.g. fuse_counts: {1: total, 2: total, ...}).
          - If it has Material/Color/Finish in properties_config_map, emit a combos
            list (e.g. bottom_cover_combos: [{material, color, finish, qty}, ...]).
            These are read directly from inventory_stock.component_type, avoiding
            any model-number string parsing.
        """
        conn = _get_connection(self.db_path)
        _create_tables(conn)
        _rebuild_stock(conn)

        # Maps AAS property idShort to inventory_stock column name.
        PROP_TO_DB_COL: Dict[str, str] = {
            "Material": "material",
            "Color": "color",
            "Finish": "finish",
        }

        available: Dict[str, Any] = {}

        for asset_key, asset_cfg in ASSET_REGISTRY.items():
            if not asset_cfg.get("is_component"):
                continue

            qty_cfg_key = asset_cfg.get("quantity_config_key")
            options_count_key = asset_cfg.get("options_count_key")

            # --- Count-based component (e.g. Fuse) ---
            if qty_cfg_key and options_count_key:
                row = conn.execute(
                    "SELECT SUM(qty_available) as total FROM inventory_stock "
                    "WHERE component_type = ? AND qty_available > 0",
                    (asset_key,),
                ).fetchone()
                total = int(row["total"]) if row and row["total"] else 0
                available[options_count_key] = {n: total for n in range(1, min(total + 1, 6))}
                continue

            # --- Attribute-option component (e.g. Bottom_Cover, Top_Cover) ---
            prop_map = asset_cfg.get("properties_config_map", {})
            attr_props = {p: col for p, col in PROP_TO_DB_COL.items() if p in prop_map}
            if not attr_props:
                continue  # e.g. PCB has no configurable attributes

            combos_key = f"{asset_key.lower()}_combos"
            combos: List[Dict[str, Any]] = []

            for row in conn.execute(
                "SELECT material, color, finish, qty_available FROM inventory_stock "
                "WHERE component_type = ? AND qty_available > 0",
                (asset_key,),
            ).fetchall():
                combo: Dict[str, Any] = {"qty": row["qty_available"]}
                for db_col in attr_props.values():
                    val = row[db_col]
                    if val is not None:
                        combo[db_col] = val
                combos.append(combo)

            available[combos_key] = combos

        conn.close()
        return available

    # -------------------------------------------------------------------------
    # Shell creation helpers
    # -------------------------------------------------------------------------

    def _load_type_shell(self, asset_key: str) -> Dict[str, Any]:
        path = self.base_path / ASSET_REGISTRY[asset_key]["type_shell"]
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _load_type_submodel(self, asset_key: str, submodel_name: str) -> Dict[str, Any]:
        cfg = ASSET_REGISTRY[asset_key]
        filename = f"{cfg['type_submodel_prefix']}-Type-{submodel_name}.json"
        path = self.base_path / cfg["type_submodels_dir"] / filename
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _save_json(self, rel_dir: str, filename: str, data: Dict[str, Any]) -> Path:
        out_path = self.base_path / rel_dir / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return out_path

    def _type_to_instance(self, doc: Dict, instance_num: str) -> Dict:
        """Replace /Type/ and /Type" with the instance number in all IDs."""
        text = json.dumps(doc)
        text = text.replace("/Type/", f"/{instance_num}/")
        text = text.replace('/Type"', f'/{instance_num}"')
        return json.loads(text)

    def _patch_shell(self, shell: Dict, asset_key: str) -> Dict:
        shell["assetInformation"]["assetKind"] = "Instance"
        shell["idShort"] = asset_key
        return shell

    def _patch_documentation(
        self,
        submodel: Dict,
        instance_num: str,
        config: Dict = None,
    ) -> Dict:
        """Set Instance_Number, Created_Date, Model_Number; remove Model_Number_Configuration."""
        elements = submodel.get("submodelElements", [])
        model_number = None

        for elem in elements:
            if elem.get("idShort") == "Model_Number_Configuration" and config:
                for child in elem.get("value", []):
                    if child.get("idShort") == "Template":
                        model_number = re.sub(
                            r"\{(\w+)\}",
                            lambda m: str(config.get(m.group(1), m.group(0))),
                            child.get("value", ""),
                        )
                break

        submodel["submodelElements"] = [
            e for e in elements if e.get("idShort") != "Model_Number_Configuration"
        ]
        for elem in submodel.get("submodelElements", []):
            if elem.get("idShort") == "Instance_Number":
                elem["value"] = instance_num
            elif elem.get("idShort") == "Created_Date":
                elem["value"] = datetime.now().strftime("%Y-%m-%d")
            elif elem.get("idShort") == "Model_Number" and model_number:
                elem["value"] = model_number

        return submodel

    def _add_order_reference(self, doc_submodel: Dict, order_id: str) -> Dict:
        """Inject Order_Reference into the Telefon Documentation submodel."""
        elements = doc_submodel.get("submodelElements", [])
        for elem in elements:
            if elem.get("idShort") == "Order_Reference":
                elem["value"] = order_id
                return doc_submodel
        elements.append({
            "modelType": "Property",
            "idShort": "Order_Reference",
            "valueType": "xs:string",
            "value": order_id,
            "description": [{"language": "en", "text": "Production order that this product was manufactured against"}],
        })
        return doc_submodel

    def _patch_properties(
        self,
        submodel: Dict,
        asset_key: str,
        config: Dict,
    ) -> Dict:
        """
        Fill Property values inside List_Of_Properties using the asset's
        properties_config_map: {idShort -> config_key} and
        static_properties: {idShort -> fixed_value}.
        """
        prop_map = ASSET_REGISTRY[asset_key].get("properties_config_map", {})
        static_map = ASSET_REGISTRY[asset_key].get("static_properties", {})
        if not prop_map and not static_map:
            return submodel
        for elem in submodel.get("submodelElements", []):
            if elem.get("idShort") != "List_Of_Properties":
                continue
            for prop in elem.get("value", []):
                id_short = prop.get("idShort")
                config_key = prop_map.get(id_short)
                if config_key and config_key in config:
                    prop["value"] = str(config[config_key])
                elif id_short in static_map:
                    prop["value"] = static_map[id_short]
        return submodel

    def _add_empty_instance_refs_to_bom(self, bom_submodel: Dict, n_fuses: int = 1) -> Dict:
        """
        Walk the BOM Components list and add Instance_Reference: '' to each slot.
        For the Fuse slot, Instance_Reference_1..N are added based on n_fuses.
        These are the placeholders that get filled during the assembly phase.
        """
        for elem in bom_submodel.get("submodelElements", []):
            if elem.get("idShort") != "Components":
                continue
            for slot in elem.get("value", []):
                slot_props = slot.setdefault("value", [])
                slot_id = slot.get("idShort", "")

                if slot_id == "Fuse":
                    # Replace Quantity_Min/Max with the concrete Quantity for this instance
                    slot_props[:] = [
                        p for p in slot_props
                        if p.get("idShort") not in ("Quantity_Min", "Quantity_Max")
                    ]
                    if not any(p.get("idShort") == "Quantity" for p in slot_props):
                        # Insert Quantity right after Component_Type
                        insert_at = next(
                            (i + 1 for i, p in enumerate(slot_props) if p.get("idShort") == "Component_Type"),
                            len(slot_props),
                        )
                        slot_props.insert(insert_at, {
                            "modelType": "Property",
                            "idShort": "Quantity",
                            "valueType": "xs:integer",
                            "value": str(n_fuses),
                            "description": [{"language": "en", "text": "Number of fuses required for this specific instance."}],
                        })
                    else:
                        # Update existing Quantity if already present
                        for p in slot_props:
                            if p.get("idShort") == "Quantity":
                                p["value"] = str(n_fuses)
                    # Add exactly n_fuses Instance_Reference slots, remove any extras
                    slot_props[:] = [p for p in slot_props if not p.get("idShort", "").startswith("Instance_Reference_")]
                    for i in range(1, n_fuses + 1):
                        slot_props.append({
                            "modelType": "Property",
                            "idShort": f"Instance_Reference_{i}",
                            "valueType": "xs:string",
                            "value": "",
                            "description": [{"language": "en", "text": f"AAS ID of fuse instance #{i} used during assembly. Filled during production."}],
                        })
                else:
                    if not any(p.get("idShort") == "Instance_Reference" for p in slot_props):
                        slot_props.append({
                            "modelType": "Property",
                            "idShort": "Instance_Reference",
                            "valueType": "xs:string",
                            "value": "",
                            "description": [{"language": "en", "text": "AAS ID of the physical instance used during assembly. Filled during production."}],
                        })
        return bom_submodel

    def _get_next_instance_num(self, asset_key: str) -> str:
        """Scan the instance shell directory and return the next 3-digit instance number."""
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

    def _create_sa_or_product_shell(
        self,
        asset_key: str,
        instance_num: str,
        config: Dict,
    ) -> str:
        """
        Create the shell JSON and all submodel JSONs for a sub-assembly or
        final product from its Type template.

        For BOM submodels: empty Instance_Reference fields are injected.
        For Telefon Documentation: Order_Reference is injected.

        Returns the instance AAS ID.
        """
        cfg = ASSET_REGISTRY[asset_key]
        n_fuses = config.get("number_of_fuses", 1)

        # Shell
        shell = self._type_to_instance(
            copy.deepcopy(self._load_type_shell(asset_key)), instance_num
        )
        shell = self._patch_shell(shell, asset_key)
        self._save_json(
            cfg["instance_shell_dir"],
            f"{cfg['instance_file_prefix']}-{instance_num}.json",
            shell,
        )
        instance_id: str = shell["id"]

        # Submodels
        order_id = config.get("_order_id", "")   # injected by create_order before calling here
        submodels: Dict[str, Dict] = {}
        for sm_name in cfg["submodels"]:
            sm = self._type_to_instance(
                copy.deepcopy(self._load_type_submodel(asset_key, sm_name)),
                instance_num,
            )

            if sm_name == "Documentation":
                sm = self._patch_documentation(sm, instance_num, config)
                if asset_key == "Telefon" and order_id:
                    sm = self._add_order_reference(sm, order_id)

            elif sm_name == "Bill_Of_Materials":
                sm = self._add_empty_instance_refs_to_bom(sm, n_fuses=n_fuses)

            elif sm_name == "Properties":
                sm = self._patch_properties(sm, asset_key, config)

            self._save_json(
                cfg["instance_submodels_dir"],
                f"{cfg['instance_file_prefix']}-{instance_num}-{sm_name}.json",
                sm,
            )
            submodels[sm_name] = sm

        # Upload new shell + submodels to AAS server
        if self.upload:
            print(f"  Uploading {asset_key} instance {instance_num} to AAS server ({self.server_base})...")
            self._upload_to_server(shell, submodels)

        return instance_id

    # -------------------------------------------------------------------------
    # Phase 1 entry point
    # -------------------------------------------------------------------------

    def create_order(self, config: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        Create a production order:
          1. Validate configuration & check stock
          2. Allocate an order ID
          3. Create Housing_With_PCB, PCB_With_Fuse, and Telefon shells upfront
          4. Reserve model-type quantities for all required components
          5. Persist order to DB

        Returns (order_id, order_details).
        """
        # --- Validate ---
        is_valid, errors = self.validate_configuration(config)
        if not is_valid:
            raise ValueError(f"Invalid configuration: {', '.join(errors)}")

        in_stock, inventory_status = self.check_inventory(config)
        if not in_stock:
            unavailable = [
                st["model_number"] for st in inventory_status.values() if not st["in_stock"]
            ]
            raise ValueError(f"Insufficient stock for: {', '.join(unavailable)}")

        model_numbers = self._get_model_numbers_for_config(config)

        # --- Allocate order ID ---
        conn = _get_connection(self.db_path)
        _create_tables(conn)

        last_order = conn.execute(
            "SELECT order_id FROM configuration_orders ORDER BY order_id DESC LIMIT 1"
        ).fetchone()
        order_num = 1
        if last_order:
            try:
                order_num = int(last_order["order_id"].split("-")[1]) + 1
            except (IndexError, ValueError):
                pass
        order_id = f"ORD-{order_num:03d}"

        # --- Create shells for sub-assemblies and final product ---
        print(f"\n── V4 Order {order_id}: creating shells ──")
        shell_instances: Dict[str, str] = {}
        config_with_order = {**config, "_order_id": order_id}

        for asset_key in ORDER_TIME_SHELL_KEYS:
            inst_num = self._get_next_instance_num(asset_key)
            inst_id = self._create_sa_or_product_shell(asset_key, inst_num, config_with_order)
            shell_instances[asset_key] = inst_num
            print(f"  ✓ {asset_key:<20} instance {inst_num}  ({inst_id})")

        # --- Reserve model-type quantities for components ---
        # Components with a quantity_config_key (e.g. Fuse) get one reservation slot
        # per unit required, so each physical instance maps to exactly one slot.
        reservation_slots: Dict[str, str] = {}
        for comp_type, model_num in model_numbers.items():
            qty_cfg_key = ASSET_REGISTRY.get(comp_type, {}).get("quantity_config_key")
            if qty_cfg_key:
                qty = config.get(qty_cfg_key, 1)
                for i in range(1, qty + 1):
                    reservation_slots[f"{comp_type}_{i}"] = model_num
            else:
                reservation_slots[comp_type] = model_num

        _reserve_model_types(conn, order_id, reservation_slots)
        print(f"  ✓ Reserved model-type quantities: {list(reservation_slots.keys())}")

        # --- Persist order ---
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        product_type = ASSET_REGISTRY.get("Telefon", {}).get("registry_key", "Unknown")
        conn.execute("""
            INSERT INTO configuration_orders (
                order_id, product_type, configuration, model_numbers_needed,
                shell_instances, status, created_date
            ) VALUES (?, ?, ?, ?, ?, 'pending', ?)
        """, (
            order_id,
            product_type,
            json.dumps(config),
            json.dumps(model_numbers),
            json.dumps(shell_instances),
            now,
        ))
        conn.commit()
        _rebuild_stock(conn)
        conn.close()

        print(f"\n✓ Order {order_id} created — shells ready, components reserved by model type.\n")

        return order_id, {
            "order_id": order_id,
            "product_type": product_type,
            "configuration": config,
            "model_numbers_needed": model_numbers,
            "shell_instances": shell_instances,
            "reservation_slots": reservation_slots,
            "inventory_status": inventory_status,
            "created_date": now,
            "status": "pending",
        }


# =============================================================================
# CLI  (for quick testing)
# =============================================================================

EXAMPLE_ORDERS = [
    {
        "bottom_cover_material": "PLA-31212", "bottom_cover_color": "Red",   "bottom_cover_finish": "Glossy",
        "top_cover_material":    "PLA-31212", "top_cover_color":    "Red",   "top_cover_finish":    "Glossy",
        "number_of_fuses": 1,
    },
    {
        "bottom_cover_material": "PLA-31212", "bottom_cover_color": "Blue",  "bottom_cover_finish": "Glossy",
        "top_cover_material":    "PLA-31212", "top_cover_color":    "Blue",  "top_cover_finish":    "Glossy",
        "number_of_fuses": 2,
    },
]


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Telefon Configurator V4")
    parser.add_argument("--create-order", type=int, metavar="N",
                        help="Create order using EXAMPLE_ORDERS[N] (0-based)")
    parser.add_argument("--list-options", action="store_true",
                        help="Show available configuration options")
    args = parser.parse_args()

    cfg = TelefonConfiguratorV4()

    if args.list_options:
        opts = cfg._get_available_options()
        print(json.dumps(
            {k: v if not isinstance(v, dict) or not any(isinstance(k2, tuple) for k2 in v)
             else {str(k2): v2 for k2, v2 in v.items()}
             for k, v in opts.items()},
            indent=2
        ))
        return

    if args.create_order is not None:
        idx = args.create_order
        if idx < 0 or idx >= len(EXAMPLE_ORDERS):
            print(f"Index out of range. Available: 0–{len(EXAMPLE_ORDERS)-1}")
            return
        order_id, details = cfg.create_order(EXAMPLE_ORDERS[idx])
        print(f"Order ID : {order_id}")
        print(f"Shells   : {details['shell_instances']}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
