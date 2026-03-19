"""
Assembly Manager V4 — Phase 2: Instance Binding & BOM Patching

Operates on orders created by TelefonConfiguratorV4.
The shells (Bottom_Cover-PCB, Bottom_Cover-PCB-Fuse, Telefon) already exist on disk
from order-placement time.  Each assembly step:
  1. Picks a physical component instance (auto-selects first available OR
     accepts an explicit instance_id, e.g. from a barcode / RFID scan).
  2. Marks that inventory_items row as 'consumed'.
  3. Fulfils the corresponding model_type_reservation.
  4. Patches the pre-created BOM JSON file with the actual Instance_Reference.

Assembly steps mirror the physical production stations:
    Step 1 (Station 1) : Bottom_Cover  + PCB         -> Bottom_Cover-PCB
    Step 2 (Station 2) : Fuse(s)                     -> Bottom_Cover-PCB-Fuse
  Step 3 (Station 3) : Top_Cover + sub-assemblies  → Final Telefon

All steps are individually callable via the API, or run in sequence via
assemble_all().
"""

import json
import sqlite3
import base64
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from inventory_db import (
    _create_tables, _get_connection, _rebuild_stock,
    _fulfill_reservation, _cancel_order_reservations,
    AAS_FILES_BASE, DEFAULT_DB_FILE,
)
from asset_registry import ASSET_REGISTRY


# =============================================================================
# AAS Server defaults
# =============================================================================

DEFAULT_SERVER_BASE = "http://localhost:8081"


def _b64url(s: str) -> str:
    """Base64url-encode a string (no padding) for AAS REST path segments."""
    return base64.urlsafe_b64encode(s.encode()).rstrip(b"=").decode()


# =============================================================================
# Assembly Manager
# =============================================================================

class AssemblyManagerV4:
    """Phase 2: bind physical component instances to pre-created order shells."""

    def __init__(
        self,
        base_path: str = None,
        db_path: str = None,
        upload: bool = True,
        server_base: str = DEFAULT_SERVER_BASE,
    ):
        self.base_path = Path(base_path) if base_path else AAS_FILES_BASE
        self.db_path = db_path or DEFAULT_DB_FILE
        self.upload = upload
        self.server_base = server_base

    # -------------------------------------------------------------------------
    # Config / ID helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _inst_num_from_id(asset_id: str) -> str:
        """Extract the 3-digit instance number from a full asset ID (last path segment)."""
        return asset_id.rstrip("/").split("/")[-1]

    # -------------------------------------------------------------------------
    # AAS Server update
    # -------------------------------------------------------------------------

    def _update_submodel_on_server(self, submodel_path: Path) -> None:
        """
        PUT a submodel JSON file back to the AAS server.
        Used after BOM patching to push the filled Instance_Reference values.
        """
        if not self.upload:
            return
        with open(submodel_path, encoding="utf-8") as f:
            sm_data = json.load(f)
        sm_id = sm_data.get("id", "")
        url = f"{self.server_base}/submodels/{_b64url(sm_id)}"
        try:
            r = requests.put(
                url, json=sm_data,
                headers={"Content-Type": "application/json"}, timeout=5,
            )
            print(f"  {'OK' if r.ok else f'FAIL ({r.status_code})'} -> server UPDATE BOM: {submodel_path.name}")
        except requests.ConnectionError:
            print(f"  ERROR -> could not connect to AAS server at {self.server_base}")

    # -------------------------------------------------------------------------
    # Instance picking
    # -------------------------------------------------------------------------

    def _pick_instance(
        self,
        model_number: str,
        override_instance_id: Optional[str],
        already_picked: set,
        conn: sqlite3.Connection,
    ) -> Dict[str, str]:
        """
        Return an available inventory_items row for the given model_number.

        If override_instance_id is provided (e.g. from a barcode or RFID scan)
        it is validated against the model_number and must have status 'available'.
        Otherwise the first available instance is auto-selected.

        Raises an exception if no suitable instance is found.
        """
        if override_instance_id:
            row = conn.execute(
                "SELECT instance_id, instance_number, model_number, status "
                "FROM inventory_items WHERE instance_id = ?",
                (override_instance_id,),
            ).fetchone()
            if not row:
                raise Exception(f"Instance not found in inventory: {override_instance_id}")
            if row["model_number"] != model_number:
                raise Exception(
                    f"Instance {override_instance_id} is model '{row['model_number']}', "
                    f"expected '{model_number}'."
                )
            if row["status"] != "available":
                raise Exception(
                    f"Instance {override_instance_id} has status '{row['status']}', "
                    f"must be 'available'."
                )
            if override_instance_id in already_picked:
                raise Exception(f"Instance {override_instance_id} already picked in this step.")
            return dict(row)

        # Auto-pick first available, excluding already-picked in this call
        if already_picked:
            placeholders = ",".join("?" * len(already_picked))
            row = conn.execute(
                f"SELECT instance_id, instance_number, model_number "
                f"FROM inventory_items "
                f"WHERE model_number = ? AND status = 'available' "
                f"AND instance_id NOT IN ({placeholders}) LIMIT 1",
                (model_number, *already_picked),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT instance_id, instance_number, model_number "
                "FROM inventory_items "
                "WHERE model_number = ? AND status = 'available' LIMIT 1",
                (model_number,),
            ).fetchone()

        if not row:
            raise Exception(
                f"No available instance for model '{model_number}'. "
                "Check inventory stock or provide an explicit instance_id."
            )
        return dict(row)

    def _consume_instance(
        self,
        instance_id: str,
        conn: sqlite3.Connection,
        now: str,
    ) -> None:
        """Mark an inventory_items row as 'consumed'."""
        conn.execute(
            "UPDATE inventory_items SET status = 'consumed', last_updated = ? "
            "WHERE instance_id = ?",
            (now, instance_id),
        )

    # -------------------------------------------------------------------------
    # BOM patching
    # -------------------------------------------------------------------------

    def _bom_path(self, asset_key: str, instance_num: str) -> Path:
        cfg = ASSET_REGISTRY[asset_key]
        return (
            self.base_path
            / cfg["instance_submodels_dir"]
            / f"{cfg['instance_file_prefix']}-{instance_num}-Bill_Of_Materials.json"
        )

    def _documentation_path(self, asset_key: str, instance_num: str) -> Path:
        cfg = ASSET_REGISTRY[asset_key]
        return (
            self.base_path
            / cfg["instance_submodels_dir"]
            / f"{cfg['instance_file_prefix']}-{instance_num}-Documentation.json"
        )

    def _shell_path(self, asset_key: str, instance_num: str) -> Path:
        cfg = ASSET_REGISTRY[asset_key]
        return (
            self.base_path
            / cfg["instance_shell_dir"]
            / f"{cfg['instance_file_prefix']}-{instance_num}.json"
        )

    def _instance_id_from_shell(self, asset_key: str, instance_num: str) -> str:
        shell_path = self._shell_path(asset_key, instance_num)
        if not shell_path.exists():
            return ""
        with open(shell_path, encoding="utf-8") as f:
            shell = json.load(f)
        return str(shell.get("id", "") or "")

    @staticmethod
    def _child_collection(parent: Dict[str, Any], id_short: str) -> Optional[Dict[str, Any]]:
        for child in parent.get("value", []):
            if child.get("idShort") == id_short:
                return child
        return None

    @staticmethod
    def _set_prop_value(parent: Dict[str, Any], id_short: str, value: str) -> bool:
        for child in parent.get("value", []):
            if child.get("idShort") == id_short and child.get("modelType") == "Property":
                child["value"] = "" if value is None else str(value)
                return True
        return False

    @staticmethod
    def _build_used_component_slot(slot_id: str, payload: Dict[str, str]) -> Dict[str, Any]:
        """Create a traceability slot when the template does not provide one."""
        return {
            "modelType": "SubmodelElementCollection",
            "idShort": slot_id,
            "description": [{"language": "en", "text": f"{slot_id} instance used"}],
            "value": [
                {
                    "modelType": "Property",
                    "idShort": "instance_id",
                    "valueType": "xs:string",
                    "value": "" if payload.get("instance_id") is None else str(payload.get("instance_id", "")),
                },
                {
                    "modelType": "Property",
                    "idShort": "instance_number",
                    "valueType": "xs:string",
                    "value": "" if payload.get("instance_number") is None else str(payload.get("instance_number", "")),
                },
                {
                    "modelType": "Property",
                    "idShort": "model_number",
                    "valueType": "xs:string",
                    "value": "" if payload.get("model_number") is None else str(payload.get("model_number", "")),
                },
            ],
        }

    @staticmethod
    def _normalize_instance_ref_id(ref_id: str) -> str:
        """Convert submodel IDs to shell IDs when needed."""
        value = (ref_id or "").strip()
        if not value:
            return ""
        parts = value.rstrip("/").split("/")
        if parts and parts[-1] in {
            "Documentation",
            "Properties",
            "Bill_Of_Materials",
            "Bill_Of_Processes",
        }:
            return "/".join(parts[:-1])
        return value

    def _model_number_from_doc(self, asset_key: str, instance_num: str) -> str:
        doc_path = self._documentation_path(asset_key, instance_num)
        if not doc_path.exists():
            return ""
        with open(doc_path, encoding="utf-8") as f:
            doc = json.load(f)
        for elem in doc.get("submodelElements", []):
            if elem.get("idShort") == "Model_Number":
                return str(elem.get("value", "") or "")
        return ""

    def _update_asset_traceability(
        self,
        asset_key: str,
        instance_num: str,
        order_id: str,
        used_updates: Dict[str, Dict[str, str]],
        assembly_date: str,
    ) -> None:
        """
        Generalized traceability update for any asset (Telefon, Bottom_Cover-PCB, Bottom_Cover-PCB-Fuse).
        Patches Documentation Assembly_Traceability and uploads to server.
        """
        doc_path = self._documentation_path(asset_key, instance_num)
        if not doc_path.exists():
            return

        with open(doc_path, encoding="utf-8") as f:
            doc = json.load(f)

        trace = next(
            (e for e in doc.get("submodelElements", []) if e.get("idShort") == "Assembly_Traceability"),
            None,
        )
        if not trace:
            return

        self._set_prop_value(trace, "Assembly_Date", assembly_date)
        self._set_prop_value(trace, "Configuration_Order_ID", order_id)

        used = self._child_collection(trace, "Used_Components")
        if used:
            for slot_id, payload in used_updates.items():
                slot = self._child_collection(used, slot_id)
                if not slot:
                    slot = self._build_used_component_slot(slot_id, {
                        "instance_id": self._normalize_instance_ref_id(payload.get("instance_id", "")),
                        "instance_number": payload.get("instance_number", ""),
                        "model_number": payload.get("model_number", ""),
                    })
                    used.setdefault("value", []).append(slot)
                    continue
                self._set_prop_value(
                    slot,
                    "instance_id",
                    self._normalize_instance_ref_id(payload.get("instance_id", "")),
                )
                self._set_prop_value(slot, "instance_number", payload.get("instance_number", ""))
                self._set_prop_value(slot, "model_number", payload.get("model_number", ""))

        with open(doc_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)

        print(f"  [OK] Patched {asset_key} Documentation traceability ({doc_path.name})")
        self._update_submodel_on_server(doc_path)

    def _update_telefon_traceability(
        self,
        order_id: str,
        telefon_num: str,
        used_updates: Dict[str, Dict[str, str]],
        assembly_date: str,
    ) -> None:
        """Backward-compatible wrapper for Telefon traceability updates."""
        self._update_asset_traceability(
            asset_key="Telefon",
            instance_num=telefon_num,
            order_id=order_id,
            used_updates=used_updates,
            assembly_date=assembly_date,
        )

    @staticmethod
    def _normalize_token(value: str) -> str:
        return "".join(ch for ch in (value or "").lower() if ch.isalnum())

    @staticmethod
    def _slot_property(slot: Dict[str, Any], id_short: str) -> Optional[Dict[str, Any]]:
        for prop in slot.get("value", []):
            if prop.get("idShort") == id_short:
                return prop
        return None

    def _slot_component_type(self, slot: Dict[str, Any]) -> str:
        prop = self._slot_property(slot, "Component_Type")
        return (prop or {}).get("value", "")

    def _component_type_to_asset_key(self, component_type: str) -> Optional[str]:
        norm = self._normalize_token(component_type)
        if not norm:
            return None
        for asset_key, cfg in ASSET_REGISTRY.items():
            c_norm = self._normalize_token(cfg.get("type_submodel_prefix", ""))
            if c_norm and (norm == c_norm or norm.endswith(c_norm) or c_norm.endswith(norm)):
                return asset_key
        return None

    def _find_slot_update(self, slot: Dict[str, Any], slot_updates: Dict[str, Any]) -> Optional[Any]:
        slot_id = slot.get("idShort", "")
        comp_type = self._slot_component_type(slot)
        asset_key = self._component_type_to_asset_key(comp_type)

        # 1) Exact slot id wins (e.g. Fuse_2)
        if slot_id in slot_updates:
            return slot_updates[slot_id]

        # 2) For split slots like Fuse_1..N, map base list update to one entry.
        m = re.match(r"^(.*)_(\d+)$", slot_id)
        if m:
            base_key = m.group(1)
            idx = int(m.group(2)) - 1
            base_update = slot_updates.get(base_key)
            if isinstance(base_update, list):
                if 0 <= idx < len(base_update):
                    return base_update[idx]
                return None

        # 3) Fall back to Component_Type / resolved asset key aliases.
        candidates = [comp_type]
        if asset_key:
            candidates.append(asset_key)

        for key in candidates:
            if key not in slot_updates:
                continue
            value = slot_updates[key]
            if m and isinstance(value, list):
                idx = int(m.group(2)) - 1
                if 0 <= idx < len(value):
                    return value[idx]
                return None
            return value
        return None

    def _patch_bom(
        self,
        bom_path: Path,
        slot_updates: Dict[str, Any],
    ) -> None:
        """
                Open a BOM JSON, find slots under 'Components', and fill
                Instance_Reference values.

        slot_updates format:
          {
                        "Bottom_Cover": "urn:aas-instance-id",        # by slot id / asset key / Component_Type
                        "Product-Component-AAU-PCB": "urn:aas-id",    # by Component_Type value
            "Fuse": ["urn:fuse-1", "urn:fuse-2"],         # list for multiple fuses
          }
        """
        with open(bom_path, encoding="utf-8") as f:
            bom = json.load(f)

        for elem in bom.get("submodelElements", []):
            if elem.get("idShort") != "Components":
                continue
            for slot in elem.get("value", []):
                update = self._find_slot_update(slot, slot_updates)
                if update is None:
                    continue
                slot_props = slot.setdefault("value", [])

                if isinstance(update, list):
                    normalized_refs = [self._normalize_instance_ref_id(ref_id) for ref_id in update]

                    # Preferred format: concrete Components list with Fuse_1..N entries.
                    components_list = self._slot_property(slot, "Components")
                    if components_list and components_list.get("modelType") == "SubmodelElementList":
                        components_list["value"] = [
                            {
                                "modelType": "Property",
                                "idShort": f"Fuse_{i}",
                                "valueType": "xs:string",
                                "value": ref_id,
                            }
                            for i, ref_id in enumerate(normalized_refs, 1)
                        ]

                    # Compatibility format: Instance_References list with Fuse_Ref entries.
                    selected_qty = self._slot_property(slot, "Selected_Quantity")
                    if selected_qty:
                        selected_qty["value"] = str(len(normalized_refs))

                    refs_list = self._slot_property(slot, "Instance_References")
                    if refs_list and refs_list.get("modelType") == "SubmodelElementList":
                        refs_list["value"] = [
                            {
                                "modelType": "Property",
                                "idShort": "Fuse_Ref",
                                "valueType": "xs:string",
                                "value": ref_id,
                            }
                            for ref_id in normalized_refs
                        ]
                    else:
                        # Legacy fallback: Instance_Reference_1..N
                        slot_props[:] = [p for p in slot_props if not p.get("idShort", "").startswith("Instance_Reference_")]
                        for i, ref_id in enumerate(normalized_refs, 1):
                            slot_props.append({
                                "modelType": "Property",
                                "idShort": f"Instance_Reference_{i}",
                                "valueType": "xs:string",
                                "value": ref_id,
                                "description": [{"language": "en", "text": f"AAS ID of fuse instance #{i} used"}],
                            })
                else:
                    normalized_ref = self._normalize_instance_ref_id(update)
                    existing = next(
                        (p for p in slot_props if p.get("idShort") in ("Instance_Reference", "Instance_Refference")),
                        None,
                    )
                    if existing:
                        existing["value"] = normalized_ref
                    else:
                        slot_props.append({
                            "modelType": "Property",
                            "idShort": "Instance_Reference",
                            "valueType": "xs:string",
                            "value": normalized_ref,
                            "description": [{"language": "en", "text": "AAS ID of the physical instance used"}],
                        })

        with open(bom_path, "w", encoding="utf-8") as f:
            json.dump(bom, f, indent=2, ensure_ascii=False)

    # -------------------------------------------------------------------------
    # Sub-assembly registration helpers (same pattern as v3)
    # -------------------------------------------------------------------------

    def _register_subassembly_as_consumed(
        self,
        asset_key: str,
        instance_num: str,
        conn: sqlite3.Connection,
    ) -> None:
        """Register a sub-assembly shell as 'consumed' in inventory_items."""
        cfg = ASSET_REGISTRY[asset_key]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        doc_path = (
            self.base_path
            / cfg["instance_submodels_dir"]
            / f"{cfg['instance_file_prefix']}-{instance_num}-Documentation.json"
        )
        with open(doc_path, encoding="utf-8") as f:
            doc = json.load(f)
        elements = doc.get("submodelElements", [])
        model_number = next((e.get("value") for e in elements if e.get("idShort") == "Model_Number"), "")
        product_name = next((e.get("value") for e in elements if e.get("idShort") == "Product_Name"), None)
        instance_id = self._instance_id_from_shell(asset_key, instance_num)
        if not instance_id:
            # Backward-compatible fallback when shell file is missing.
            instance_id = doc.get("id", "")

        conn.execute("""
            INSERT INTO inventory_items (
                instance_id, instance_number, model_number, component_type,
                product_name, created_date, status, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, 'consumed', ?)
            ON CONFLICT(instance_id) DO UPDATE SET
                status = 'consumed', last_updated = excluded.last_updated
        """, (instance_id, instance_num, model_number, asset_key, product_name, now, now))

    def _register_telefon_as_available(
        self,
        instance_num: str,
        conn: sqlite3.Connection,
        config: Dict = None,
    ) -> None:
        """Register the completed Telefon in inventory as 'available' (ready to ship)."""
        cfg = ASSET_REGISTRY["Telefon"]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        doc_path = (
            self.base_path
            / cfg["instance_submodels_dir"]
            / f"{cfg['instance_file_prefix']}-{instance_num}-Documentation.json"
        )
        with open(doc_path, encoding="utf-8") as f:
            doc = json.load(f)
        elements = doc.get("submodelElements", [])
        model_number = next((e.get("value") for e in elements if e.get("idShort") == "Model_Number"), "")
        product_name = next((e.get("value") for e in elements if e.get("idShort") == "Product_Name"), None)
        instance_id = self._instance_id_from_shell("Telefon", instance_num)
        if not instance_id:
            # Backward-compatible fallback when shell file is missing.
            instance_id = doc.get("id", "")

        material = color = finish = None
        nr_fuses = None
        if config:
            # Config is stored in the nested format; flatten for flat-key property_map lookups.
            flat_config: Dict[str, Any] = {}
            for key, val in config.items():
                if isinstance(val, dict):
                    for pk, pv in val.items():
                        flat_config[f"{key.lower()}_{pk}"] = pv
                else:
                    flat_config[key] = val
            prop_map = ASSET_REGISTRY["Telefon"].get("properties_config_map", {})
            material = flat_config.get(prop_map.get("Material"))
            color    = flat_config.get(prop_map.get("Color"))
            finish   = flat_config.get(prop_map.get("Finish"))
            nr_fuses = flat_config.get(prop_map.get("Nr_Fuses"))

        conn.execute("""
            INSERT INTO inventory_items (
                instance_id, instance_number, model_number, component_type,
                product_name, material, color, finish, nr_fuses,
                created_date, status, last_updated
            ) VALUES (?, ?, ?, 'Telefon', ?, ?, ?, ?, ?, ?, 'available', ?)
            ON CONFLICT(instance_id) DO UPDATE SET
                status = CASE
                    WHEN inventory_items.status IN ('consumed', 'reserved')
                    THEN inventory_items.status
                    ELSE 'available'
                END,
                model_number = excluded.model_number,
                material = excluded.material,
                color = excluded.color,
                finish = excluded.finish,
                nr_fuses = excluded.nr_fuses,
                last_updated = excluded.last_updated
        """, (
            instance_id, instance_num, model_number,
            product_name, material, color, finish, nr_fuses, now, now,
        ))

    # -------------------------------------------------------------------------
    # Order helpers
    # -------------------------------------------------------------------------

    def _load_order(self, order_id: str, conn: sqlite3.Connection) -> sqlite3.Row:
        order = conn.execute(
            "SELECT * FROM configuration_orders WHERE order_id = ?", (order_id,)
        ).fetchone()
        if not order:
            raise Exception(f"Order not found: {order_id}")
        return order

    def _get_shell_instances(self, order: sqlite3.Row) -> Dict[str, str]:
        try:
            return json.loads(order["shell_instances"] or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _shell_instance_id(shells: Dict[str, str], *keys: str) -> str:
        """Return first present shell instance ID for any provided key alias."""
        for key in keys:
            value = shells.get(key)
            if value:
                return value
        return ""

    def _get_assembly_progress(self, order: sqlite3.Row) -> Dict[str, Any]:
        try:
            return json.loads(order["assembly_progress"] or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}

    def _get_model_numbers(self, order: sqlite3.Row) -> Dict[str, str]:
        try:
            return json.loads(order["model_numbers_needed"] or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}

    def _get_order_config(self, order: sqlite3.Row) -> Dict[str, Any]:
        try:
            return json.loads(order["configuration"] or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}

    # -------------------------------------------------------------------------
    # Step 1 — Station 1: Bottom_Cover + PCB -> Bottom_Cover-PCB
    # -------------------------------------------------------------------------

    def assemble_step1_housing(
        self,
        order_id: str,
        bottom_cover_instance_id: Optional[str] = None,
        pcb_instance_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Assembly Step 1 — Station 1.

        Consumes : Bottom_Cover + PCB physical instances.
        Updates  : Bottom_Cover-PCB BOM (Instance_Reference for both slots).
        Transition: pending → step1_done.

        Parameters
        ----------
        bottom_cover_instance_id : AAS instance ID from a barcode/RFID scan (optional).
        pcb_instance_id          : AAS instance ID from a barcode/RFID scan (optional).
        """
        conn = _get_connection(self.db_path)
        _create_tables(conn)

        order = self._load_order(order_id, conn)
        if order["status"] != "pending":
            conn.close()
            raise Exception(
                f"Step 1 requires status 'pending'. Order {order_id} is '{order['status']}'."
            )

        shells        = self._get_shell_instances(order)
        model_numbers = self._get_model_numbers(order)
        progress      = self._get_assembly_progress(order)
        now           = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        hwp_id = self._shell_instance_id(shells, "Bottom_Cover-PCB")
        if not hwp_id:
            conn.close()
            raise Exception(
                f"shell_instances missing Bottom_Cover-PCB for order {order_id}"
            )
        hwp_num = self._inst_num_from_id(hwp_id)

        print(f"\n-- V4 STEP 1 (Station 1): Bottom_Cover-PCB - order {order_id} --")

        already_picked: set = set()

        # Pick Bottom_Cover
        bc = self._pick_instance(
            model_numbers["Bottom_Cover"], bottom_cover_instance_id, already_picked, conn
        )
        already_picked.add(bc["instance_id"])
        print(f"  Bottom_Cover : {bc['model_number']}  instance {bc['instance_number']}")

        # Pick PCB
        pcb = self._pick_instance(
            model_numbers["PCB"], pcb_instance_id, already_picked, conn
        )
        already_picked.add(pcb["instance_id"])
        print(f"  PCB          : {pcb['model_number']}  instance {pcb['instance_number']}")

        # Consume both
        self._consume_instance(bc["instance_id"],  conn, now)
        self._consume_instance(pcb["instance_id"], conn, now)
        print(f"  [OK] Consumed Bottom_Cover instance {bc['instance_number']}")
        print(f"  [OK] Consumed PCB          instance {pcb['instance_number']}")

        # Fulfill reservations
        _fulfill_reservation(conn, order_id, "Bottom_Cover")
        _fulfill_reservation(conn, order_id, "PCB")

        # Patch Bottom_Cover-PCB BOM (slot resolution is BOM-driven).
        bom_path = self._bom_path("Bottom_Cover-PCB", hwp_num)
        if bom_path.exists():
            self._patch_bom(bom_path, {
                "Bottom_Cover": bc["instance_id"],
                "PCB": pcb["instance_id"],
            })
            print(f"  [OK] Patched Bottom_Cover-PCB BOM ({bom_path.name})")
            self._update_submodel_on_server(bom_path)

        # Update Bottom_Cover-PCB traceability
        self._update_asset_traceability(
            asset_key="Bottom_Cover-PCB",
            instance_num=hwp_num,
            order_id=order_id,
            assembly_date=now[:10],
            used_updates={
                "Bottom_Cover": {
                    "instance_id": bc["instance_id"],
                    "instance_number": bc["instance_number"],
                    "model_number": bc["model_number"],
                },
                "PCB": {
                    "instance_id": pcb["instance_id"],
                    "instance_number": pcb["instance_number"],
                    "model_number": pcb["model_number"],
                },
            },
        )

        telefon_id = shells.get("Telefon", "")
        if telefon_id:
            telefon_num = self._inst_num_from_id(telefon_id)
            self._update_telefon_traceability(
                order_id=order_id,
                telefon_num=telefon_num,
                assembly_date=now[:10],
                used_updates={
                    "Bottom_Cover": {
                        "instance_id": bc["instance_id"],
                        "instance_number": bc["instance_number"],
                        "model_number": bc["model_number"],
                    },
                    "PCB": {
                        "instance_id": pcb["instance_id"],
                        "instance_number": pcb["instance_number"],
                        "model_number": pcb["model_number"],
                    },
                    "Housing_With_PCB": {
                        "instance_id": hwp_id,
                        "instance_number": hwp_num,
                        "model_number": self._model_number_from_doc("Bottom_Cover-PCB", hwp_num),
                    },
                    "Bottom_Cover_PCB": {
                        "instance_id": hwp_id,
                        "instance_number": hwp_num,
                        "model_number": self._model_number_from_doc("Bottom_Cover-PCB", hwp_num),
                    },
                },
            )

        # Update progress
        progress["step1"] = {
            "bottom_cover": {"instance_id": bc["instance_id"], "instance_number": bc["instance_number"]},
            "pcb":          {"instance_id": pcb["instance_id"], "instance_number": pcb["instance_number"]},
        }
        progress["bottom_cover-pcb_id"] = hwp_id
        conn.execute(
            "UPDATE configuration_orders SET status = 'step1_done', "
            "assembly_progress = ? WHERE order_id = ?",
            (json.dumps(progress), order_id),
        )
        conn.commit()
        _rebuild_stock(conn)
        conn.close()

        print(f"\n[OK] Step 1 complete - order {order_id} ready for Step 2.\n")
        return {"bottom_cover-pcb_instance": hwp_num, "consumed": {"bottom_cover": bc, "pcb": pcb}}

    # -------------------------------------------------------------------------
    # Step 2 — Station 2: Fuse(s) -> Bottom_Cover-PCB-Fuse
    # -------------------------------------------------------------------------

    def assemble_step2_pcb_fuse(
        self,
        order_id: str,
        fuse_instance_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Assembly Step 2 — Station 2.

        Consumes : All required Fuse physical instances.
        Updates  : Bottom_Cover-PCB-Fuse BOM (fuse references).
        Transition: step1_done → step2_done.

        Parameters
        ----------
        fuse_instance_ids : List of AAS instance IDs from barcode/RFID (optional).
                            Must have exactly the right count if provided.
        """
        conn = _get_connection(self.db_path)
        _create_tables(conn)

        order = self._load_order(order_id, conn)
        if order["status"] != "step1_done":
            conn.close()
            raise Exception(
                f"Step 2 requires status 'step1_done'. Order {order_id} is '{order['status']}'."
            )

        shells        = self._get_shell_instances(order)
        model_numbers = self._get_model_numbers(order)
        order_config  = self._get_order_config(order)
        progress      = self._get_assembly_progress(order)
        n_fuses       = order_config.get("number_of_fuses", 1)
        now           = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        pwf_id = self._shell_instance_id(shells, "Bottom_Cover-PCB-Fuse")
        if not pwf_id:
            conn.close()
            raise Exception(
                f"shell_instances missing Bottom_Cover-PCB-Fuse for order {order_id}"
            )
        pwf_num = self._inst_num_from_id(pwf_id)

        if fuse_instance_ids and len(fuse_instance_ids) != n_fuses:
            conn.close()
            raise Exception(
                f"Order requires {n_fuses} fuse(s) but {len(fuse_instance_ids)} "
                "instance ID(s) were provided."
            )

        print(f"\n-- V4 STEP 2 (Station 2): Bottom_Cover-PCB-Fuse - order {order_id} --")

        fuse_model = model_numbers["Fuse"]
        already_picked: set = set()
        consumed_fuses = []

        for i in range(1, n_fuses + 1):
            explicit_id = fuse_instance_ids[i - 1] if fuse_instance_ids else None
            fuse = self._pick_instance(fuse_model, explicit_id, already_picked, conn)
            already_picked.add(fuse["instance_id"])
            self._consume_instance(fuse["instance_id"], conn, now)
            _fulfill_reservation(conn, order_id, f"Fuse_{i}")
            consumed_fuses.append(fuse)
            print(f"  Fuse_{i:<3}      : {fuse['model_number']}  instance {fuse['instance_number']}")
            print(f"  [OK] Consumed Fuse_{i} instance {fuse['instance_number']}")

        # In step 2 the Bottom_Cover-PCB shell was already created.
        hwp_id  = self._shell_instance_id(shells, "Bottom_Cover-PCB")
        hwp_num = self._inst_num_from_id(hwp_id) if hwp_id else ""
        hwp_cfg = ASSET_REGISTRY["Bottom_Cover-PCB"]
        hwp_shell_path = (
            self.base_path
            / hwp_cfg["instance_shell_dir"]
            / f"{hwp_cfg['instance_file_prefix']}-{hwp_num}.json"
        )
        housing_instance_id = ""
        if hwp_shell_path.exists():
            with open(hwp_shell_path, encoding="utf-8") as _f:
                housing_instance_id = json.load(_f)["id"]

        bom_path = self._bom_path("Bottom_Cover-PCB-Fuse", pwf_num)
        if bom_path.exists():
            self._patch_bom(bom_path, {
                "Fuse": [f["instance_id"] for f in consumed_fuses],
                "Bottom_Cover-PCB": housing_instance_id,
            })
            print(f"  [OK] Patched Bottom_Cover-PCB-Fuse BOM ({bom_path.name})")
            self._update_submodel_on_server(bom_path)

        # Extract step1 progress data (needed for both traceability updates)
        step1 = progress.get("step1", {})

        # Update Bottom_Cover-PCB-Fuse traceability
        fuse_updates = {
            "Bottom_Cover": {
                "instance_id": step1.get("bottom_cover", {}).get("instance_id", ""),
                "instance_number": step1.get("bottom_cover", {}).get("instance_number", ""),
                "model_number": model_numbers.get("Bottom_Cover", ""),
            },
            "PCB": {
                "instance_id": step1.get("pcb", {}).get("instance_id", ""),
                "instance_number": step1.get("pcb", {}).get("instance_number", ""),
                "model_number": model_numbers.get("PCB", ""),
            }
        }
        for i, fuse in enumerate(consumed_fuses, 1):
            fuse_updates[f"Fuse_{i}"] = {
                "instance_id": fuse["instance_id"],
                "instance_number": fuse["instance_number"],
                "model_number": fuse["model_number"],
            }
        self._update_asset_traceability(
            asset_key="Bottom_Cover-PCB-Fuse",
            instance_num=pwf_num,
            order_id=order_id,
            assembly_date=now[:10],
            used_updates=fuse_updates,
        )

        telefon_id = shells.get("Telefon", "")
        if telefon_id:
            telefon_num = self._inst_num_from_id(telefon_id)
            self._update_telefon_traceability(
                order_id=order_id,
                telefon_num=telefon_num,
                assembly_date=now[:10],
                used_updates={
                    "Bottom_Cover": {
                        "instance_id": step1.get("bottom_cover", {}).get("instance_id", ""),
                        "instance_number": step1.get("bottom_cover", {}).get("instance_number", ""),
                        "model_number": model_numbers.get("Bottom_Cover", ""),
                    },
                    "PCB": {
                        "instance_id": step1.get("pcb", {}).get("instance_id", ""),
                        "instance_number": step1.get("pcb", {}).get("instance_number", ""),
                        "model_number": model_numbers.get("PCB", ""),
                    },
                    "Housing_With_PCB": {
                        "instance_id": hwp_id,
                        "instance_number": hwp_num,
                        "model_number": self._model_number_from_doc("Bottom_Cover-PCB", hwp_num),
                    },
                    "PCB_With_Fuse": {
                        "instance_id": pwf_id,
                        "instance_number": pwf_num,
                        "model_number": self._model_number_from_doc("Bottom_Cover-PCB-Fuse", pwf_num),
                    },
                    "Bottom_Cover_PCB": {
                        "instance_id": hwp_id,
                        "instance_number": hwp_num,
                        "model_number": self._model_number_from_doc("Bottom_Cover-PCB", hwp_num),
                    },
                    "Bottom_Cover_PCB_Fuse": {
                        "instance_id": pwf_id,
                        "instance_number": pwf_num,
                        "model_number": self._model_number_from_doc("Bottom_Cover-PCB-Fuse", pwf_num),
                    },
                },
            )

        progress["step2"] = {f"fuse_{i}": {"instance_id": consumed_fuses[i-1]["instance_id"],
                                            "instance_number": consumed_fuses[i-1]["instance_number"]}
                             for i in range(1, n_fuses + 1)}
        progress["bottom_cover-PCB-Fuse_id"] = pwf_id
        conn.execute(
            "UPDATE configuration_orders SET status = 'step2_done', "
            "assembly_progress = ? WHERE order_id = ?",
            (json.dumps(progress), order_id),
        )
        conn.commit()
        _rebuild_stock(conn)
        conn.close()

        print(f"\n[OK] Step 2 complete - order {order_id} ready for Step 3.\n")
        return {"bottom_cover-PCB-Fuse_instance": pwf_num, "consumed_fuses": consumed_fuses}

    # -------------------------------------------------------------------------
    # Step 3 — Station 3: Top_Cover + sub-assemblies → Final Telefon
    # -------------------------------------------------------------------------

    def assemble_step3_final(
        self,
        order_id: str,
        top_cover_instance_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Assembly Step 3 — Station 3.

        Consumes : Top_Cover physical instance.
                   Marks Bottom_Cover-PCB and Bottom_Cover-PCB-Fuse sub-assemblies consumed.
        Updates  : Telefon BOM with all component and sub-assembly references.
        Registers: Telefon as 'available' in inventory (ready to ship).
        Transition: step2_done → assembled.

        Parameters
        ----------
        top_cover_instance_id : AAS instance ID from barcode/RFID (optional).
        """
        conn = _get_connection(self.db_path)
        _create_tables(conn)

        order = self._load_order(order_id, conn)
        if order["status"] != "step2_done":
            conn.close()
            raise Exception(
                f"Step 3 requires status 'step2_done'. Order {order_id} is '{order['status']}'."
            )

        shells       = self._get_shell_instances(order)
        model_numbers = self._get_model_numbers(order)
        order_config = self._get_order_config(order)
        progress     = self._get_assembly_progress(order)
        n_fuses      = order_config.get("number_of_fuses", 1)
        now          = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        telefon_id  = shells.get("Telefon", "")
        hwp_id      = self._shell_instance_id(shells, "Bottom_Cover-PCB")
        pwf_id      = self._shell_instance_id(shells, "Bottom_Cover-PCB-Fuse")
        telefon_num = self._inst_num_from_id(telefon_id) if telefon_id else None
        hwp_num     = self._inst_num_from_id(hwp_id)     if hwp_id     else None
        pwf_num     = self._inst_num_from_id(pwf_id)     if pwf_id     else None

        if not all([telefon_num, hwp_num, pwf_num]):
            conn.close()
            raise Exception(f"shell_instances incomplete for order {order_id}")

        print(f"\n-- V4 STEP 3 (Station 3): Final Telefon - order {order_id} --")
        print(f"  Bottom_Cover-PCB      : instance {hwp_num}")
        print(f"  Bottom_Cover-PCB-Fuse : instance {pwf_num}")

        # Pick Top_Cover
        tc = self._pick_instance(
            model_numbers["Top_Cover"], top_cover_instance_id, set(), conn
        )
        print(f"  Top_Cover        : {tc['model_number']}  instance {tc['instance_number']}")

        # Consume Top_Cover + fulfil reservation
        self._consume_instance(tc["instance_id"], conn, now)
        _fulfill_reservation(conn, order_id, "Top_Cover")
        print(f"  [OK] Consumed Top_Cover instance {tc['instance_number']}")

        # Mark sub-assemblies as consumed
        self._register_subassembly_as_consumed("Bottom_Cover-PCB", hwp_num, conn)
        self._register_subassembly_as_consumed("Bottom_Cover-PCB-Fuse", pwf_num, conn)
        print(f"  [OK] Registered Bottom_Cover-PCB      instance {hwp_num} as consumed")
        print(f"  [OK] Registered Bottom_Cover-PCB-Fuse instance {pwf_num} as consumed")

        # hwp_id and pwf_id already hold the full AAS IDs (stored at order time)

        # Retrieve step 1 + step 2 consumed instance IDs for full Telefon BOM
        step1    = progress.get("step1", {})
        step2    = progress.get("step2", {})
        bc_id    = step1.get("bottom_cover", {}).get("instance_id", "")
        pcb_id   = step1.get("pcb", {}).get("instance_id", "")
        fuse_ids = [step2.get(f"fuse_{i}", {}).get("instance_id", "") for i in range(1, n_fuses + 1)]

        # Patch Telefon BOM with ALL references
        telefon_bom_path = self._bom_path("Telefon", telefon_num)
        if telefon_bom_path.exists():
            self._patch_bom(telefon_bom_path, {
                "Top_Cover":       tc["instance_id"],
                "Bottom_Cover-PCB-Fuse": pwf_id,
            })
            print(f"  [OK] Patched Telefon BOM ({telefon_bom_path.name})")
            self._update_submodel_on_server(telefon_bom_path)

        self._update_telefon_traceability(
            order_id=order_id,
            telefon_num=telefon_num,
            assembly_date=now[:10],
            used_updates={
                "Bottom_Cover": {
                    "instance_id": bc_id,
                    "instance_number": step1.get("bottom_cover", {}).get("instance_number", ""),
                    "model_number": model_numbers.get("Bottom_Cover", ""),
                },
                "Top_Cover": {
                    "instance_id": tc["instance_id"],
                    "instance_number": tc["instance_number"],
                    "model_number": tc["model_number"],
                },
                "PCB": {
                    "instance_id": pcb_id,
                    "instance_number": step1.get("pcb", {}).get("instance_number", ""),
                    "model_number": model_numbers.get("PCB", ""),
                },
                "Housing_With_PCB": {
                    "instance_id": hwp_id,
                    "instance_number": hwp_num,
                    "model_number": self._model_number_from_doc("Bottom_Cover-PCB", hwp_num),
                },
                "PCB_With_Fuse": {
                    "instance_id": pwf_id,
                    "instance_number": pwf_num,
                    "model_number": self._model_number_from_doc("Bottom_Cover-PCB-Fuse", pwf_num),
                },
                "Bottom_Cover_PCB": {
                    "instance_id": hwp_id,
                    "instance_number": hwp_num,
                    "model_number": self._model_number_from_doc("Bottom_Cover-PCB", hwp_num),
                },
                "Bottom_Cover_PCB_Fuse": {
                    "instance_id": pwf_id,
                    "instance_number": pwf_num,
                    "model_number": self._model_number_from_doc("Bottom_Cover-PCB-Fuse", pwf_num),
                },
            },
        )

        # Register the finished Telefon as available in inventory
        self._register_telefon_as_available(telefon_num, conn, order_config)
        print(f"  [OK] Registered Telefon instance {telefon_num} as available in inventory")

        # telefon_id is already the full AAS ID from shell_instances (stored at order time)

        progress["step3"] = {
            "top_cover": {"instance_id": tc["instance_id"], "instance_number": tc["instance_number"]},
        }
        progress["telefon_instance_num"] = telefon_num
        progress["telefon_instance_id"]  = telefon_id

        conn.execute(
            "UPDATE configuration_orders SET status = 'assembled', assembled_date = ?, "
            "assembly_progress = ? WHERE order_id = ?",
            (now, json.dumps(progress), order_id),
        )
        conn.commit()
        _rebuild_stock(conn)
        conn.close()

        print(f"\n[OK] Step 3 complete - order {order_id} fully assembled.")
        print(f"  Telefon instance : {telefon_num}  ({telefon_id})\n")
        return {"telefon_instance": telefon_num, "telefon_instance_id": telefon_id, "consumed_top_cover": tc}

    # -------------------------------------------------------------------------
    # Convenience: run all 3 steps
    # -------------------------------------------------------------------------

    def assemble_all(
        self,
        order_id: str,
        bottom_cover_instance_id: Optional[str] = None,
        pcb_instance_id: Optional[str] = None,
        fuse_instance_ids: Optional[List[str]] = None,
        top_cover_instance_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run all 3 assembly steps in sequence. Returns step 3 result."""
        self.assemble_step1_housing(order_id, bottom_cover_instance_id, pcb_instance_id)
        self.assemble_step2_pcb_fuse(order_id, fuse_instance_ids)
        return self.assemble_step3_final(order_id, top_cover_instance_id)

    # -------------------------------------------------------------------------
    # Cancel order
    # -------------------------------------------------------------------------

    def cancel_order(self, order_id: str) -> None:
        """
        Cancel a pending order: release all model-type reservations and
        mark the order status as 'cancelled'.
        Already-consumed components from partial assembly are NOT restored.
        """
        conn = _get_connection(self.db_path)
        _create_tables(conn)

        order = self._load_order(order_id, conn)
        if order["status"] in ("assembled", "released"):
            conn.close()
            raise Exception(
                f"Order {order_id} is already '{order['status']}' and cannot be cancelled."
            )

        cancelled = _cancel_order_reservations(conn, order_id)
        conn.execute(
            "UPDATE configuration_orders SET status = 'cancelled' WHERE order_id = ?",
            (order_id,),
        )
        conn.commit()
        _rebuild_stock(conn)
        conn.close()
        print(f"[OK] Order {order_id} cancelled ({cancelled} pending reservation(s) released).")

    # -------------------------------------------------------------------------
    # Release (ship) an assembled Telefon
    # -------------------------------------------------------------------------

    def release_order(self, order_id: str) -> None:
        """Mark the Telefon as shipped and transition order to 'released'."""
        conn = _get_connection(self.db_path)
        _create_tables(conn)

        order = self._load_order(order_id, conn)
        if order["status"] != "assembled":
            conn.close()
            raise Exception(
                f"Order {order_id} cannot be released (current status: '{order['status']}')."
            )

        progress    = self._get_assembly_progress(order)
        telefon_id  = progress.get("telefon_instance_id")
        now         = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if telefon_id:
            conn.execute(
                "UPDATE inventory_items SET status = 'consumed', last_updated = ? "
                "WHERE instance_id = ? AND status != 'consumed'",
                (now, telefon_id),
            )

        conn.execute(
            "UPDATE configuration_orders SET status = 'released', assembled_date = ? "
            "WHERE order_id = ?",
            (now, order_id),
        )
        conn.commit()
        _rebuild_stock(conn)
        conn.close()
        print(f"[OK] Order {order_id} released (Telefon shipped).")

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _shell_aas_id(self, asset_key: str, instance_num: str) -> str:
        """Read the AAS 'id' from the already-created instance shell JSON."""
        cfg = ASSET_REGISTRY[asset_key]
        shell_path = (
            self.base_path
            / cfg["instance_shell_dir"]
            / f"{cfg['instance_file_prefix']}-{instance_num}.json"
        )
        if not shell_path.exists():
            return ""
        with open(shell_path, encoding="utf-8") as f:
            shell = json.load(f)
        return shell.get("id", "")

    # -------------------------------------------------------------------------
    # CLI listing helpers
    # -------------------------------------------------------------------------

    def list_orders(self, status_filter: Optional[str] = None) -> List[Dict]:
        conn = _get_connection(self.db_path)
        if status_filter:
            rows = conn.execute(
                "SELECT * FROM configuration_orders WHERE status = ? ORDER BY created_date DESC",
                (status_filter,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM configuration_orders ORDER BY created_date DESC"
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Assembly Manager V4")
    parser.add_argument("--list",         action="store_true",     help="List all orders")
    parser.add_argument("--list-pending", action="store_true",     help="List pending/in-progress orders")
    parser.add_argument("--step1",        metavar="ORDER_ID",      help="Run Step 1 for an order")
    parser.add_argument("--step2",        metavar="ORDER_ID",      help="Run Step 2 for an order")
    parser.add_argument("--step3",        metavar="ORDER_ID",      help="Run Step 3 for an order")
    parser.add_argument("--assemble",     metavar="ORDER_ID",      help="Run all 3 steps for an order")
    parser.add_argument("--cancel",       metavar="ORDER_ID",      help="Cancel an order")
    parser.add_argument("--release",      metavar="ORDER_ID",      help="Release (ship) an assembled order")
    args = parser.parse_args()

    mgr = AssemblyManagerV4()

    STEP_LABEL = {
        "pending":    "Awaiting Step 1",
        "step1_done": "Awaiting Step 2",
        "step2_done": "Awaiting Step 3",
        "assembled":  "Assembled",
        "released":   "Released",
        "cancelled":  "Cancelled",
    }

    if args.list or args.list_pending:
        filter_status = None if args.list else None
        orders = mgr.list_orders()
        pending_only = args.list_pending
        if pending_only:
            orders = [o for o in orders if o["status"] in ("pending", "step1_done", "step2_done")]
        if not orders:
            print("No orders found.")
            return
        print("\n" + "=" * 100)
        print(f"  {'Order ID':<15} {'Product Type':<20} {'Status':<22} {'Created':<19}")
        print("-" * 100)
        for o in orders:
            print(f"  {o['order_id']:<15} {o['product_type']:<20} "
                  f"{STEP_LABEL.get(o['status'], o['status']):<22} {o['created_date']:<19}")
        print("=" * 100 + "\n")
        return

    for attr, func in [
        ("step1",    lambda oid: mgr.assemble_step1_housing(oid)),
        ("step2",    lambda oid: mgr.assemble_step2_pcb_fuse(oid)),
        ("step3",    lambda oid: mgr.assemble_step3_final(oid)),
        ("assemble", lambda oid: mgr.assemble_all(oid)),
        ("cancel",   lambda oid: mgr.cancel_order(oid)),
        ("release",  lambda oid: mgr.release_order(oid)),
    ]:
        oid = getattr(args, attr)
        if oid:
            try:
                func(oid)
            except Exception as e:
                print(f"Error: {e}")
            return

    parser.print_help()


if __name__ == "__main__":
    main()
