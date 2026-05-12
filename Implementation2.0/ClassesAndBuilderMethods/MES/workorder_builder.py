"""
workorder_builder.py — Build a WorkOrderMessage by recursively traversing the
assembly hierarchy defined in shell preset YAML files.

Does NOT query BaSyx for structure — uses preset YAMLs as the source of truth.
The BaSyx instance shell IRIs (from shell_uploader) are used as ComponentReferences
in the Ingredients dict.

WorkOrder format matches WorkOrderExampleComplex.json exactly.
"""

import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "InformationModels"))
sys.path.insert(0, str(Path(__file__).parent))
from MessageStructure import WorkOrderMessage
import basyx_client

log = logging.getLogger(__name__)

PRESETS_DIR = Path(__file__).parent.parent / "BaSyx_AAS_Generator" / "shell_presets"

# Maps the last IRI segment (asset_name) to a preset file name
ASSET_NAME_TO_PRESET: dict[str, str] = {
    "BottomCoverDrilling_SA": "bottom_cover_drilling_assembly",
    "BottomCoverPCB_SA":      "bottom_cover_pcb_assembly",
    "BottomCoverPCBFuse_SA":  "bottom_cover_pcb_fuse_assembly",
}

# Derives (display_name, semantic_iri) from a CapabilityParams key like "BitDiameter_mm"
_UNIT_SEMANTIC: list[tuple[str, str, str]] = [
    # (suffix, unit_label, semantic_iri)  — longest first
    ("_mm_per_s", "mm_per_s", "https://aausmartlab.org/Semantics/mm_per_s"),
    ("_x_mm",     "mm",       "https://aausmartlab.org/Semantics/mm"),
    ("_y_mm",     "mm",       "https://aausmartlab.org/Semantics/mm"),
    ("_z_mm",     "mm",       "https://aausmartlab.org/Semantics/mm"),
    ("_RPM",      "RPM",      "https://aausmartlab.org/Semantics/RPM"),
    ("_mm",       "mm",       "https://aausmartlab.org/Semantics/mm"),
    ("_g",        "gram",     "https://aausmartlab.org/Semantics/gram"),
    ("_s",        "s",        "https://aausmartlab.org/Semantics/s"),
]


def _parse_param(key: str, value: Any) -> tuple[str, dict]:
    """Convert a CapabilityParams key/value to (display_name, { semantic_id, value })."""
    for suffix, _unit, semantic in _UNIT_SEMANTIC:
        if key.endswith(suffix):
            base = key[: -len(suffix)]
            # Capitalise axis letter for _x_mm / _y_mm / _z_mm
            if suffix in ("_x_mm", "_y_mm", "_z_mm"):
                axis = suffix[1].upper()  # "x" → "X"
                base = f"{base}_{axis}"
            return base, {"semantic_id": semantic, "value": value}
    return key, {"semantic_id": "https://aausmartlab.org/Semantics/Unknown", "value": value}


def _flatten_capability_params(cap_params: dict) -> dict:
    """
    Flatten nested CapabilityParams dict into a single-level dict of
    { display_name: { semantic_id, value } }.
    Skips non-numeric values (e.g. OperationLabel, SupportedComponents).
    """
    result = {}
    for _group, group_val in cap_params.items():
        if not isinstance(group_val, dict):
            continue
        for param_key, param_val in group_val.items():
            if not isinstance(param_val, (int, float)):
                continue
            display_name, param_dict = _parse_param(param_key, param_val)
            result[display_name] = param_dict
    return result


def _resolve_sm_value(elem: dict) -> str | float | None:
    """Extract a scalar value from a BaSyx submodel element."""
    val = elem.get("value")
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, str) and val:
        return val
    if isinstance(val, dict):
        keys = val.get("keys", [])
        if keys:
            return keys[-1].get("value")
    return None


def _fetch_aas_properties(shell_iri: str, basyx_url: str) -> dict:
    """
    Pull MaterialProperties + PhysicalDimensions from the component type shell
    in BaSyx. Resolves the Properties submodel IRI from the shell's own references
    rather than guessing the suffix, so it works for both UI-uploaded and
    MES-generated shells.

    Returns { "MaterialProperties": {...}, "PhysicalDimensions": {...} }.
    All values use the WorkOrder semanticId format (capital S).
    """
    empty = {"MaterialProperties": {}, "PhysicalDimensions": {}}
    try:
        # Resolve shell — tries exact IRI first, then falls back to idShort search
        shell = basyx_client.resolve_shell(shell_iri, basyx_url)
        if not shell:
            log.debug("Shell not found in BaSyx: %s", shell_iri)
            return empty
        actual_iri = shell.get("id", shell_iri)
        sm_iris = basyx_client.get_submodel_refs_for_shell(actual_iri, basyx_url)
        props_iri = next((iri for iri in sm_iris if "/Properties" in iri), None)
        if not props_iri:
            # Fallback: try both IRI conventions against the resolved IRI
            for candidate in (
                f"{actual_iri}/Submodels/Properties",
                f"{actual_iri}/Submodel/Properties/0",
            ):
                sm = basyx_client.fetch_submodel(candidate, basyx_url)
                if sm:
                    props_iri = candidate
                    break

        if not props_iri:
            log.debug("No Properties submodel found for %s", shell_iri)
            return empty

        sm = basyx_client.fetch_submodel(props_iri, basyx_url)
        if not sm:
            return empty

        elements = sm.get("submodelElements", [])
        mat_props: dict = {}
        phys_dims: dict = {}

        mat_col = basyx_client.find_element_by_idshort(elements, "MaterialProperties")
        if mat_col and isinstance(mat_col.get("value"), list):
            for elem in mat_col["value"]:
                id_short = elem.get("idShort", "")
                val = _resolve_sm_value(elem)
                if val is not None and id_short:
                    mat_props[id_short] = {
                        "semanticId": f"https://aausmartlab.org/Semantics/{id_short}",
                        "value": str(val),
                    }

        phys_col = basyx_client.find_element_by_idshort(elements, "PhysicalDimensions")
        if phys_col and isinstance(phys_col.get("value"), list):
            for elem in phys_col["value"]:
                id_short = elem.get("idShort", "")
                val = _resolve_sm_value(elem)
                if val is not None and id_short:
                    phys_dims[id_short] = {
                        "semanticId": f"https://aausmartlab.org/Semantics/{id_short}",
                        "value": str(val),
                    }

        log.debug(
            "Fetched AAS properties for %s: mat=%d phys=%d",
            shell_iri, len(mat_props), len(phys_dims),
        )
        return {"MaterialProperties": mat_props, "PhysicalDimensions": phys_dims}

    except Exception as exc:
        log.warning("Could not fetch AAS properties for %s: %s", shell_iri, exc)
        return empty


def _load_preset(name: str) -> dict:
    path = PRESETS_DIR / f"{name}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


_UUID_RE = re.compile(
    r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def _is_sub_assembly_iri(iri: str) -> bool:
    """Return True if the IRI belongs to a sub-assembly (not a raw component)."""
    return "/Shells/Assembly/" in iri


def _asset_name_from_iri(iri: str) -> str:
    """Last non-UUID segment of an IRI."""
    clean = _UUID_RE.sub("", iri.rstrip("/"))
    return clean.split("/")[-1]


def _type_iri_from_full(iri: str) -> str:
    """Strip trailing UUID segment to get the component type IRI.

    e.g. …/BottomCover_ABS_Black/37d24975-… → …/BottomCover_ABS_Black
    """
    return _UUID_RE.sub("", iri.rstrip("/"))


def _make_properties_for_slot(slot_cfg: dict) -> dict:
    """Build a Properties dict (MaterialProperties + PhysicalDimensions) from slot config."""
    customer = slot_cfg.get("properties") or {}
    mat = {}
    for prop_key, sem_key in (
        ("material", "Material"),
        ("color", "Color"),
        ("finish", "Finish"),
    ):
        val = customer.get(prop_key)
        if val:
            mat[sem_key] = {
                "semanticId": f"https://aausmartlab.org/Semantics/{sem_key}",
                "value": val,
            }
    dims = {}
    for prop_key, sem_key in (
        ("length", "Length"),
        ("width", "Width"),
        ("height", "Height"),
    ):
        val = customer.get(prop_key)
        if val is not None:
            dims[sem_key] = {
                "semanticId": "https://aausmartlab.org/Semantics/mm",
                "value": str(val),
            }
    return {"MaterialProperties": mat, "PhysicalDimensions": dims}


def build_workorder(
    final_preset: dict,
    configuration: list[dict],
    shell_iris: dict[str, str],
    order_id: str,
    basyx_url: str | None = None,
) -> WorkOrderMessage:
    """
    Recursively traverse the preset assembly hierarchy and build a WorkOrderMessage.

    Args:
        final_preset: merged final product preset dict
        configuration: list of { slot, componentTypeId, category, quantity, properties }
        shell_iris: { asset_name → instance_shell_iri } from shell_uploader
        order_id: e.g. "ORD-ABCD1234"

    Returns: WorkOrderMessage ready for publishing.
    """
    ingredients: dict[str, dict] = {}
    properties: dict[str, dict] = {}
    assemblies: dict[str, dict] = {}
    process_steps: dict[str, dict] = {}

    _ing_counter = [0]
    _step_counter = [0]
    _last_step_id: list[str | None] = [None]  # global across recursion levels

    # Build a quick lookup: componentTypeId → slot config
    slot_by_type: dict[str, dict] = {
        s["componentTypeId"]: s for s in configuration if s.get("componentTypeId")
    }
    # Also index by category for fuzzy matching
    slot_by_category: dict[str, dict] = {
        (s.get("category") or "").lower(): s for s in configuration if s.get("category")
    }

    def _next_ing() -> str:
        _ing_counter[0] += 1
        return f"Ingredient_{_ing_counter[0]}"

    def _next_step() -> str:
        _step_counter[0] += 1
        return f"{_step_counter[0]}x1"

    def _find_slot_config(ref_iri: str) -> dict:
        """Find the matching slot configuration for a raw component IRI."""
        asset_name = _asset_name_from_iri(ref_iri)
        # 1. Try exact componentTypeId match
        for slot in configuration:
            ctype = slot.get("componentTypeId", "")
            if ctype and (ctype == asset_name or ctype in ref_iri or asset_name in ctype):
                return slot
        # 2. Try category/slot-label match, normalising spaces→underscores
        iri_lower = ref_iri.lower()
        for slot in configuration:
            for field in ("category", "slot"):
                raw = (slot.get(field) or "").lower().replace(" ", "_")
                if raw and raw in iri_lower:
                    return slot
        return {}

    def resolve(preset: dict) -> list[str]:
        """
        Process one preset level.
        Returns the list of ingredient IDs that are the OUTPUT(s) of this level.
        """
        bom_entries = (
            preset.get("submodels", {})
            .get("BillOfMaterials", {})
            .get("BOMEntries", [])
        )
        bop_steps = (
            preset.get("submodels", {})
            .get("BillOfProcesses", {})
            .get("ProcessSteps", [])
        )
        asset_name = preset.get("asset_name", "")
        asset_type = preset.get("asset_type", "")
        shell_type = preset.get("shell", "sub_assembly_shell")

        # ── Step 1: collect input ingredient IDs from BOM ──────────────────
        input_ids: list[str] = []

        for entry in bom_entries:
            ref_iri = entry.get("ProductFamilyRef", "")
            if not ref_iri:
                continue

            if _is_sub_assembly_iri(ref_iri):
                # Recurse into sub-assembly preset
                sub_asset_name = _asset_name_from_iri(ref_iri)
                sub_preset_name = ASSET_NAME_TO_PRESET.get(sub_asset_name)
                if not sub_preset_name:
                    log.warning("No preset mapping for sub-assembly IRI: %s", ref_iri)
                    continue
                sub_preset = _load_preset(sub_preset_name)
                sub_output_ids = resolve(sub_preset)
                input_ids.extend(sub_output_ids)
            else:
                # Raw component → create leaf ingredient.
                # ComponentReference = type-level IRI (no UUID) so the production
                # line knows what type to pick; instance assignment happens there.
                ing_id = _next_ing()
                slot_cfg = _find_slot_config(ref_iri)

                # aasTypeIri from DB carries the full UUID IRI (the actual BaSyx shell).
                # Strip UUID for ComponentReference; keep full for property fetch.
                full_iri = (slot_cfg.get("aasTypeIri") if slot_cfg else None) or ref_iri
                component_ref_iri = _type_iri_from_full(full_iri)
                ingredients[ing_id] = {"ComponentReference": component_ref_iri}

                # Fetch properties from the full UUID IRI (exists in BaSyx).
                aas_props = (
                    _fetch_aas_properties(full_iri, basyx_url)
                    if basyx_url
                    else {"MaterialProperties": {}, "PhysicalDimensions": {}}
                )
                customer_props = _make_properties_for_slot(slot_cfg) if slot_cfg else {}
                properties[ing_id] = {
                    "MaterialProperties": {
                        **aas_props.get("MaterialProperties", {}),
                        **customer_props.get("MaterialProperties", {}),
                    },
                    "PhysicalDimensions": {
                        **aas_props.get("PhysicalDimensions", {}),
                        **customer_props.get("PhysicalDimensions", {}),
                    },
                }
                input_ids.append(ing_id)

        # ── Step 2: process BOP steps ───────────────────────────────────────
        if shell_type == "final_product_shell":
            level_iri_template = (
                f"https://aausmartlab.org/Shells/Configuration/{asset_type}/{asset_name}"
            )
        else:
            level_iri_template = (
                f"https://aausmartlab.org/Shells/Assembly/{asset_type}/{asset_name}"
            )

        instance_iri = shell_iris.get(asset_name, level_iri_template)

        output_id: str | None = None

        for step in bop_steps:
            process_type = step.get("ProcessType", "")
            required_comps = step.get("RequiredComponents", [])
            cap_params = step.get("CapabilityParams", {})

            if process_type == "Assemble":
                # Create output ingredient representing the assembled result
                output_id = _next_ing()
                ingredients[output_id] = {"ComponentReference": instance_iri}
                properties[output_id] = {"MaterialProperties": {}, "PhysicalDimensions": {}}
                assemblies[output_id] = {"Ingredients": list(input_ids)}

                step_id = _next_step()
                cap_ref = "https://aausmartlab.org/Submodels/Capability/Assemble"
                if output_id not in process_steps:
                    process_steps[output_id] = {}
                step_name = f"ProcessStep{_step_counter[0]}"
                deps = [_last_step_id[0]] if _last_step_id[0] else []
                process_steps[output_id][step_name] = {
                    "CapabilityReference": cap_ref,
                    "ProcessStepId": step_id,
                    "Dependencies": deps,
                    "Parameters": {"InputComponents": list(input_ids)},
                }
                _last_step_id[0] = step_id

            else:
                # Non-assemble step (e.g. Drilling) — targets a specific raw ingredient
                target_id = _find_target_ingredient(input_ids, required_comps, ingredients)
                if target_id is None and input_ids:
                    target_id = input_ids[0]

                if target_id:
                    step_id = _next_step()
                    # Use ProcessType if explicit, else fall back to Operation field
                    cap_name = process_type or step.get("Operation", "")
                    cap_ref = f"https://aausmartlab.org/Submodels/Capability/{cap_name}"
                    params = _flatten_capability_params(cap_params) if cap_params else {}

                    if target_id not in process_steps:
                        process_steps[target_id] = {}
                    step_name = f"ProcessStep{_step_counter[0]}"
                    deps = [_last_step_id[0]] if _last_step_id[0] else []
                    process_steps[target_id][step_name] = {
                        "CapabilityReference": cap_ref,
                        "ProcessStepId": step_id,
                        "Dependencies": deps,
                        "Parameters": params,
                    }
                    _last_step_id[0] = step_id

                    # Create output ingredient for the processed component
                    output_id = _next_ing()
                    ingredients[output_id] = {"ComponentReference": instance_iri}
                    properties[output_id] = {"MaterialProperties": {}, "PhysicalDimensions": {}}
                    assemblies[output_id] = {"Ingredients": [target_id]}

        if output_id:
            return [output_id]
        return list(input_ids)

    def _find_target_ingredient(
        input_ids: list[str],
        required_comps: list[str],
        ingredients: dict[str, dict],
    ) -> str | None:
        for ing_id in input_ids:
            ref = ingredients[ing_id]["ComponentReference"]
            for req in required_comps:
                if req.lower() in ref.lower() or ref.endswith(req):
                    return ing_id
        return None

    # ── Build the full WorkOrder ────────────────────────────────────────────
    final_output_ids = resolve(final_preset)
    final_asset_name = final_preset.get("asset_name", "")
    product_reference = shell_iris.get(final_asset_name, "")

    return WorkOrderMessage(
        timestamp=datetime.now(),
        order_id=order_id,
        priority=0,
        issue_date=datetime.now(),
        product_reference=product_reference,
        ingredients=ingredients,
        properties=properties,
        assemblies=assemblies,
        process_steps=process_steps,
    )
