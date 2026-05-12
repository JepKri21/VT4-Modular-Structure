"""
line_selector.py — Find the first production line that covers all required
capabilities needed by the WorkOrder.

Required capabilities are extracted directly from the WorkOrder's ProcessSteps
(all CapabilityReferences), so we don't need to query the ServiceRequired
submodel in BaSyx.

Line matching: query BaSyx for all resource shells, collect their offered
capability semanticIds, group them by line_id, return first line that covers all.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "InformationModels"))
from MessageStructure import WorkOrderMessage

import basyx_client

log = logging.getLogger(__name__)

# Known line IDs (can be extended or auto-discovered from BaSyx)
KNOWN_LINE_IDS = ["ProductionLine1"]


def _extract_required_capabilities(workorder: WorkOrderMessage) -> set[str]:
    """Return the set of unique CapabilityReferences from the WorkOrder ProcessSteps."""
    caps = set()
    for step_dict in workorder.process_steps.values():
        for step_data in step_dict.values():
            cap = step_data.get("CapabilityReference")
            if cap:
                caps.add(cap)
    return caps


def _get_offered_capabilities_for_line(line_id: str, basyx_url: str) -> set[str]:
    """
    Read the ServiceOffered submodel from the ProductionLine shell and return
    the set of capability IRIs it advertises.

    The ProductionLine shell is pre-created externally; the MES only reads it.
    If the shell or submodel is absent, returns an empty set and the caller's
    fallback warning fires — same observable behaviour as before.
    """
    line_iri = f"https://aausmartlab.org/Shells/ProductionLine/{line_id}"
    sm_iris = basyx_client.get_submodel_refs_for_shell(line_iri, basyx_url)
    service_iri = next((iri for iri in sm_iris if "/ServiceOffered" in iri), None)
    if not service_iri:
        log.debug(
            "No ServiceOffered submodel found for line %s — is the shell in BaSyx?", line_id
        )
        return set()

    sm = basyx_client.fetch_submodel(service_iri, basyx_url)
    if not sm:
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
    Return the first line_id whose resources cover all capabilities required
    by the WorkOrder.

    Falls back to KNOWN_LINE_IDS[0] if no match is found (allows testing without
    BaSyx being fully populated with line shells).
    """
    required = _extract_required_capabilities(workorder)
    log.info("Required capabilities: %s", required)

    for line_id in KNOWN_LINE_IDS:
        offered = _get_offered_capabilities_for_line(line_id, basyx_url)
        log.info("Line %s offers: %s", line_id, offered)
        if required.issubset(offered):
            log.info("Selected line: %s", line_id)
            return line_id

    # Fallback: return first known line and log a warning
    fallback = KNOWN_LINE_IDS[0] if KNOWN_LINE_IDS else "ProductionLine1"
    log.warning(
        "No line fully covers required capabilities %s — falling back to %s",
        required,
        fallback,
    )
    return fallback
