"""
Assembly Manager V4 — Phase 2: Instance Binding & BOM Patching

Operates on orders created by TelefonConfiguratorV4.
The shells (Housing_With_PCB, PCB_With_Fuse, Telefon) already exist on disk
from order-placement time.  Each assembly step:
  1. Picks a physical component instance (auto-selects first available OR
     accepts an explicit instance_id, e.g. from a barcode / RFID scan).
  2. Marks that inventory_items row as 'consumed'.
  3. Fulfils the corresponding model_type_reservation.
  4. Patches the pre-created BOM JSON file with the actual Instance_Reference.

Assembly steps mirror the physical production stations:
  Step 1 (Station 1) : Bottom_Cover  + PCB         → Housing_With_PCB
  Step 2 (Station 2) : Fuse(s)                     → PCB_With_Fuse
  Step 3 (Station 3) : Top_Cover + sub-assemblies  → Final Telefon

All steps are individually callable via the API, or run in sequence via
assemble_all().
"""

import json
import sqlite3
import base64
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
            print(f"  {'OK' if r.ok else f'FAIL ({r.status_code})'} → server UPDATE BOM: {submodel_path.name}")
        except requests.ConnectionError:
            print(f"  ERROR → could not connect to AAS server at {self.server_base}")

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

    def _patch_bom(
        self,
        bom_path: Path,
        slot_updates: Dict[str, Any],
    ) -> None:
        """
        Open a BOM JSON, find named slots under 'Components', and fill
        Instance_Reference values.

        slot_updates format:
          {
            "Bottom_Cover": "urn:aas-instance-id",        # single reference
            "PCB_With_Fuse": "urn:aas-instance-id",       # single reference
            "Fuse": ["urn:fuse-1", "urn:fuse-2"],         # list for multiple fuses
          }
        """
        with open(bom_path, encoding="utf-8") as f:
            bom = json.load(f)

        for elem in bom.get("submodelElements", []):
            if elem.get("idShort") != "Components":
                continue
            for slot in elem.get("value", []):
                slot_id = slot.get("idShort", "")
                if slot_id not in slot_updates:
                    continue
                update = slot_updates[slot_id]
                slot_props = slot.setdefault("value", [])

                if isinstance(update, list):
                    # Multiple fuse references: Instance_Reference_1, _2, ...
                    for i, ref_id in enumerate(update, 1):
                        ref_key = f"Instance_Reference_{i}"
                        existing = next((p for p in slot_props if p.get("idShort") == ref_key), None)
                        if existing:
                            existing["value"] = ref_id
                        else:
                            slot_props.append({
                                "modelType": "Property",
                                "idShort": ref_key,
                                "valueType": "xs:string",
                                "value": ref_id,
                                "description": [{"language": "en", "text": f"AAS ID of fuse instance #{i} used"}],
                            })
                else:
                    existing = next((p for p in slot_props if p.get("idShort") == "Instance_Reference"), None)
                    if existing:
                        existing["value"] = update
                    else:
                        slot_props.append({
                            "modelType": "Property",
                            "idShort": "Instance_Reference",
                            "valueType": "xs:string",
                            "value": update,
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
        instance_id  = doc.get("id", "")

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
        instance_id  = doc.get("id", "")

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
    # Step 1 — Station 1: Bottom_Cover + PCB → Housing_With_PCB
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
        Updates  : Housing_With_PCB BOM  (Instance_Reference for both slots).
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

        hwp_id = shells.get("Housing_With_PCB")
        if not hwp_id:
            conn.close()
            raise Exception(f"shell_instances missing Housing_With_PCB for order {order_id}")
        hwp_num = self._inst_num_from_id(hwp_id)

        print(f"\n── V4 STEP 1 (Station 1): Housing_With_PCB — order {order_id} ──")

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
        print(f"  ✓ Consumed Bottom_Cover instance {bc['instance_number']}")
        print(f"  ✓ Consumed PCB          instance {pcb['instance_number']}")

        # Fulfill reservations
        _fulfill_reservation(conn, order_id, "Bottom_Cover")
        _fulfill_reservation(conn, order_id, "PCB")

        # Patch Housing_With_PCB BOM
        # BOM slots: "Bottom_Cover" → bc.instance_id, "PCB_With_Fuse" → pcb.instance_id
        # (The type BOM uses "PCB_With_Fuse" as the slot name for the raw PCB component)
        bom_path = self._bom_path("Housing_With_PCB", hwp_num)
        if bom_path.exists():
            self._patch_bom(bom_path, {
                "Bottom_Cover": bc["instance_id"],
                "PCB_With_Fuse": pcb["instance_id"],   # slot idShort from type template
            })
            print(f"  ✓ Patched Housing_With_PCB BOM ({bom_path.name})")
            self._update_submodel_on_server(bom_path)

        # Update progress
        progress["step1"] = {
            "bottom_cover": {"instance_id": bc["instance_id"], "instance_number": bc["instance_number"]},
            "pcb":          {"instance_id": pcb["instance_id"], "instance_number": pcb["instance_number"]},
        }
        conn.execute(
            "UPDATE configuration_orders SET status = 'step1_done', "
            "assembly_progress = ? WHERE order_id = ?",
            (json.dumps(progress), order_id),
        )
        conn.commit()
        _rebuild_stock(conn)
        conn.close()

        print(f"\n✓ Step 1 complete — order {order_id} ready for Step 2.\n")
        return {"housing_with_pcb_instance": hwp_num, "consumed": {"bottom_cover": bc, "pcb": pcb}}

    # -------------------------------------------------------------------------
    # Step 2 — Station 2: Fuse(s) → PCB_With_Fuse
    # -------------------------------------------------------------------------

    def assemble_step2_pcb_fuse(
        self,
        order_id: str,
        fuse_instance_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Assembly Step 2 — Station 2.

        Consumes : All required Fuse physical instances.
        Updates  : PCB_With_Fuse BOM  (Instance_Reference_1..N for Fuse slot).
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

        pwf_id = shells.get("PCB_With_Fuse")
        if not pwf_id:
            conn.close()
            raise Exception(f"shell_instances missing PCB_With_Fuse for order {order_id}")
        pwf_num = self._inst_num_from_id(pwf_id)

        if fuse_instance_ids and len(fuse_instance_ids) != n_fuses:
            conn.close()
            raise Exception(
                f"Order requires {n_fuses} fuse(s) but {len(fuse_instance_ids)} "
                "instance ID(s) were provided."
            )

        print(f"\n── V4 STEP 2 (Station 2): PCB_With_Fuse — order {order_id} ──")

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
            print(f"  ✓ Consumed Fuse_{i} instance {fuse['instance_number']}")

        # In step 2 the HWP shell was already created — read its instance number for file access
        hwp_id  = shells.get("Housing_With_PCB", "")
        hwp_num = self._inst_num_from_id(hwp_id) if hwp_id else ""
        hwp_cfg = ASSET_REGISTRY["Housing_With_PCB"]
        hwp_shell_path = (
            self.base_path
            / hwp_cfg["instance_shell_dir"]
            / f"{hwp_cfg['instance_file_prefix']}-{hwp_num}.json"
        )
        housing_instance_id = ""
        if hwp_shell_path.exists():
            with open(hwp_shell_path, encoding="utf-8") as _f:
                housing_instance_id = json.load(_f)["id"]

        bom_path = self._bom_path("PCB_With_Fuse", pwf_num)
        if bom_path.exists():
            self._patch_bom(bom_path, {
                "Fuse": [f["instance_id"] for f in consumed_fuses],
                "Housing_With_PCB": housing_instance_id,
            })
            print(f"  ✓ Patched PCB_With_Fuse BOM ({bom_path.name})")
            self._update_submodel_on_server(bom_path)

        progress["step2"] = {f"fuse_{i}": {"instance_id": consumed_fuses[i-1]["instance_id"],
                                            "instance_number": consumed_fuses[i-1]["instance_number"]}
                             for i in range(1, n_fuses + 1)}
        conn.execute(
            "UPDATE configuration_orders SET status = 'step2_done', "
            "assembly_progress = ? WHERE order_id = ?",
            (json.dumps(progress), order_id),
        )
        conn.commit()
        _rebuild_stock(conn)
        conn.close()

        print(f"\n✓ Step 2 complete — order {order_id} ready for Step 3.\n")
        return {"pcb_with_fuse_instance": pwf_num, "consumed_fuses": consumed_fuses}

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
                   Marks Housing_With_PCB and PCB_With_Fuse sub-assemblies consumed.
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
        hwp_id      = shells.get("Housing_With_PCB", "")
        pwf_id      = shells.get("PCB_With_Fuse", "")
        telefon_num = self._inst_num_from_id(telefon_id) if telefon_id else None
        hwp_num     = self._inst_num_from_id(hwp_id)     if hwp_id     else None
        pwf_num     = self._inst_num_from_id(pwf_id)     if pwf_id     else None

        if not all([telefon_num, hwp_num, pwf_num]):
            conn.close()
            raise Exception(f"shell_instances incomplete for order {order_id}")

        print(f"\n── V4 STEP 3 (Station 3): Final Telefon — order {order_id} ──")
        print(f"  Housing_With_PCB : instance {hwp_num}")
        print(f"  PCB_With_Fuse    : instance {pwf_num}")

        # Pick Top_Cover
        tc = self._pick_instance(
            model_numbers["Top_Cover"], top_cover_instance_id, set(), conn
        )
        print(f"  Top_Cover        : {tc['model_number']}  instance {tc['instance_number']}")

        # Consume Top_Cover + fulfil reservation
        self._consume_instance(tc["instance_id"], conn, now)
        _fulfill_reservation(conn, order_id, "Top_Cover")
        print(f"  ✓ Consumed Top_Cover instance {tc['instance_number']}")

        # Mark sub-assemblies as consumed
        self._register_subassembly_as_consumed("Housing_With_PCB", hwp_num, conn)
        self._register_subassembly_as_consumed("PCB_With_Fuse",    pwf_num, conn)
        print(f"  ✓ Registered Housing_With_PCB instance {hwp_num} as consumed")
        print(f"  ✓ Registered PCB_With_Fuse    instance {pwf_num} as consumed")

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
                "Bottom_Cover":    bc_id,
                "Top_Cover":       tc["instance_id"],
                "PCB":             pcb_id,
                "Fuse":            fuse_ids,
                # Sub-assembly shells reference (non-standard additional refs)
                "Housing_With_PCB": hwp_id,
                "PCB_With_Fuse":    pwf_id,
            })
            print(f"  ✓ Patched Telefon BOM ({telefon_bom_path.name})")
            self._update_submodel_on_server(telefon_bom_path)

        # Register the finished Telefon as available in inventory
        self._register_telefon_as_available(telefon_num, conn, order_config)
        print(f"  ✓ Registered Telefon instance {telefon_num} as available in inventory")

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

        print(f"\n✓ Step 3 complete — order {order_id} fully assembled.")
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
        print(f"✓ Order {order_id} cancelled ({cancelled} pending reservation(s) released).")

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
        print(f"✓ Order {order_id} released (Telefon shipped).")

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
