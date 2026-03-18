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
from uuid import uuid4

import requests

from inventory_db import (
    _create_tables, _get_connection, _rebuild_stock,
    _reserve_model_types, AAS_FILES_BASE, DEFAULT_DB_FILE,
)
from asset_registry import ASSET_REGISTRY, ORDER_TIME_SHELL_KEYS


# =============================================================================
# AAS Server defaults
# =============================================================================

DEFAULT_SERVER_BASE = "http://localhost:8081"
CONFIG_TEMPLATE_ID = "https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max/Configuration_Template"


def _b64url(s: str) -> str:
    """Base64url-encode a string (no padding) for AAS REST path segments."""
    return base64.urlsafe_b64encode(s.encode()).rstrip(b"=").decode()


# =============================================================================
# Configurator class
# =============================================================================

class TelefonConfiguratorV4:
    """
    Phase 1 configurator.

    create_order(config) -> (order_id, details):
      1. Validate configuration
      2. Check model-type stock
    3. Create Bottom_Cover_PCB, Bottom_Cover_PCB_Fuse, and Telefon shells upfront
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
        self.base_path = Path(base_path) if base_path else AAS_FILES_BASE
        self.db_path = db_path or DEFAULT_DB_FILE
        self.upload = upload
        self.server_base = server_base
        self._ensure_config_template_on_server()
        self._config_template = self._load_config_template()

    # -------------------------------------------------------------------------
    # Config helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _flatten_config(config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert nested config {Bottom_Cover: {material: x}} to flat {bottom_cover_material: x}.

        Nested component dicts are expanded using the pattern: {component_lower}_{property}.
        Top-level scalar values (e.g. number_of_fuses, _order_id) are kept as-is.
        """
        flat: Dict[str, Any] = {}
        for key, value in config.items():
            if isinstance(value, dict):
                prefix = key.lower()  # "Bottom_Cover" → "bottom_cover"
                for prop, v in value.items():
                    flat[f"{prefix}_{prop}"] = v
            else:
                flat[key] = value
        return flat

    # -------------------------------------------------------------------------
    # AAS Server upload
    # -------------------------------------------------------------------------

    def _post_or_put(self, endpoint: str, resource_id: str, data: Dict) -> requests.Response:
        """POST to create; fall back to PUT if the server returns 409 (already exists)."""
        headers = {"Content-Type": "application/json"}
        r = requests.post(endpoint, json=data, headers=headers, timeout=5)
        if r.status_code == 409:
            r = requests.put(f"{endpoint}/{_b64url(resource_id)}", json=data, headers=headers, timeout=5)
        return r

    def _upload_to_server(self, shell: Dict, submodels: Dict[str, Dict]) -> None:
        """
        POST submodels then shell to the AAS server.
        Falls back to PUT if a resource already exists (409).
        """
        if not self.upload:
            return
        submodel_endpoint = f"{self.server_base}/submodels"
        shell_endpoint = f"{self.server_base}/shells"
        for sm_name, sm_data in submodels.items():
            try:
                r = self._post_or_put(submodel_endpoint, sm_data.get("id", ""), sm_data)
                if r.ok:
                    print(f"  OK → server submodel: {sm_name}")
                else:
                    print(f"  FAIL ({r.status_code}) → server submodel: {sm_name}")
                    try:
                        print(f"    Server: {r.json()}")
                    except Exception:
                        print(f"    Server: {r.text[:300]}")
            except requests.ConnectionError:
                print(f"  ERROR → could not connect to AAS server at {self.server_base}")
                return
        try:
            r = self._post_or_put(shell_endpoint, shell.get("id", ""), shell)
            if r.ok:
                print(f"  OK → server shell: {shell.get('id', '')}")
            else:
                print(f"  FAIL ({r.status_code}) → server shell: {shell.get('id', '')}")
                try:
                    print(f"    Server: {r.json()}")
                except Exception:
                    print(f"    Server: {r.text[:300]}")
        except requests.ConnectionError:
            print(f"  ERROR → could not connect to AAS server at {self.server_base}")

    # -------------------------------------------------------------------------
    # Configuration template
    # -------------------------------------------------------------------------

    def _config_template_local_path(self) -> Path:
        return (
            self.base_path
            / "JSON_Submodels"
            / "Product_Submodels_JSON"
            / "Final_Product_Submodels"
            / "Product-Final_Product-Telefon-Telefon_Pro_Max-Configuration_Template.json"
        )

    def _load_config_template_from_server(self) -> Dict[str, Any]:
        """Fetch shared configuration template from AAS server by its stable template ID."""
        url = f"{self.server_base}/submodels/{_b64url(CONFIG_TEMPLATE_ID)}"
        try:
            r = requests.get(url, timeout=5)
            if not r.ok:
                return {}
            data = r.json()
            return data if isinstance(data, dict) else {}
        except (requests.RequestException, ValueError):
            return {}

    def _ensure_config_template_on_server(self) -> None:
        """Ensure shared Configuration_Template exists on server (single shared resource)."""
        if not self.upload:
            return

        # If template already exists remotely, do nothing.
        if self._load_config_template_from_server():
            return

        path = self._config_template_local_path()
        if not path.exists():
            return

        try:
            with open(path, encoding="utf-8") as f:
                template = json.load(f)
            r = self._post_or_put(f"{self.server_base}/submodels", CONFIG_TEMPLATE_ID, template)
            if r.ok:
                print("  OK -> server shared submodel: Configuration_Template")
            else:
                print(f"  FAIL ({r.status_code}) -> server shared submodel: Configuration_Template")
        except (OSError, ValueError, requests.RequestException):
            # Non-fatal: local fallback in _load_config_template will still work.
            return

    def _load_config_template(self) -> Dict[str, Any]:
        # Prefer the server-hosted shared template; fall back to local file for offline/dev use.
        server_template = self._load_config_template_from_server()
        if server_template:
            return server_template

        path = self._config_template_local_path()
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    # -------------------------------------------------------------------------
    # Model number derivation  (same logic as v3)
    # -------------------------------------------------------------------------

    def _get_model_numbers_for_config(self, config: Dict[str, Any]) -> Dict[str, str]:
        """Return {component_type: model_number} for all components in the config."""
        flat = self._flatten_config(config)
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
                    lambda m: str(flat.get(m.group(1), m.group(0))),
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
        flat = self._flatten_config(config)

        # Collect required config fields from all properties_config_maps in ASSET_REGISTRY.
        # Sub-assembly maps (e.g. Bottom_Cover_PCB) share the same config keys as components,
        # so the union of all values covers the full required set.
        required: set = {
            config_key
            for cfg in ASSET_REGISTRY.values()
            for config_key in cfg.get("properties_config_map", {}).values()
        }
        for field in required:
            if field not in flat:
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
                            if mat_key and fin_key and mat_key in flat and fin_key in flat:
                                if (flat[mat_key], flat[fin_key]) in incompatible:
                                    errors.append(
                                        f"Invalid: {flat[mat_key]} cannot be {flat[fin_key]}"
                                    )

        return len(errors) == 0, errors

    def check_inventory(self, config: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Check effective available stock (inventory_items minus pending model-type reservations).
        Returns (all_available, {component_type: status_dict}).
        """
        model_numbers = self._get_model_numbers_for_config(config)
        required_components = self._resolve_required_components_from_bom("Telefon", config)
        if not required_components:
            # Fallback to legacy behavior if BOM traversal cannot resolve.
            required_components = {
                comp_type: (config.get(ASSET_REGISTRY.get(comp_type, {}).get("quantity_config_key"), 1)
                            if ASSET_REGISTRY.get(comp_type, {}).get("quantity_config_key") else 1)
                for comp_type in model_numbers.keys()
            }
        conn = _get_connection(self.db_path)
        _create_tables(conn)
        _rebuild_stock(conn)   # ensures model_type_reservations are factored in

        inventory_status = {}
        all_available = True

        for comp_type, qty_needed in required_components.items():
            model_num = model_numbers.get(comp_type)
            if not model_num:
                continue
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
        Return available configuration options, combining template structure with inventory availability.
        Only options allowed by the template and in stock are returned.
        """
        conn = _get_connection(self.db_path)
        _create_tables(conn)
        _rebuild_stock(conn)

        PROP_TO_DB_COL: Dict[str, str] = {
            "Material": "material",
            "Color": "color",
            "Finish": "finish",
        }

        available: Dict[str, Any] = {"quantity_fields": []}

        # --- Parse template for allowed options ---
        template = self._config_template
        allowed_options: Dict[str, Dict[str, set]] = {}  # e.g. {"Bottom_Cover": {"material": {"PLA-31212", ...}, ...}}
        for elem in template.get("submodelElements", []):
            if elem.get("idShort") == "Configurable_Components":
                for comp in elem.get("value", []):
                    comp_ref = None
                    comp_type = None
                    allowed: Dict[str, set] = {}
                    for prop in comp.get("value", []):
                        if prop.get("idShort") == "Component_Reference":
                            comp_ref = prop.get("value")
                            # Map AAS id to asset_key
                            for k, v in ASSET_REGISTRY.items():
                                if v.get("type_submodel_prefix") in comp_ref:
                                    comp_type = k
                                    break
                        elif prop.get("idShort", "").startswith("Available_"):
                            field = prop.get("idShort").replace("Available_", "").lower()  # e.g. material
                            allowed[field] = set()
                            for opt in prop.get("value", []):
                                # Support both old structured option entries and
                                # newer plain string entries.
                                if isinstance(opt, str):
                                    allowed[field].add(opt)
                                    continue

                                if isinstance(opt, dict):
                                    # Case A: direct property-like object
                                    if opt.get("idShort") == f"{field.capitalize()}_ID" and opt.get("value") not in (None, ""):
                                        allowed[field].add(opt.get("value"))

                                    # Case B: collection wrapper with nested properties
                                    for opt_prop in opt.get("value", []):
                                        if isinstance(opt_prop, dict) and opt_prop.get("idShort") == f"{field.capitalize()}_ID":
                                            val = opt_prop.get("value")
                                            if val not in (None, ""):
                                                allowed[field].add(val)
                    if comp_type and allowed:
                        allowed_options[comp_type] = allowed

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
                # Read Quantity_Max from the type BOM slot so the cap stays in sync with the AAS data.
                max_qty = total  # fallback: no cap beyond stock
                parent_bom_key = asset_cfg.get("parent_bom_key")
                if parent_bom_key:
                    try:
                        parent_bom = self._load_type_submodel(parent_bom_key, "Bill_Of_Materials")
                        for _elem in parent_bom.get("submodelElements", []):
                            if _elem.get("idShort") != "Components":
                                continue
                            for _slot in _elem.get("value", []):
                                _slot_key = self._component_type_to_asset_key(
                                    self._slot_component_type(_slot)
                                )
                                if _slot_key == asset_key:
                                    raw = self._slot_property_value(_slot, "Quantity_Max")
                                    if raw not in (None, ""):
                                        max_qty = int(raw)
                                    break
                    except Exception:
                        pass  # keep fallback
                count_options = {n: total for n in range(1, min(total, max_qty) + 1)}
                available[options_count_key] = count_options
                available["quantity_fields"].append({
                    "asset_key": asset_key,
                    "label": asset_key.replace("_", " ").replace("-", " "),
                    "config_key": qty_cfg_key,
                    "options_key": options_count_key,
                    "options": count_options,
                })
                continue

            # --- Attribute-option component (e.g. Bottom_Cover, Top_Cover) ---
            prop_map = asset_cfg.get("properties_config_map", {})
            attr_props = {p: col for p, col in PROP_TO_DB_COL.items() if p in prop_map}
            if not attr_props:
                continue  # e.g. PCB has no configurable attributes

            combos_key = f"{asset_key.lower()}_combos"
            combos: List[Dict[str, Any]] = []

            # Get allowed values from template for this component
            allowed = allowed_options.get(asset_key, {})

            for row in conn.execute(
                "SELECT material, color, finish, qty_available FROM inventory_stock "
                "WHERE component_type = ? AND qty_available > 0",
                (asset_key,),
            ).fetchall():
                combo: Dict[str, Any] = {"qty": row["qty_available"]}
                valid = True
                for aas_prop, db_col in attr_props.items():
                    val = row[db_col]
                    combo[db_col] = val
                    # If template restricts allowed values, filter
                    allowed_set = allowed.get(db_col)
                    if allowed_set is not None and val not in allowed_set:
                        valid = False
                if valid:
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
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)

        # Fallback for renamed/migrated submodel filenames.
        type_dir = self.base_path / cfg["type_submodels_dir"]
        candidates = list(type_dir.glob(f"*-Type-{submodel_name}.json"))
        if not candidates:
            raise FileNotFoundError(path)

        def _norm(s: str) -> str:
            return re.sub(r"[^a-z0-9]", "", s.lower())

        def _common_suffix_len(a: str, b: str) -> int:
            i = 0
            while i < min(len(a), len(b)) and a[-(i + 1)] == b[-(i + 1)]:
                i += 1
            return i

        expected_stem = f"{cfg.get('type_submodel_prefix', '')}-Type-{submodel_name}"
        expected_norm = _norm(expected_stem)
        identifiers = [_norm(cfg.get("type_submodel_prefix", ""))]
        identifiers = [x for x in identifiers if x]

        # Exact normalized stem match is preferred for typo-safe recovery.
        for cand in candidates:
            if _norm(cand.stem) == expected_norm:
                with open(cand, encoding="utf-8") as f:
                    return json.load(f)

        best_path = candidates[0]
        best_score = -1
        for cand in candidates:
            cand_norm = _norm(cand.stem)
            score = 0
            for ident in identifiers:
                if ident in cand_norm or cand_norm in ident:
                    score = max(score, len(ident))
                else:
                    score = max(score, _common_suffix_len(ident, cand_norm))
            if score > best_score:
                best_score = score
                best_path = cand

        # Guardrail: do not silently use a mismatched template from another asset.
        if best_score <= 0:
            raise FileNotFoundError(path)

        with open(best_path, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _normalize_token(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (value or "").lower())

    def _component_type_to_asset_key(self, component_type: str) -> Optional[str]:
        norm = self._normalize_token(component_type)
        if not norm:
            return None
        for asset_key, cfg in ASSET_REGISTRY.items():
            c_norm = self._normalize_token(cfg.get("type_submodel_prefix", ""))
            if c_norm and (norm == c_norm or norm.endswith(c_norm) or c_norm.endswith(norm)):
                return asset_key
        return None

    @staticmethod
    def _slot_property_value(slot: Dict[str, Any], prop_id: str) -> Optional[str]:
        for prop in slot.get("value", []):
            if prop.get("idShort") == prop_id:
                return prop.get("value")
        return None

    def _slot_component_type(self, slot: Dict[str, Any]) -> str:
        return self._slot_property_value(slot, "Component_Type") or ""

    def _slot_quantity(self, slot: Dict[str, Any], child_key: Optional[str], config: Dict[str, Any]) -> int:
        # Instance-level explicit quantities win.
        for key in ("Selected_Quantity", "Quantity"):
            raw = self._slot_property_value(slot, key)
            if raw not in (None, ""):
                try:
                    return max(0, int(raw))
                except (TypeError, ValueError):
                    pass

        qty_min = None
        qty_max = None
        raw_min = self._slot_property_value(slot, "Quantity_Min")
        raw_max = self._slot_property_value(slot, "Quantity_Max")
        try:
            if raw_min not in (None, ""):
                qty_min = max(0, int(raw_min))
        except (TypeError, ValueError):
            qty_min = None
        try:
            if raw_max not in (None, ""):
                qty_max = max(0, int(raw_max))
        except (TypeError, ValueError):
            qty_max = None

        if child_key:
            qty_cfg = ASSET_REGISTRY.get(child_key, {}).get("quantity_config_key")
            if qty_cfg:
                flat = self._flatten_config(config)
                try:
                    qty = max(0, int(flat.get(qty_cfg, qty_min if qty_min is not None else 1)))
                    if qty_min is not None:
                        qty = max(qty_min, qty)
                    if qty_max is not None:
                        qty = min(qty_max, qty)
                    return qty
                except (TypeError, ValueError):
                    pass

        if qty_min is not None:
            return qty_min

        return 1

    def _resolve_required_components_from_bom(
        self,
        asset_key: str,
        config: Dict[str, Any],
        multiplier: int = 1,
        stack: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        """
        Recursively expand BOM tree from a product/sub-assembly and return
        leaf component requirements as {component_asset_key: quantity}.
        """
        stack = stack or []
        if asset_key in stack:
            return {}

        cfg = ASSET_REGISTRY.get(asset_key, {})
        if cfg.get("is_component"):
            return {asset_key: multiplier}

        try:
            bom = self._load_type_submodel(asset_key, "Bill_Of_Materials")
        except FileNotFoundError:
            return {}

        totals: Dict[str, int] = {}
        for elem in bom.get("submodelElements", []):
            if elem.get("idShort") != "Components":
                continue
            for slot in elem.get("value", []):
                comp_type = self._slot_component_type(slot)
                child_key = self._component_type_to_asset_key(comp_type)
                if not child_key:
                    continue

                qty = self._slot_quantity(slot, child_key, config)
                eff_qty = multiplier * qty
                if eff_qty <= 0:
                    continue

                child_cfg = ASSET_REGISTRY.get(child_key, {})
                if child_cfg.get("is_component"):
                    totals[child_key] = totals.get(child_key, 0) + eff_qty
                else:
                    nested = self._resolve_required_components_from_bom(
                        child_key,
                        config,
                        multiplier=eff_qty,
                        stack=[*stack, asset_key],
                    )
                    for k, v in nested.items():
                        totals[k] = totals.get(k, 0) + v

        return totals

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
        flat = self._flatten_config(config) if config else {}

        for elem in elements:
            if elem.get("idShort") == "Model_Number_Configuration" and config:
                for child in elem.get("value", []):
                    if child.get("idShort") == "Template":
                        model_number = re.sub(
                            r"\{(\w+)\}",
                            lambda m: str(flat.get(m.group(1), m.group(0))),
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
        flat = self._flatten_config(config)
        for elem in submodel.get("submodelElements", []):
            if elem.get("idShort") != "List_Of_Properties":
                continue
            for prop in elem.get("value", []):
                id_short = prop.get("idShort")
                config_key = prop_map.get(id_short)
                if config_key and config_key in flat:
                    prop["value"] = str(flat[config_key])
                elif id_short in static_map:
                    prop["value"] = static_map[id_short]
        return submodel

    def _expand_assembly_processes_in_bop(self, bop_submodel: Dict, config: Dict[str, Any]) -> Dict:
        """
        Expand assembly processes in Bill_Of_Processes based on component quantities.
        
        Reads the 'Repeatable_Component' metadata from the type template to determine
        which component drives process repetition. Creates additional assembly processes
        for each indexed instance beyond the first (e.g., Fuse_2, Fuse_3, etc.).
        
        Pattern:
        - Assemble_1: base assembly (includes first instance: Fuse_1)
        - Assemble_2, Assemble_3, ...: additional processes for extra instances
        """
        expanded_processes = []
        process_counter = 1

        for elem in bop_submodel.get("submodelElements", []):
            if elem.get("modelType") != "SubmodelElementCollection":
                expanded_processes.append(elem)
                continue

            # This is an assembly process (e.g., Assemble_1)
            base_process = copy.deepcopy(elem)

            # Extract Repeatable_Component metadata if present
            repeatable_component = None
            for sub in base_process.get("value", []):
                if sub.get("idShort") == "Repeatable_Component":
                    repeatable_component = sub.get("value", "")
                    break

            # Extract required components from the base process
            base_components = []
            for sub in base_process.get("value", []):
                if sub.get("idShort") == "Required_Components":
                    base_components = [
                        prop.get("value", "")
                        for prop in sub.get("value", [])
                        if prop.get("idShort", "").startswith("Component_Id_")
                    ]
                    break

            # If Repeatable_Component is specified, use it; otherwise auto-detect
            quantifiable_components = {}
            if repeatable_component:
                # Explicit mode: only expand for the specified component
                try:
                    child_key = self._component_type_to_asset_key(repeatable_component)
                    qty = self._slot_quantity(
                        {"idShort": repeatable_component, "value": [{"idShort": "Component_Type", "value": repeatable_component}]},
                        child_key,
                        config,
                    )
                    if qty > 1:
                        quantifiable_components[repeatable_component] = qty
                except (KeyError, TypeError):
                    pass
            else:
                # Auto-detect mode: find all components with qty > 1
                for comp_ref in base_components:
                    comp_type_match = re.match(r"^([A-Za-z_-]+?)(?:_\d+)?$", comp_ref)
                    if comp_type_match:
                        comp_type = comp_type_match.group(1)
                        try:
                            child_key = self._component_type_to_asset_key(comp_type)
                            qty = self._slot_quantity(
                                {"idShort": comp_type, "value": [{"idShort": "Component_Type", "value": comp_type}]},
                                child_key,
                                config,
                            )
                            if qty > 1:
                                quantifiable_components[comp_type] = qty
                        except (KeyError, TypeError):
                            pass

            # Add the base process
            base_process_id = base_process.get("idShort", f"Assemble_{process_counter}")
            base_process["idShort"] = base_process_id
            expanded_processes.append(base_process)
            process_counter += 1

            # For each quantifiable component, create additional processes (starting from 2nd instance)
            for comp_type, qty in quantifiable_components.items():
                for idx in range(2, qty + 1):
                    # Create new assembly process for this specific instance (Fuse_2, Fuse_3, etc.)
                    new_process = copy.deepcopy(elem)
                    new_process["idShort"] = f"Assemble_{process_counter}"

                    # Update Required_Components to reference the indexed instance
                    for sub in new_process.get("value", []):
                        if sub.get("idShort") == "Required_Components":
                            component_props = sub.get("value", [])
                            for i, prop in enumerate(component_props):
                                if prop.get("idShort", "").startswith("Component_Id_"):
                                    current_value = prop.get("value", "")
                                    # Replace component reference with indexed version
                                    if current_value.startswith(comp_type):
                                        prop["value"] = f"{comp_type}_{idx}"
                            break

                    expanded_processes.append(new_process)
                    process_counter += 1

        # Clean up: remove Repeatable_Component metadata from instances (it's only needed in type templates)
        for elem in expanded_processes:
            if elem.get("modelType") == "SubmodelElementCollection":
                # Remove Repeatable_Component property from the process
                elem["value"] = [
                    sub for sub in elem.get("value", [])
                    if sub.get("idShort") != "Repeatable_Component"
                ]

        bop_submodel["submodelElements"] = expanded_processes
        return bop_submodel

    def _add_empty_instance_refs_to_bom(self, bom_submodel: Dict, config: Dict[str, Any]) -> Dict:
        """
        Build a production-ready instance BOM:
        - Components container as SubmodelElementCollection
        - component slots expanded to indexed entries (<idShort>_1..<idShort>_N)
        - each slot keeps only Component_Type + Instance_Refference
        """
        for elem in bom_submodel.get("submodelElements", []):
            if elem.get("idShort") != "Components":
                continue

            # Instance BOM should be a plain collection, not a typed template list.
            elem["modelType"] = "SubmodelElementCollection"
            for key in ("typeValueListElement", "valueTypeListElement", "orderRelevant"):
                if key in elem:
                    del elem[key]

            expanded_slots = []
            for slot in elem.get("value", []):
                slot_id = slot.get("idShort", "")
                comp_type = self._slot_component_type(slot)
                child_key = self._component_type_to_asset_key(comp_type)
                qty = self._slot_quantity(slot, child_key, config)

                # If already explicitly split in template (e.g. Screw_1), keep as-is.
                is_already_split = bool(re.match(r"^.+_\d+$", slot_id))
                split_count = max(1, qty)

                for i in range(1, split_count + 1):
                    expanded_slot = {
                        "modelType": "SubmodelElementCollection",
                        "idShort": slot_id if is_already_split else f"{slot_id}_{i}",
                        "value": [
                            {
                                "modelType": "Property",
                                "idShort": "Component_Type",
                                "valueType": "xs:string",
                                "value": comp_type,
                            },
                            {
                                "modelType": "Property",
                                "idShort": "Instance_Refference",
                                "valueType": "xs:string",
                                "value": "",
                            },
                        ],
                    }

                    # Preserve non-configurator metadata at slot level when present.
                    if slot.get("semanticId"):
                        expanded_slot["semanticId"] = copy.deepcopy(slot.get("semanticId"))
                    if slot.get("description"):
                        expanded_slot["description"] = copy.deepcopy(slot.get("description"))

                    expanded_slots.append(expanded_slot)

                    # Already-split template slots represent one concrete unit.
                    if is_already_split:
                        break

            elem["value"] = expanded_slots
        return bom_submodel

    def _get_next_instance_num(self, asset_key: str) -> str:
        """Return a UUID-based instance token (32 hex chars, no dashes)."""
        # Keep filenames/path parsing robust by using uuid4().hex (no '-' chars).
        # This remains compatible with existing numeric instance tokens.
        return uuid4().hex

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
                sm = self._add_empty_instance_refs_to_bom(sm, config=config)

            elif sm_name == "Bill_Of_Processes":
                sm = self._expand_assembly_processes_in_bop(sm, config=config)

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
    # Registry reset
    # -------------------------------------------------------------------------

    def reset_registry(self, delete_instances: bool = False) -> bool:
        """
        Reset the v4 order registry:
          - Clears configuration_orders, assembly_log, and model_type_reservations tables.
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

        conn = _get_connection(self.db_path)
        _create_tables(conn)

        # Release any reserved items back to available
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        released = conn.execute(
            "UPDATE inventory_items SET status = 'available', last_updated = ? WHERE status = 'reserved'",
            (now,),
        ).rowcount
        if released:
            print(f"  ✓ Released {released} reserved inventory item(s) back to 'available'")

        # Clear order tables (including v4-specific model_type_reservations)
        conn.execute("DELETE FROM model_type_reservations")
        conn.execute("DELETE FROM assembly_log")
        conn.execute("DELETE FROM configuration_orders")
        print("  ✓ Cleared configuration_orders, assembly_log, and model_type_reservations")

        if delete_instances:
            from inventory_db import INSTANCE_SUBMODEL_DIRS
            instance_shell_dirs = [
                cfg["instance_shell_dir"]
                for cfg in ASSET_REGISTRY.values()
            ]
            instance_submodel_dirs = list(INSTANCE_SUBMODEL_DIRS)

            # ── Delete shells and their submodels from the AAS server ──
            server_deleted = 0
            shell_endpoint = f"{self.server_base}/shells"
            submodel_endpoint = f"{self.server_base}/submodels"

            for rel_dir in set(instance_shell_dirs):
                folder = self.base_path / rel_dir
                if not folder.exists():
                    continue
                for file in folder.glob("*.json"):
                    try:
                        with open(file, encoding="utf-8") as f:
                            shell = json.load(f)
                    except (json.JSONDecodeError, OSError):
                        continue
                    # Delete each referenced submodel from the server
                    for ref in shell.get("submodels", []):
                        for key in ref.get("keys", []):
                            sm_id = key.get("value", "")
                            if sm_id:
                                try:
                                    r = requests.delete(
                                        f"{submodel_endpoint}/{_b64url(sm_id)}",
                                        timeout=5,
                                    )
                                    if r.ok:
                                        server_deleted += 1
                                except requests.ConnectionError:
                                    pass
                    # Delete the shell itself from the server
                    shell_id = shell.get("id", "")
                    if shell_id:
                        try:
                            r = requests.delete(
                                f"{shell_endpoint}/{_b64url(shell_id)}",
                                timeout=5,
                            )
                            if r.ok:
                                server_deleted += 1
                        except requests.ConnectionError:
                            pass

            if server_deleted:
                print(f"  ✓ Deleted {server_deleted} resource(s) from AAS server")
            else:
                print("  ⓘ No resources deleted from AAS server (server not reachable or nothing to delete)")

            # Ensure shared configuration template is deleted as part of full instance/server reset.
            try:
                r = requests.delete(
                    f"{submodel_endpoint}/{_b64url(CONFIG_TEMPLATE_ID)}",
                    timeout=5,
                )
                if r.ok:
                    print("  ✓ Deleted shared Configuration_Template from AAS server")
                else:
                    print("  ⓘ Shared Configuration_Template was not deleted (not found or server rejected delete)")
            except requests.ConnectionError:
                print(f"  ⓘ Could not connect to AAS server at {self.server_base} to delete shared Configuration_Template")

            # ── Delete local instance JSON files ──
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

    # -------------------------------------------------------------------------
    # Phase 1 entry point
    # -------------------------------------------------------------------------

    def create_order(self, config: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        Create a production order:
          1. Validate configuration & check stock
          2. Allocate an order ID
          3. Create Bottom_Cover_PCB, Bottom_Cover_PCB_Fuse, and Telefon shells upfront
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
        required_components = self._resolve_required_components_from_bom("Telefon", config)
        if not required_components:
            required_components = {
                comp_type: (config.get(ASSET_REGISTRY.get(comp_type, {}).get("quantity_config_key"), 1)
                            if ASSET_REGISTRY.get(comp_type, {}).get("quantity_config_key") else 1)
                for comp_type in model_numbers.keys()
            }

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
        flat_config = self._flatten_config(config)
        config_with_order = {**flat_config, "_order_id": order_id}

        for asset_key in ORDER_TIME_SHELL_KEYS:
            inst_num = self._get_next_instance_num(asset_key)
            inst_id = self._create_sa_or_product_shell(asset_key, inst_num, config_with_order)
            shell_instances[asset_key] = inst_id   # full asset ID (not just instance number)
            print(f"  ✓ {asset_key:<20} instance {inst_num}  ({inst_id})")

        # --- Reserve model-type quantities for components ---
        # Components with a quantity_config_key (e.g. Fuse) get one reservation slot
        # per unit required, so each physical instance maps to exactly one slot.
        reservation_slots: Dict[str, str] = {}
        for comp_type, qty in required_components.items():
            model_num = model_numbers.get(comp_type)
            if not model_num:
                continue
            qty = max(0, int(qty))
            if qty <= 0:
                continue
            if qty == 1:
                reservation_slots[comp_type] = model_num
            else:
                for i in range(1, qty + 1):
                    reservation_slots[f"{comp_type}_{i}"] = model_num

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
        "Bottom_Cover": {"material": "PLA-31212", "color": "Red",  "finish": "Glossy"},
        "Top_Cover":    {"material": "PLA-31212", "color": "Red",  "finish": "Glossy"},
        "number_of_fuses": 1,
    },
    {
        "Bottom_Cover": {"material": "PLA-31212", "color": "Blue", "finish": "Glossy"},
        "Top_Cover":    {"material": "PLA-31212", "color": "Blue", "finish": "Glossy"},
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
    parser.add_argument("--reset-registry", action="store_true",
                        help="Clear all configuration orders and assembly history")
    parser.add_argument("--delete-instances", action="store_true",
                        help="Also delete instance JSON files and clear inventory (use with --reset-registry)")
    args = parser.parse_args()

    cfg = TelefonConfiguratorV4()

    if args.reset_registry:
        cfg.reset_registry(delete_instances=args.delete_instances)
        return

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
