"""
line_selector.py — Find a production line that can actually run a WorkOrder.

Selection is two-level:

1. **Capability type** — every ProcessStep references a capability type
   (``CapabilityReference``, an IRI). A line must offer all required types.
2. **Parameters** — for each step, the line's offered capability of that type
   must also accept the step's *parameters*: value ranges, supported components,
   allowed materials, and the input→output transformation. This is delegated to
   ``capability_param_matcher`` (a dict-based mirror of the Line Controller's
   matcher), so a line whose drill exists but can't reach the requested diameter
   is rejected here instead of failing later in the Line Controller.

Matching is **permissive**: when an offered capability declares no constraint
(or its detail submodel can't be read) the step passes on type alone, matching
prior behaviour. Pass ``strict=True`` to turn permissive fallbacks into failures
(used by tests). Every decision is logged with the per-dimension match path so a
silent permissive degradation is visible.

Required capabilities and parameters are taken directly from the WorkOrder's
ProcessSteps; transformation inputs/outputs (ingredient IDs) are resolved to
component *type* IRIs via the WorkOrder's ingredient map before comparison.
Raises ValueError if no lines are registered or none can run the order.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "InformationModels"))
from MessageStructure import WorkOrderMessage

import basyx_client
import capability_param_matcher as cpm

log = logging.getLogger(__name__)

_PRODUCTION_LINE_IRI_PREFIX = "https://aausmartlab.org/Shells/Resources/ProductionLine/"
_CAPABILITY_IRI_PREFIX = "https://aausmartlab.org/Submodels/Capability/"


def _discover_lines(basyx_url: str) -> list[dict]:
    """Query BaSyx for all shells whose IRI starts with the production line prefix."""
    lines = []
    for shell in basyx_client.list_shells(basyx_url):
        iri = shell.get("id", "")
        if iri.startswith(_PRODUCTION_LINE_IRI_PREFIX):
            lines.append(shell)
    if lines:
        log.info("Discovered production lines in BaSyx: %s", [s.get("idShort") for s in lines])
    else:
        log.warning("No production line shells found in BaSyx (prefix=%s)", _PRODUCTION_LINE_IRI_PREFIX)
    return lines


def _submodel_iris_from_shell(shell: dict) -> list[str]:
    """Extract submodel IRIs referenced in a shell dict (no extra fetch needed)."""
    iris = []
    for ref in shell.get("submodels", []):
        keys = ref.get("keys", [])
        if keys:
            iris.append(keys[-1].get("value", ""))
    return iris


# ─────────────────────────── required side ────────────────────────────────

def _resolve_types(ids: list[str], ingredients: dict) -> list[str]:
    """Map ingredient IDs to their component *type* IRIs via the ingredient map.

    Transformation Input/OutputTypes on a step are ingredient IDs (e.g.
    ``BottomCover_0``); the offered side compares component type IRIs. An
    unresolvable id is kept as-is so the mismatch is visible rather than hidden.
    """
    out = []
    for i in ids:
        ctype = (ingredients.get(i) or {}).get("ComponentTypeReference")
        out.append(ctype if ctype else i)
    return out


def _material_for(properties: dict, ing_id: str):
    """Best-effort material for a step's ingredient, or None (permissive)."""
    mat = ((properties.get(ing_id) or {}).get("MaterialProperties") or {}).get("Material")
    if isinstance(mat, dict):
        return mat.get("value")
    return mat or None


def _extract_required_steps(workorder: WorkOrderMessage) -> list[dict]:
    """Build a per-step match input, resolved against the WorkOrder ingredient map.

    Each entry: ``capability_type`` (IRI), ``step_label``, ``Parameters`` tree,
    ``ComponentTypes`` (resolved type IRIs), ``Material``, and resolved
    ``InputTypes``/``OutputTypes``.
    """
    ingredients = workorder.ingredients or {}
    properties = workorder.properties or {}
    steps: list[dict] = []
    for ing_id, step_dict in workorder.process_steps.items():
        material = _material_for(properties, ing_id)
        for step_name, step_data in step_dict.items():
            cap = step_data.get("CapabilityReference")
            if not cap:
                continue
            pt = step_data.get("ProcessTransformations") or {}
            input_types = _resolve_types(pt.get("InputTypes") or [], ingredients)
            output_types = _resolve_types(pt.get("OutputTypes") or [], ingredients)
            steps.append({
                "capability_type": cap,
                "step_label": f"{ing_id}/{step_name}",
                "Parameters": step_data.get("Parameters") or {},
                "ComponentTypes": sorted(set(input_types) | set(output_types)),
                "Material": material,
                "InputTypes": input_types,
                "OutputTypes": output_types,
            })
    return steps


# ─────────────────────────── offered side ─────────────────────────────────

def _get_offered_entries(shell: dict, basyx_url: str) -> list[dict]:
    """Read the line's ServiceOffered submodel into a list of offered entries.

    Each entry: ``capability_type`` (IRI) and ``submodel_iri`` (the detail
    OfferedCapability submodel, or None). The detail submodel is fetched lazily
    by the matcher path so a line that fails on type never fetches it.
    """
    sm_iris = _submodel_iris_from_shell(shell)
    service_iri = next((iri for iri in sm_iris if "/ServiceOffered" in iri), None)
    if not service_iri:
        log.debug("No ServiceOffered submodel found for line %s", shell.get("idShort"))
        return []

    sm = basyx_client.fetch_submodel(service_iri, basyx_url)
    if not sm:
        log.warning("ServiceOffered submodel not found in BaSyx: %s", service_iri)
        return []

    cap_offered = basyx_client.find_element_by_idshort(
        sm.get("submodelElements", []), "OfferedCapabilities"
    )
    if not cap_offered or not isinstance(cap_offered.get("value"), list):
        return []

    entries = []
    for entry in cap_offered["value"]:
        children = entry.get("value") if isinstance(entry.get("value"), list) else []
        cap_type_elem = basyx_client.find_element_by_idshort(children, "CapabilityType")
        cap_type = cap_type_elem.get("value") if cap_type_elem else None
        if not cap_type:
            continue
        # The link is named CapabilitySubmodelReference (matching the resource
        # Skills submodel). Fall back to the legacy CapabilityReference name so a
        # ServiceOffered instance not yet regenerated still resolves.
        ref_elem = (
            basyx_client.find_element_by_idshort(children, "CapabilitySubmodelReference")
            or basyx_client.find_element_by_idshort(children, "CapabilityReference")
        )
        submodel_iri = None
        if ref_elem:
            keys = (ref_elem.get("value") or {}).get("keys", [])
            if keys:
                submodel_iri = keys[-1].get("value")
        entries.append({
            "capability_type": f"{_CAPABILITY_IRI_PREFIX}{cap_type}",
            "submodel_iri": submodel_iri,
        })
    return entries


def _fetch_cached(iri: str, basyx_url: str, cache: dict) -> dict | None:
    """Fetch a detail submodel once per line (shared refs are common)."""
    if iri not in cache:
        cache[iri] = basyx_client.fetch_submodel(iri, basyx_url)
    return cache[iri]


def _step_satisfiable(
    step: dict,
    offered_entries: list[dict],
    basyx_url: str,
    cache: dict,
    strict: bool,
    trace: list[str],
) -> bool:
    """True if any offered entry of the step's capability type accepts its parameters."""
    matching = [e for e in offered_entries if e["capability_type"] == step["capability_type"]]
    if not matching:
        trace.append(f"{step['step_label']}: no offered capability of type {step['capability_type']}")
        return False
    for e in matching:
        submodel = _fetch_cached(e["submodel_iri"], basyx_url, cache) if e["submodel_iri"] else None
        result = cpm.match_step(step, submodel, strict=strict)
        log.info(
            "  step %s vs %s -> ok=%s [%s] %s",
            step["step_label"], e["submodel_iri"], result.ok, result.summary(), result.reason,
        )
        if result.ok:
            return True
        trace.append(f"{step['step_label']} via {e['submodel_iri']}: {result.reason}")
    return False


def select_line(
    workorder: WorkOrderMessage,
    basyx_url: str = basyx_client.BASYX_URL,
    strict: bool = False,
) -> str:
    """Return the idShort of the first production line that can run the WorkOrder.

    A line qualifies when every ProcessStep is satisfiable by at least one offered
    capability of the matching type whose parameters/components/materials/
    transformation accept the step (permissive on unconstrained dimensions unless
    ``strict``). Raises ValueError if no lines are registered or none qualify.
    """
    required_steps = _extract_required_steps(workorder)
    log.info(
        "Required steps: %s",
        [f"{s['step_label']}:{s['capability_type']}" for s in required_steps],
    )

    lines = _discover_lines(basyx_url)
    if not lines:
        raise ValueError(
            "No production line found that can run the work order — no production "
            "line shells are registered in BaSyx."
        )

    failures: list[str] = []
    for shell in lines:
        line_id = shell.get("idShort") or shell["id"][len(_PRODUCTION_LINE_IRI_PREFIX):]
        offered_entries = _get_offered_entries(shell, basyx_url)
        log.info("Line %s offers types: %s", line_id, sorted({e["capability_type"] for e in offered_entries}))
        cache: dict = {}
        trace: list[str] = []
        if all(_step_satisfiable(s, offered_entries, basyx_url, cache, strict, trace)
               for s in required_steps):
            log.info("Selected line: %s", line_id)
            return line_id
        failures.append(f"line {line_id}: " + ("; ".join(trace) if trace else "offers nothing"))

    raise ValueError(
        "No production line can run this work order. Reasons per line: "
        + " | ".join(failures)
    )
