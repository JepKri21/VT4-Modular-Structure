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

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "InformationModels"))
sys.path.insert(0, str(Path(__file__).parent))
from MessageStructure import WorkOrderMessage
import basyx_client

log = logging.getLogger(__name__)

PRESETS_DIR = Path(__file__).parent.parent / "BaSyx_AAS_Generator" / "shell_presets"

# Maps the last IRI segment (asset_name) to a preset file name
ASSET_NAME_TO_PRESET: dict[str, str] = {
    "BottomCoverDrillingSA": "bottom_cover_drilling_assembly",
    "BottomCoverPCBSA":      "bottom_cover_pcb_assembly",
    "BottomCoverPCBFuseSA":  "bottom_cover_pcb_fuse_assembly",
}

# Cache: component variant IRI → all property sections fetched from BaSyx
_TYPE_SHELL_PROPS_CACHE: dict[str, dict] = {}

_XS_NUMERIC = {
    "xs:integer", "xs:int", "xs:long", "xs:short", "xs:byte",
    "xs:double", "xs:float", "xs:decimal",
}

def _coerce_value(raw, value_type: str):
    """Convert a BaSyx string value to int or float when the template says so."""
    if raw is None:
        return raw
    vt = (value_type or "").lower()
    if vt in ("xs:integer", "xs:int", "xs:long", "xs:short", "xs:byte"):
        try:
            return int(raw)
        except (ValueError, TypeError):
            pass
    elif vt in ("xs:double", "xs:float", "xs:decimal"):
        try:
            return float(raw)
        except (ValueError, TypeError):
            pass
    return raw


def _elem_semantic_id(elem: dict) -> str:
    """Extract the semantic IRI from a BaSyx v3 element dict."""
    sem = elem.get("semanticId") or {}
    keys = sem.get("keys", [])
    return keys[-1].get("value", "") if keys else ""



def _get_type_shell_properties(component_iri: str, basyx_url: str) -> dict:
    """
    Fetch static properties (e.g. Length/Width/Height) from the category type shell
    in BaSyx.  The category type shell carries a TEMPLATE-kind Properties submodel
    populated with default values that are the same for every variant in that category.

    Strategy:
      1. Derive category type IRI by stripping the last path segment from the
         variant IRI:  …/Component/BottomCover/BottomCoverPETGGray
                     → …/Component/BottomCover
      2. Fetch the Properties template at {category_type_iri}/Properties.
      3. Fall back to {component_iri}/Properties (variant-level) if not found.
    """
    if component_iri in _TYPE_SHELL_PROPS_CACHE:
        return _TYPE_SHELL_PROPS_CACHE[component_iri]

    # Derive category type IRI: strip the variant name (last path segment).
    category_type_iri = component_iri.rstrip("/").rsplit("/", 1)[0]
    category_props_iri = f"{category_type_iri}/Properties"

    log.info("category-type props fetch: %s", category_props_iri)
    sm = basyx_client.fetch_submodel(category_props_iri, basyx_url)

    if not sm:
        # Fallback: try the variant shell's own Properties submodel.
        variant_props_iri = f"{component_iri}/Properties"
        log.info("  not found, trying variant: %s", variant_props_iri)
        sm = basyx_client.fetch_submodel(variant_props_iri, basyx_url)

    if not sm:
        log.warning("  no Properties submodel found for %s", component_iri)
        _TYPE_SHELL_PROPS_CACHE[component_iri] = {}
        return {}

    # Read every top-level collection present (PhysicalDimensions,
    # ElectricalProperties, MaterialProperties, …) without hardcoding the set.
    result: dict = {}
    for col in sm.get("submodelElements", []):
        if col.get("modelType") != "SubmodelElementCollection":
            continue
        children = col.get("value", [])
        if not isinstance(children, list):
            continue
        section = col["idShort"]
        result[section] = {
            elem["idShort"]: {
                "SemanticId": _elem_semantic_id(elem),
                "value": _coerce_value(elem.get("value"), elem.get("valueType", "")),
            }
            for elem in children
            if elem.get("idShort") and elem.get("value") is not None
        }

    log.info("  → sections=%s", list(result.keys()) or "EMPTY")
    _TYPE_SHELL_PROPS_CACHE[component_iri] = result
    return result

def _fetch_required_cap_params(shell_iri: str, operation: str, basyx_url: str) -> dict:
    """
    Fetch capability parameters for a process step from BaSyx.

    Looks up the shell's BillOfProcesses submodel, finds the step whose
    Operation matches, follows its RequiredCapabilityRef, and returns
    { id_short: { SemanticId, value } } for every leaf Property element.
    Returns an empty dict if the BOP or ref is not found.
    """
    bop_iri = f"{shell_iri}/BillOfProcesses"
    bop = basyx_client.fetch_submodel(bop_iri, basyx_url)
    if not bop:
        log.warning("BOP not found in BaSyx: %s", bop_iri)
        return {}

    steps_coll = basyx_client.find_element_by_idshort(
        bop.get("submodelElements", []), "ProcessSteps"
    )
    if not steps_coll:
        return {}

    cap_sm_iri: str | None = None
    for step_elem in (steps_coll.get("value") or []):
        op_elem = basyx_client.find_element_by_idshort(
            step_elem.get("value", []), "Operation"
        )
        if (op_elem or {}).get("value", "") == operation:
            ref_elem = basyx_client.find_element_by_idshort(
                step_elem.get("value", []), "RequiredCapabilityRef"
            )
            if ref_elem:
                keys = (ref_elem.get("value") or {}).get("keys", [])
                if keys:
                    cap_sm_iri = keys[-1].get("value", "")
            break

    if not cap_sm_iri:
        log.warning("No RequiredCapabilityRef for operation=%s in %s", operation, bop_iri)
        return {}

    cap_sm = basyx_client.fetch_submodel(cap_sm_iri, basyx_url)
    if not cap_sm:
        log.warning("Required capability submodel not found: %s", cap_sm_iri)
        return {}

    result: dict = {}

    def _walk(elements: list) -> None:
        for elem in elements:
            if elem.get("modelType") == "Property" and elem.get("value") is not None:
                id_short = elem.get("idShort", "")
                if id_short:
                    result[id_short] = {
                        "SemanticId": _elem_semantic_id(elem),
                        "value": _coerce_value(elem.get("value"), elem.get("valueType", "")),
                    }
            children = elem.get("value", [])
            if isinstance(children, list):
                _walk(children)

    _walk(cap_sm.get("submodelElements", []))
    return result






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

    e.g. …/BottomCoverABSBlack/37d24975-… → …/BottomCoverABSBlack
    """
    return _UUID_RE.sub("", iri.rstrip("/"))


def _make_properties_for_slot(slot_cfg: dict) -> dict:
    """Build a Properties dict (MaterialProperties + PhysicalDimensions) from slot config."""
    customer = slot_cfg.get("properties") or {}
    mat = {}
    for prop_key, id_short, sem_fragment in (
        ("material", "Material",   "Material"),
        ("color",    "Color",      "Color"),
        ("finish",   "Finish",     "SurfaceFinish"),
    ):
        val = customer.get(prop_key)
        if val:
            mat[id_short] = {
                "SemanticId": f"https://aausmartlab.org/Semantics/{sem_fragment}",
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
                "SemanticId": "https://aausmartlab.org/Semantics/mm",
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

    _name_count: dict[str, int] = {}
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

    def _make_ing_id(name: str) -> str:
        _name_count[name] = _name_count.get(name, 0) + 1
        n = _name_count[name]
        return name if n == 1 else f"{name}_{n}"

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
                log.debug("slot match (typeId) for %s → slot=%s", asset_name, slot.get("slot"))
                return slot
        # 2. Try category/slot-label match, normalising spaces→underscores
        iri_lower = ref_iri.lower()
        for slot in configuration:
            for field in ("category", "slot"):
                raw = (slot.get(field) or "").lower().replace(" ", "_")
                if raw and raw in iri_lower:
                    log.debug("slot match (%s) for %s → slot=%s", field, asset_name, slot.get("slot"))
                    return slot
        log.warning("no slot match for %s — properties will be empty", asset_name)
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
                # Raw component — resolve the actual ordered component IRI first,
                # then use it as the ingredient name so "BottomCoverPETGGray"
                # appears instead of the generic BOM family name "BottomCover3DP".
                slot_cfg = _find_slot_config(ref_iri)
                type_iri = (slot_cfg.get("aasTypeIri") if slot_cfg else None) or ref_iri
                component_ref_iri = _type_iri_from_full(type_iri)
                category_iri = component_ref_iri.rstrip("/").rsplit("/", 1)[0]

                ing_id = _make_ing_id(_asset_name_from_iri(component_ref_iri))

                ingredients[ing_id] = {"ComponentReference": category_iri}

                # Static defaults from the category type shell in BaSyx
                # (e.g. .../Component/Fuse → Length/Width/Height).
                # Delta (Material/Color/Finish) comes from the order configuration.
                # Order values override type-shell defaults.
                type_props = _get_type_shell_properties(component_ref_iri, basyx_url) if basyx_url else {}
                order_props = _make_properties_for_slot(slot_cfg) if slot_cfg else {}
                merged: dict = {}
                for section in set(type_props) | set(order_props):
                    merged[section] = {**type_props.get(section, {}), **order_props.get(section, {})}
                properties[ing_id] = merged
                log.info(
                    "ingredient %s — %s",
                    ing_id,
                    {s: list(v.keys()) for s, v in merged.items()},
                )
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

            if process_type == "Assemble":
                # Create output ingredient representing the assembled result
                output_id = _make_ing_id(asset_name)
                ingredients[output_id] = {"ComponentReference": instance_iri}
                properties[output_id] = {}
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
                    params = _fetch_required_cap_params(instance_iri, cap_name, basyx_url) if basyx_url else {}

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
                    output_id = _make_ing_id(asset_name)
                    ingredients[output_id] = {"ComponentReference": instance_iri}
                    properties[output_id] = {}
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
                req_l = req.lower()
                if req_l in ref.lower() or ref.endswith(req) or req_l in ing_id.lower():
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
