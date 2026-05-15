"""
line_selector.py — Find the first production line that covers all required
capabilities needed by the WorkOrder.

Required capabilities are extracted directly from the WorkOrder's ProcessSteps
(all CapabilityReferences), so we don't need to query the ServiceRequired
submodel in BaSyx.

Line matching: discover all production line shells from BaSyx by IRI prefix,
collect their offered capabilities, return first line that covers all required.
Raises ValueError if no lines are registered or none match the required capabilities.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "InformationModels"))
from MessageStructure import WorkOrderMessage

import basyx_client

log = logging.getLogger(__name__)

_PRODUCTION_LINE_IRI_PREFIX = "https://aausmartlab.org/Shells/ProductionLine/"


def _discover_lines(basyx_url: str) -> list[dict]:
    """
    Query BaSyx for all shells and return the full shell dicts for every shell
    whose IRI starts with the production line prefix.
    """
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


def _extract_required_capabilities(workorder: WorkOrderMessage) -> set[str]:
    """Return the set of unique CapabilityReferences from the WorkOrder ProcessSteps."""
    caps = set()
    for step_dict in workorder.process_steps.values():
        for step_data in step_dict.values():
            cap = step_data.get("CapabilityReference")
            if cap:
                caps.add(cap)
    return caps


def _submodel_iris_from_shell(shell: dict) -> list[str]:
    """Extract submodel IRIs referenced in a shell dict (no extra fetch needed)."""
    iris = []
    for ref in shell.get("submodels", []):
        keys = ref.get("keys", [])
        if keys:
            iris.append(keys[-1].get("value", ""))
    return iris


def _get_offered_capabilities(shell: dict, basyx_url: str) -> set[str]:
    """
    Read the ServiceOffered submodel from an already-fetched ProductionLine shell
    dict and return the set of capability IRIs it advertises.
    """
    sm_iris = _submodel_iris_from_shell(shell)
    service_iri = next((iri for iri in sm_iris if "/ServiceOffered" in iri), None)
    if not service_iri:
        log.debug("No ServiceOffered submodel found for line %s", shell.get("idShort"))
        return set()

    sm = basyx_client.fetch_submodel(service_iri, basyx_url)
    if not sm:
        log.warning("ServiceOffered submodel not found in BaSyx: %s", service_iri)
        return set()

    offered = set()
    cap_offered = basyx_client.find_element_by_idshort(
        sm.get("submodelElements", []), "OfferedCapabilities"
    )
    if not cap_offered or not isinstance(cap_offered.get("value"), list):
        return offered

    for entry in cap_offered["value"]:
        children = entry.get("value") if isinstance(entry.get("value"), list) else []
        cap_type_elem = basyx_client.find_element_by_idshort(children, "CapabilityType")
        cap_type = cap_type_elem.get("value") if cap_type_elem else None
        if cap_type:
            offered.add(f"https://aausmartlab.org/Submodels/Capability/{cap_type}")

    return offered


def select_line(
    workorder: WorkOrderMessage,
    basyx_url: str = basyx_client.BASYX_URL,
) -> str:
    """
    Discover all production lines from BaSyx and return the idShort of the first
    whose ServiceOffered covers all capabilities required by the WorkOrder.

    Raises ValueError if no production lines are registered in BaSyx or if none
    can satisfy the required capabilities.
    """
    required = _extract_required_capabilities(workorder)
    log.info("Required capabilities: %s", required)

    lines = _discover_lines(basyx_url)
    if not lines:
        raise ValueError(
            "No production line found that matches the required capabilities: "
            f"{required}. No production line shells are registered in BaSyx."
        )

    for shell in lines:
        line_id = shell.get("idShort") or shell["id"][len(_PRODUCTION_LINE_IRI_PREFIX):]
        offered = _get_offered_capabilities(shell, basyx_url)
        log.info("Line %s offers: %s", line_id, offered)
        if required.issubset(offered):
            log.info("Selected line: %s", line_id)
            return line_id

    raise ValueError(
        f"No production line found that matches the required capabilities: {required}. "
        f"Available lines: {[s.get('idShort') for s in lines]}."
    )
