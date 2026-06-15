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
import preset_loader

log = logging.getLogger(__name__)

PRESETS_DIR = Path(__file__).parent.parent / "BaSyx_AAS_Generator" / "shell_presets"
SHELL_TEMPLATES_DIR = Path(__file__).parent.parent / "BaSyx_AAS_Generator" / "shell_templates"

# Maps the last IRI segment (asset_name) to a preset file name
ASSET_NAME_TO_PRESET: dict[str, str] = {
    "BottomCoverPCB":      "bottom_cover_pcb_assembly",
    "BottomCoverPCBFuse":  "bottom_cover_pcb_fuse_assembly",
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
    Fetch static properties from the category type shell in BaSyx.

    The category type shell carries default values shared by every variant
    in that category (e.g. Length/Width/Height for all fuses).

    Strategy:
      1. Derive category IRI by stripping the last path segment from the variant IRI:
           …/Component/Fuse/Fuse16ASB → …/Component/Fuse
      2. Fetch {category_iri}/Properties.
      3. Fall back to {component_iri}/Properties if the category submodel is absent.
    """
    if component_iri in _TYPE_SHELL_PROPS_CACHE:
        return _TYPE_SHELL_PROPS_CACHE[component_iri]

    category_type_iri = component_iri.rstrip("/").rsplit("/", 1)[0]
    category_props_iri = f"{category_type_iri}/Properties"

    log.info("category-type props fetch: %s", category_props_iri)
    sm = basyx_client.fetch_submodel(category_props_iri, basyx_url)

    if not sm:
        variant_props_iri = f"{component_iri}/Properties"
        log.info("  not found, trying variant: %s", variant_props_iri)
        sm = basyx_client.fetch_submodel(variant_props_iri, basyx_url)

    if not sm:
        log.warning("  no Properties submodel found for %s", component_iri)
        _TYPE_SHELL_PROPS_CACHE[component_iri] = {}
        return {}

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
                "semanticId": _elem_semantic_id(elem),
                "value": _coerce_value(elem.get("value"), elem.get("valueType", "")),
            }
            for elem in children
            if elem.get("idShort") and elem.get("value") is not None
        }

    log.info("  -> sections=%s", list(result.keys()) or "EMPTY")
    _TYPE_SHELL_PROPS_CACHE[component_iri] = result
    return result

def _fetch_required_component_iris(shell_iri: str, operation: str, basyx_url: str) -> list[str]:
    """
    Read RequiredComponents model references from the BOP in BaSyx and resolve
    each one to the ComponentTypeReference IRI of the referenced BOM entry.

    Returns a list of component type IRIs, e.g.
    ["https://aausmartlab.org/Shells/Component/BottomCover",
     "https://aausmartlab.org/Shells/Component/PCB"].
    """
    bop_iri = f"{shell_iri}/BillOfProcesses"
    bop = basyx_client.fetch_submodel(bop_iri, basyx_url)
    if not bop:
        log.warning("BOP not found for RequiredComponents resolution: %s", bop_iri)
        return []

    steps_coll = basyx_client.find_element_by_idshort(bop.get("submodelElements", []), "ProcessSteps")
    if not steps_coll:
        return []

    req_refs: list[dict] = []
    for step_elem in (steps_coll.get("value") or []):
        op_elem = basyx_client.find_element_by_idshort(step_elem.get("value", []), "Operation")
        if (op_elem or {}).get("value", "") != operation:
            continue
        req_list = basyx_client.find_element_by_idshort(step_elem.get("value", []), "RequiredComponents")
        if req_list:
            req_refs = req_list.get("value") or []
        break

    iris: list[str] = []
    for ref_elem in req_refs:
        keys = (ref_elem.get("value") or {}).get("keys", [])
        # Expected: [Submodel: bom_iri, SMC: "BOMEntries", SMC: entry_id_short]
        if len(keys) < 3:
            continue
        bom_sm_iri = keys[0].get("value", "")
        entry_id_short = keys[2].get("value", "")
        if not bom_sm_iri or not entry_id_short:
            continue

        bom_sm = basyx_client.fetch_submodel(bom_sm_iri, basyx_url)
        if not bom_sm:
            log.warning("BOM submodel not found: %s", bom_sm_iri)
            continue

        entries_coll = basyx_client.find_element_by_idshort(bom_sm.get("submodelElements", []), "BOMEntries")
        if not entries_coll:
            continue

        entry_elem = basyx_client.find_element_by_idshort((entries_coll.get("value") or []), entry_id_short)
        if not entry_elem:
            log.warning("BOM entry %s not found in %s", entry_id_short, bom_sm_iri)
            continue

        comp_ref_elem = basyx_client.find_element_by_idshort(entry_elem.get("value", []), "ComponentTypeReference")
        if not comp_ref_elem:
            continue

        ref_keys = (comp_ref_elem.get("value") or {}).get("keys", [])
        if ref_keys:
            iri = ref_keys[0].get("value", "")
            if iri:
                iris.append(iri)

    return iris


def _fetch_required_cap_params(shell_iri: str, operation: str, basyx_url: str) -> tuple[dict, str | None]:
    """
    Fetch capability parameters for a process step from BaSyx.

    Looks up the shell's BillOfProcesses submodel, finds the step whose
    Operation matches, follows its RequiredCapabilityRef, and returns
    ({ id_short: { SemanticId, value } }, required_capability_submodel_iri).
    Returns ({}, None) if the BOP or ref is not found.
    """
    bop_iri = f"{shell_iri}/BillOfProcesses"
    bop = basyx_client.fetch_submodel(bop_iri, basyx_url)
    if not bop:
        log.warning("BOP not found in BaSyx: %s", bop_iri)
        return {}, None

    steps_coll = basyx_client.find_element_by_idshort(
        bop.get("submodelElements", []), "ProcessSteps"
    )
    if not steps_coll:
        return {}, None

    cap_sm_iri: str | None = None
    for step_elem in (steps_coll.get("value") or []):
        op_elem = basyx_client.find_element_by_idshort(
            step_elem.get("value", []), "Operation"
        )
        if (op_elem or {}).get("value", "") == operation:
            ref_elem = basyx_client.find_element_by_idshort(
                step_elem.get("value", []), "RequiredCapabilityReference"
            )
            if ref_elem:
                keys = (ref_elem.get("value") or {}).get("keys", [])
                if keys:
                    cap_sm_iri = keys[-1].get("value", "")
            break

    if not cap_sm_iri:
        log.warning("No RequiredCapabilityReference for operation=%s in %s", operation, bop_iri)
        return {}, None

    cap_sm = basyx_client.fetch_submodel(cap_sm_iri, basyx_url)
    if not cap_sm:
        log.warning("Required capability submodel not found: %s", cap_sm_iri)
        return {}, cap_sm_iri

    def _parse_elements(elements: list) -> dict:
        """Parse BaSyx elements into a dict, preserving collection nesting."""
        parsed: dict = {}
        for elem in elements:
            model_type = elem.get("modelType", "")
            id_short = elem.get("idShort", "")
            if not id_short:
                continue
            if model_type == "Property" and elem.get("value") is not None:
                parsed[id_short] = {
                    "SemanticId": _elem_semantic_id(elem),
                    "value": _coerce_value(elem.get("value"), elem.get("valueType", "")),
                }
            elif model_type == "SubmodelElementCollection":
                children = elem.get("value", [])
                if isinstance(children, list):
                    nested = _parse_elements(children)
                    if nested:
                        parsed[id_short] = nested
        return parsed

    params_coll = basyx_client.find_element_by_idshort(
        cap_sm.get("submodelElements", []), "Parameters"
    )
    if not params_coll:
        return {}, cap_sm_iri
    return _parse_elements(params_coll.get("value", [])), cap_sm_iri






def _load_preset(name: str) -> dict:
    path = PRESETS_DIR / f"{name}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _type_iri_base_from_shell_template(shell_type: str) -> str:
    """Derive the type-level IRI base from a shell template's id_pattern.

    Reads id_pattern (e.g. "…/Shells/Product/{asset_type}/{asset_name}_{uuid}")
    and strips everything from /{asset_name} onward, leaving the {asset_type}
    token in place for the caller to substitute.

    Returns "" if the template file is missing or has no id_pattern.
    """
    path = SHELL_TEMPLATES_DIR / f"{shell_type}.yaml"
    try:
        with open(path, encoding="utf-8") as f:
            tmpl = yaml.safe_load(f)
        id_pattern = tmpl.get("id_pattern", "")
        return re.sub(r"/\{asset_name\}.*$", "", id_pattern)
    except Exception:
        return ""


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


_NUMERIC_PREFIX_RE = re.compile(r"^([\d.]+)")


def _parse_electrical_value(val):
    """Strip a unit suffix from strings like '16A' or '250V' and return a number."""
    if not isinstance(val, str):
        return val
    m = _NUMERIC_PREFIX_RE.match(val.strip())
    if m:
        num = m.group(1)
        try:
            return int(num) if "." not in num else float(num)
        except ValueError:
            pass
    return val


_MATERIALS_BASE = "https://aausmartlab.org/Materials/"


def _make_properties_for_slot(slot_cfg: dict) -> dict:
    """Build a Properties dict from slot config, covering all property sections."""
    customer = slot_cfg.get("properties") or {}

    mat = {}
    for prop_key, id_short, sem_fragment in (
        ("material", "Material",  "Material"),
        ("color",    "Color",     "Color"),
        ("finish",   "Finish",    "SurfaceFinish"),
    ):
        val = customer.get(prop_key)
        if val:
            # Material carries a resolvable identity: emit the canonical material
            # IRI (…/Materials/<name>) so it matches a capability's AllowedMaterials
            # by full IRI rather than a bare-name heuristic. Already-qualified
            # values (full URLs) pass through unchanged.
            if id_short == "Material" and isinstance(val, str) and not val.startswith("http"):
                val = f"{_MATERIALS_BASE}{val}"
            mat[id_short] = {
                "semanticId": f"https://aausmartlab.org/Semantics/{sem_fragment}",
                "value": val,
            }

    dims = {}
    for prop_key, sem_key in (
        ("length", "Length"),
        ("width",  "Width"),
        ("height", "Height"),
        ("weight", "Weight"),
    ):
        val = customer.get(prop_key)
        if val is not None:
            # Identity semanticId per dimension (the unit lives as a qualifier on
            # the component side); previously all three shared …/Semantics/mm.
            dims[sem_key] = {
                "semanticId": f"https://aausmartlab.org/Semantics/Parameter/{sem_key}",
                "value": val,
            }

    elec = {}
    for prop_key, id_short, sem_fragment in (
        ("voltageRating", "VoltageRating", "VoltageRating"),
        ("currentRating", "CurrentRating", "CurrentRating"),
        ("type",          "Type",          "ElectricalType"),
    ):
        val = customer.get(prop_key)
        if val is not None:
            elec[id_short] = {
                "semanticId": f"https://aausmartlab.org/Semantics/{sem_fragment}",
                "value": _parse_electrical_value(val),
            }

    result: dict = {}
    if mat:
        result["MaterialProperties"] = mat
    if dims:
        result["PhysicalDimensions"] = dims
    if elec:
        result["ElectricalProperties"] = elec
    return result


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

    # Number of fuses ordered — drives expansion of the fuse sub-assembly so the
    # workorder traverses one assemble step per physical fuse. Must match the
    # count used by shell_uploader so the generated operation names line up with
    # what was uploaded to BaSyx.
    fuse_count = preset_loader.fuse_count(configuration)

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
                log.debug("slot match (typeId) for %s -> slot=%s", asset_name, slot.get("slot"))
                return slot
        # 2. Try category/slot-label match, normalising spaces→underscores
        iri_lower = ref_iri.lower()
        for slot in configuration:
            for field in ("category", "slot"):
                raw = (slot.get(field) or "").lower().replace(" ", "_")
                if raw and raw in iri_lower:
                    log.debug("slot match (%s) for %s -> slot=%s", field, asset_name, slot.get("slot"))
                    return slot
        log.warning("no slot match for %s — properties will be empty", asset_name)
        return {}

    def _component_type_iri(component_ref_iri: str) -> str:
        """Strip the last path segment to get the category type IRI.

        e.g. …/Component/BottomCover/BottomCoverABSBlack → …/Component/BottomCover
        """
        return component_ref_iri.rstrip("/").rsplit("/", 1)[0]

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
            ref_iri = entry.get("ComponentTypeReference", "")
            if not ref_iri:
                continue

            if _is_sub_assembly_iri(ref_iri):
                # Recurse into sub-assembly preset
                sub_asset_name = _asset_name_from_iri(ref_iri)
                sub_preset_name = ASSET_NAME_TO_PRESET.get(sub_asset_name)
                if not sub_preset_name:
                    log.warning("No preset mapping for sub-assembly IRI: %s", ref_iri)
                    continue
                sub_preset = preset_loader.expand_fuse_assembly(
                    _load_preset(sub_preset_name), fuse_count
                )
                sub_output_ids = resolve(sub_preset)
                input_ids.extend(sub_output_ids)
            else:
                # Raw component — resolve the actual ordered component IRI first,
                # then use it as the ingredient name so "BottomCoverPETGGray"
                # appears instead of the generic BOM family name "BottomCover3DP".
                slot_cfg = _find_slot_config(ref_iri)
                type_iri = (slot_cfg.get("aasTypeIri") if slot_cfg else None) or ref_iri
                component_ref_iri = _type_iri_from_full(type_iri)
                category_iri = _component_type_iri(component_ref_iri)

                # Expand this BOM entry N times according to the YAML BOM Quantity field.
                # Each explicitly-split entry (Quantity: 1) produces exactly one ingredient,
                # so two Fuse entries → two ingredients without further MES-quantity expansion.
                ordered_qty = int(entry.get("Quantity", 1))
                type_props = _get_type_shell_properties(component_ref_iri, basyx_url) if basyx_url else {}
                order_props = _make_properties_for_slot(slot_cfg) if slot_cfg else {}
                merged: dict = {}
                for section in set(type_props) | set(order_props):
                    merged[section] = {**type_props.get(section, {}), **order_props.get(section, {})}

                for _ in range(ordered_qty):
                    ing_id = _make_ing_id(_asset_name_from_iri(component_ref_iri))
                    ingredients[ing_id] = {
                        "ComponentReference": "",
                        "ComponentTypeReference": category_iri,
                    }
                    properties[ing_id] = merged
                    log.info(
                        "ingredient %s — %s",
                        ing_id,
                        {s: list(v.keys()) for s, v in merged.items()},
                    )
                    input_ids.append(ing_id)

        # ── Step 2: process BOP steps ───────────────────────────────────────
        iri_base = _type_iri_base_from_shell_template(shell_type)
        type_iri_template = iri_base.replace("{asset_type}", asset_type)
        level_iri_template = f"{type_iri_template}/{asset_name}"

        instance_iri = shell_iris.get(asset_name, level_iri_template)

        output_id = _make_ing_id(asset_name)
        ingredients[output_id] = {
            "ComponentReference": instance_iri,
            "ComponentTypeReference": type_iri_template,
        }
        properties[output_id] = {}

        has_assemble_step = False
        assemble_count = [0]
        remaining_inputs = list(input_ids)  # tracks inputs not yet consumed by an assemble step

        for step in bop_steps:
            process_type = step.get("ProcessType", "")
            operation = step.get("Operation", "")

            # Fetch RequiredComponents from the AAS (model references → resolved IRIs)
            required_comp_iris = (
                _fetch_required_component_iris(instance_iri, operation, basyx_url)
                if basyx_url else []
            )

            if process_type == "Assemble":
                has_assemble_step = True
                assemble_count[0] += 1

                # Record all initial inputs in Assemblies once (first assemble step)
                if assemble_count[0] == 1:
                    assemblies[output_id] = {"Ingredients": list(input_ids)}

                # Find which remaining inputs this step explicitly requires
                step_inputs = _find_all_step_inputs(remaining_inputs, required_comp_iris, ingredients)
                if not step_inputs:
                    step_inputs = list(remaining_inputs)
                for sid in step_inputs:
                    if sid in remaining_inputs:
                        remaining_inputs.remove(sid)

                # Subsequent steps prepend the previous output (partial assembly) as first input
                if assemble_count[0] > 1:
                    step_inputs = [output_id] + step_inputs

                step_id = _next_step()
                cap_ref = "https://aausmartlab.org/Submodels/Capability/Assemble"
                step_name = f"ProcessStep{_step_counter[0]}"
                deps = [_last_step_id[0]] if _last_step_id[0] else []
                params, req_cap_iri = _fetch_required_cap_params(instance_iri, operation, basyx_url) if basyx_url else ({}, None)
                if output_id not in process_steps:
                    process_steps[output_id] = {}
                process_steps[output_id][step_name] = {
                    "CapabilityReference": cap_ref,
                    "RequiredCapabilitySubmodelReference": req_cap_iri,
                    "ProcessStepId": step_id,
                    "Dependencies": deps,
                    "Parameters": params,
                    "ProcessTransformations": {
                        "InputTypes": list(step_inputs),
                        "OutputTypes": [output_id],
                    },
                }
                _last_step_id[0] = step_id

            else:
                # Non-assemble step (e.g. Drilling) — operates in-place on a raw ingredient.
                # Step is stored under the target ingredient's key (not the output assembly).
                target_id = _find_target_ingredient(input_ids, required_comp_iris, ingredients)
                if target_id is None and input_ids:
                    target_id = input_ids[0]

                if target_id:
                    step_id = _next_step()
                    cap_name = process_type or operation
                    cap_ref = f"https://aausmartlab.org/Submodels/Capability/{cap_name}"
                    params, req_cap_iri = _fetch_required_cap_params(instance_iri, cap_name, basyx_url) if basyx_url else ({}, None)

                    step_name = f"ProcessStep{_step_counter[0]}"
                    deps = [_last_step_id[0]] if _last_step_id[0] else []
                    if target_id not in process_steps:
                        process_steps[target_id] = {}
                    process_steps[target_id][step_name] = {
                        "CapabilityReference": cap_ref,
                        "RequiredCapabilitySubmodelReference": req_cap_iri,
                        "ProcessStepId": step_id,
                        "Dependencies": deps,
                        "Parameters": params,
                        "ProcessTransformations": {
                            "InputTypes": [target_id],
                            "OutputTypes": [target_id],
                        },
                    }
                    _last_step_id[0] = step_id

        # Emit extra assemble steps for any quantity-expanded ingredients not
        # consumed by the BOP step templates (e.g. quantity=2 with one step template).
        while remaining_inputs and has_assemble_step:
            assemble_count[0] += 1
            extra_inputs = [output_id] + list(remaining_inputs)
            remaining_inputs.clear()
            step_id = _next_step()
            step_name = f"ProcessStep{_step_counter[0]}"
            deps = [_last_step_id[0]] if _last_step_id[0] else []
            if output_id not in process_steps:
                process_steps[output_id] = {}
            process_steps[output_id][step_name] = {
                "CapabilityReference": "https://aausmartlab.org/Submodels/Capability/Assemble",
                "ProcessStepId": step_id,
                "Dependencies": deps,
                "Parameters": {},
                "ProcessTransformations": {
                    "InputTypes": extra_inputs,
                    "OutputTypes": [output_id],
                },
            }
            _last_step_id[0] = step_id

        # If no assemble step produced the output, return the raw inputs instead
        if not has_assemble_step:
            del ingredients[output_id]
            del properties[output_id]
            process_steps.pop(output_id, None)
            return list(input_ids)

        return [output_id]

    def _find_target_ingredient(
        input_ids: list[str],
        required_comp_iris: list[str],
        ingredients: dict[str, dict],
    ) -> str | None:
        """Return the first ingredient whose ComponentTypeReference matches a required IRI."""
        for ing_id in input_ids:
            ing = ingredients[ing_id]
            ref = ing.get("ComponentTypeReference") or ing.get("ComponentReference", "")
            for iri in required_comp_iris:
                if ref == iri or ref.startswith(iri) or iri.startswith(ref):
                    return ing_id
        return None

    def _find_all_step_inputs(
        input_ids: list[str],
        required_comp_iris: list[str],
        ingredients: dict[str, dict],
    ) -> list[str]:
        """Return ingredient IDs matching required_comp_iris, one match per IRI."""
        if not required_comp_iris:
            return []
        matched: list[str] = []
        unmatched = list(required_comp_iris)
        for ing_id in input_ids:
            if not unmatched:
                break
            ing = ingredients.get(ing_id, {})
            ref = ing.get("ComponentTypeReference") or ing.get("ComponentReference", "")
            for iri in list(unmatched):
                if ref == iri or ref.startswith(iri) or iri.startswith(ref):
                    matched.append(ing_id)
                    unmatched.remove(iri)
                    break
        return matched

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
