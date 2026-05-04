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
    Collect all offered capability semanticIds from resource shells that belong
    to a given line.

    Heuristic: shells whose idShort contains the line_id prefix or whose IRI
    matches the line_id pattern are considered resources of that line.
    A more robust approach would use the LineConfiguration submodel.
    """
    all_shells = basyx_client.list_shells(basyx_url)
    offered = set()

    for shell in all_shells:
        shell_id = shell.get("id", "")
        id_short = shell.get("idShort", "")

        # Only look at resource shells associated with this line
        if line_id not in shell_id and line_id not in id_short:
            continue

        # Fetch submodels for this shell
        submodel_refs = basyx_client.get_submodel_refs_for_shell(shell_id, basyx_url)
        for sm_iri in submodel_refs:
            if "Capability" not in sm_iri and "Offered" not in sm_iri:
                continue
            sm = basyx_client.fetch_submodel(sm_iri, basyx_url)
            if not sm:
                continue
            # Collect semanticId values from capability elements
            _collect_semantic_ids(sm.get("submodelElements", []), offered)

    return offered


def _collect_semantic_ids(elements: list, result: set) -> None:
    for elem in elements:
        sem = elem.get("semanticId")
        if sem:
            keys = sem.get("keys", [])
            for k in keys:
                val = k.get("value", "")
                if val:
                    result.add(val)
        children = elem.get("value", [])
        if isinstance(children, list):
            _collect_semantic_ids(children, result)


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
