"""Writes traceability and process-history data back to component AAS shells on BaSyx.

Two responsibilities:
- write_traceability(): attaches the specific instance IRIs consumed by an
  order to the final-product shell (one call per order at finalisation).
- write_process_record(): appends a single ProcessRecord to a component shell's
  ProcessTracking submodel (one call per BoP step per output component).

Both functions are best-effort: they log failures and return False instead of
raising, so the Line Controller's critical execution path is never blocked by
an AAS write failure.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime

import requests


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


def _put_or_post_property(parent_path: str, id_short: str, value: str, headers: dict) -> bool:
    """Update an existing Property via PUT, or create it via POST to the parent if it doesn't exist.

    Optional fields (e.g. CompletionTime) are absent from the initial record,
    so a plain PUT would return 404. This helper creates them on first write.
    """
    body = json.dumps({"modelType": "Property", "idShort": id_short, "valueType": "xs:string", "value": value})
    encoded = body.encode("utf-8")
    try:
        resp = requests.put(f"{parent_path}.{id_short}", headers=headers, data=encoded)
        if resp.status_code in (200, 201, 204):
            return True
        if resp.status_code == 404:
            resp = requests.post(parent_path, headers=headers, data=encoded)
            if resp.status_code in (200, 201):
                return True
            print(f"[aas] POST {id_short} failed: {resp.status_code} {resp.text[:200]}")
            return False
        print(f"[aas] PUT {id_short} failed: {resp.status_code} {resp.text[:200]}")
        return False
    except requests.RequestException as e:
        print(f"[aas] HTTP error updating {id_short}: {e}")
        return False


def write_traceability(
    aas_server_base: str,
    product_shell_iri: str,
    used_components: dict[str, str],
) -> bool:
    """Attach the specific instance IRIs consumed by an order to the product shell.

    Args:
        aas_server_base: e.g. "http://localhost:8081".
        product_shell_iri: the work order's `ProductReference` resolved to an
            actual shell IRI on the server.
        used_components: ingredient_name -> instance IRI.
            e.g. {"Ingredient_1": ".../Bottom_Cover/Bottom_Cover-BC003"}

    Returns:
        True if the server accepted the write, False if it didn't exist or
        the call failed. Never raises — traceability is auxiliary, not on the
        critical path.
    """
    if not used_components:
        print("[trace] no components recorded; nothing to write")
        return False

    # Build a Traceability submodel under the product shell.
    submodel_id = f"{product_shell_iri.rstrip('/')}/Traceability"
    submodel = {
        "modelType": "Submodel",
        "kind": "Instance",
        "id": submodel_id,
        "idShort": "Traceability",
        "description": [{"language": "en", "text": "Specific component instances consumed by the order"}],
        "submodelElements": [
            {
                "modelType": "SubmodelElementCollection",
                "idShort": "UsedComponents",
                "value": [
                    {
                        "modelType": "Property",
                        "idShort": ingredient,
                        "valueType": "xs:string",
                        "value": instance_iri,
                    }
                    for ingredient, instance_iri in used_components.items()
                ],
            },
            {
                "modelType": "Property",
                "idShort": "RecordedAt",
                "valueType": "xs:dateTime",
                "value": datetime.now().isoformat(),
            },
        ],
    }

    server = aas_server_base.rstrip("/")
    payload = json.dumps(submodel)
    headers = {"Content-Type": "application/json"}

    try:
        # Try create first.
        resp = requests.post(f"{server}/submodels", headers=headers, data=payload.encode("utf-8"))
        if resp.status_code in (200, 201):
            print(f"[trace] wrote Traceability submodel for {product_shell_iri}")
            return True
        if resp.status_code == 409:
            # Already exists — update via PUT.
            put = requests.put(
                f"{server}/submodels/{_b64(submodel_id)}",
                headers=headers,
                data=payload.encode("utf-8"),
            )
            if put.status_code in (200, 201, 204):
                print(f"[trace] updated Traceability submodel for {product_shell_iri}")
                return True
            print(
                f"[trace] PUT failed for {submodel_id}: "
                f"{put.status_code} {put.text[:200]}"
            )
            return False
        print(
            f"[trace] POST failed for {submodel_id}: "
            f"{resp.status_code} {resp.text[:200]}"
        )
        return False
    except requests.RequestException as e:
        print(f"[trace] HTTP error writing traceability: {e}")
        return False


# ── BillOfProcesses status ───────────────────────────────────────────────────

def write_bop_step_started(
    aas_server_base: str,
    product_shell_iri: str,
    step_id_short: str,
    executed_by: str,
    start_time: str | None = None,
) -> str | None:
    """Create an InProgress StepRecord in BillOfProcesses.ProcessTracking on the product shell.

    Args:
        aas_server_base: e.g. "http://localhost:8081".
        product_shell_iri: IRI of the final product or sub-assembly shell.
        step_id_short: idShort of the ProcessStep in BillOfProcesses.ProcessSteps (e.g. "Drilling_0").
        executed_by: resource_id of the station executing the step.
        start_time: ISO 8601 timestamp when the step went InProgress.

    Returns:
        The idShort used for the created record (same as step_id_short) so
        write_bop_step_completed() can find it, or None on failure. Never raises.
    """
    server = aas_server_base.rstrip("/")
    submodel_id = f"{product_shell_iri.rstrip('/')}/BillOfProcesses"
    headers = {"Content-Type": "application/json"}

    elements: list[dict] = [
        {"modelType": "Property", "idShort": "StepRef", "valueType": "xs:string", "value": step_id_short},
        {"modelType": "Property", "idShort": "StepStatus", "valueType": "xs:string", "value": "InProgress"},
        {"modelType": "Property", "idShort": "ExecutedBy", "valueType": "xs:string", "value": executed_by},
    ]
    if start_time:
        elements.append({"modelType": "Property", "idShort": "StartTime", "valueType": "xs:string", "value": start_time})

    record = {"modelType": "SubmodelElementCollection", "idShort": step_id_short, "value": elements}

    try:
        resp = requests.post(
            f"{server}/submodels/{_b64(submodel_id)}/submodel-elements/ProcessTracking",
            headers=headers,
            data=json.dumps(record).encode("utf-8"),
        )
        if resp.status_code in (200, 201):
            print(f"[bop] {step_id_short} -> InProgress on {product_shell_iri}")
            return step_id_short
        print(f"[bop] POST StepRecord failed: {resp.status_code} {resp.text[:200]}")
        return None
    except requests.RequestException as e:
        print(f"[bop] HTTP error writing StepRecord: {e}")
        return None


def write_bop_step_completed(
    aas_server_base: str,
    product_shell_iri: str,
    record_id_short: str,
    completion_time: str | None = None,
    status: str = "Completed",
) -> bool:
    """Patch StepStatus and CompletionTime on an existing BoP StepRecord.

    Args:
        aas_server_base: e.g. "http://localhost:8081".
        product_shell_iri: IRI of the product shell that owns the BillOfProcesses.
        record_id_short: idShort returned by write_bop_step_started().
        completion_time: ISO 8601 timestamp when the step completed.
        status: "Completed", "Failed", etc.

    Returns:
        True if both fields were patched, False on any error. Never raises.
    """
    server = aas_server_base.rstrip("/")
    submodel_id = f"{product_shell_iri.rstrip('/')}/BillOfProcesses"
    base = f"{server}/submodels/{_b64(submodel_id)}/submodel-elements/ProcessTracking.{record_id_short}"
    headers = {"Content-Type": "application/json"}

    ok = True
    for id_short, value in [("StepStatus", status), ("CompletionTime", completion_time)]:
        if value is None:
            continue
        if not _put_or_post_property(base, id_short, value, headers):
            ok = False

    if ok:
        print(f"[bop] {record_id_short} -> {status} on {product_shell_iri}")
    return ok


# ── ProcessTracking ──────────────────────────────────────────────────────────

_PROCESS_TRACKING_TEMPLATE_ID = "https://aausmartlab.org/Submodels/Templates/ProcessTracking"


def fetch_process_tracking_template(aas_server_base: str) -> bool:
    """Verify the ProcessTracking template exists on BaSyx. Call once at startup.

    Args:
        aas_server_base: e.g. "http://localhost:8081".

    Returns:
        True if the template is present, False otherwise.
    """
    server = aas_server_base.rstrip("/")
    try:
        resp = requests.get(f"{server}/submodels/{_b64(_PROCESS_TRACKING_TEMPLATE_ID)}")
        if resp.status_code == 200:
            print("[process] ProcessTracking template found on BaSyx server")
            return True
        print(f"[process] ProcessTracking template not found: {resp.status_code} — run upload_templates.py first")
        return False
    except requests.RequestException as e:
        print(f"[process] HTTP error fetching ProcessTracking template: {e}")
        return False


def write_process_started(
    aas_server_base: str,
    component_shell_iri: str,
    process_type: str,
    performed_by: str,
    capability_reference_iri: str | None = None,
    skill_reference_iri: str | None = None,
    skill_name: str | None = None,
    start_time: str | None = None,
) -> str | None:
    """Append an InProgress ProcessRecord to a component shell's ProcessTracking submodel.

    Creates the ProcessTracking submodel and registers it on the shell if this is
    the first process recorded for this component.

    Args:
        aas_server_base: e.g. "http://localhost:8081".
        component_shell_iri: IRI of the component or assembly shell to write to.
        process_type: capability type name, e.g. "Assemble", "Drilling".
        performed_by: resource_id of the station that will perform the step.
        capability_reference_iri: IRI of the required capability submodel on the product AAS
            (e.g. Assemble_TopCoverCapabilityRequired). Points to where the actual parameters live.
        skill_reference_iri: IRI of the Skills submodel on the resource that performed the step.
        start_time: ISO 8601 timestamp when the step went IN_PROGRESS.

    Returns:
        The idShort of the created record (e.g. "Assemble_0") so write_process_completed()
        can find it later, or None on failure. Never raises.
    """
    server = aas_server_base.rstrip("/")
    submodel_id = f"{component_shell_iri.rstrip('/')}/ProcessTracking"
    submodel_id_b64 = _b64(submodel_id)
    headers = {"Content-Type": "application/json"}

    index = _get_process_history_length(server, submodel_id_b64)
    if index is None:
        if not _create_process_tracking_submodel(server, component_shell_iri, submodel_id, headers):
            return None
        index = 0

    record_id_short = f"{process_type}_{index}"
    record = _build_process_record(
        record_id_short=record_id_short,
        process_type=process_type,
        performed_by=performed_by,
        capability_reference_iri=capability_reference_iri,
        skill_reference_iri=skill_reference_iri,
        skill_name=skill_name,
        start_time=start_time,
        completion_time=None,
        status="InProgress",
    )

    try:
        resp = requests.post(
            f"{server}/submodels/{submodel_id_b64}/submodel-elements/ProcessHistory",
            headers=headers,
            data=json.dumps(record).encode("utf-8"),
        )
        if resp.status_code in (200, 201):
            print(f"[process] started {record_id_short} on {component_shell_iri}")
            return record_id_short
        print(f"[process] POST ProcessRecord failed: {resp.status_code} {resp.text[:200]}")
        return None
    except requests.RequestException as e:
        print(f"[process] HTTP error writing ProcessRecord: {e}")
        return None


def write_process_completed(
    aas_server_base: str,
    component_shell_iri: str,
    record_id_short: str,
    completion_time: str | None = None,
    status: str = "Completed",
) -> bool:
    """Patch the Status and CompletionTime on an existing InProgress ProcessRecord.

    Args:
        aas_server_base: e.g. "http://localhost:8081".
        component_shell_iri: IRI of the shell that owns the ProcessTracking submodel.
        record_id_short: idShort returned by write_process_started(), e.g. "Assemble_0".
        completion_time: ISO 8601 timestamp when the step completed.
        status: "Completed", "Failed", etc.

    Returns:
        True if both fields were patched, False on any error. Never raises.
    """
    server = aas_server_base.rstrip("/")
    submodel_id = f"{component_shell_iri.rstrip('/')}/ProcessTracking"
    headers = {"Content-Type": "application/json"}
    base = f"{server}/submodels/{_b64(submodel_id)}/submodel-elements/ProcessHistory.{record_id_short}"

    ok = True
    for id_short, value in [("Status", status), ("CompletionTime", completion_time)]:
        if value is None:
            continue
        if not _put_or_post_property(base, id_short, value, headers):
            ok = False

    if ok:
        print(f"[process] completed {record_id_short} on {component_shell_iri}")
    return ok


def write_process_record(
    aas_server_base: str,
    component_shell_iri: str,
    process_type: str,
    performed_by: str,
    capability_reference_iri: str | None = None,
    skill_reference_iri: str | None = None,
    skill_name: str | None = None,
    start_time: str | None = None,
    completion_time: str | None = None,
    status: str = "Completed",
) -> bool:
    """Append a single already-complete ProcessRecord (no prior InProgress write).

    Used for output shells whose IRI was only known after the station returned its
    result — there was no shell to write InProgress to at step start.

    Returns:
        True if the record was written, False on any error. Never raises.
    """
    server = aas_server_base.rstrip("/")
    submodel_id = f"{component_shell_iri.rstrip('/')}/ProcessTracking"
    submodel_id_b64 = _b64(submodel_id)
    headers = {"Content-Type": "application/json"}

    index = _get_process_history_length(server, submodel_id_b64)
    if index is None:
        if not _create_process_tracking_submodel(server, component_shell_iri, submodel_id, headers):
            return False
        index = 0

    record_id_short = f"{process_type}_{index}"
    record = _build_process_record(
        record_id_short=record_id_short,
        process_type=process_type,
        performed_by=performed_by,
        capability_reference_iri=capability_reference_iri,
        skill_reference_iri=skill_reference_iri,
        skill_name=skill_name,
        start_time=start_time,
        completion_time=completion_time,
        status=status,
    )

    try:
        resp = requests.post(
            f"{server}/submodels/{submodel_id_b64}/submodel-elements/ProcessHistory",
            headers=headers,
            data=json.dumps(record).encode("utf-8"),
        )
        if resp.status_code in (200, 201):
            print(f"[process] wrote {record_id_short} on {component_shell_iri}")
            return True
        print(f"[process] POST ProcessRecord failed: {resp.status_code} {resp.text[:200]}")
        return False
    except requests.RequestException as e:
        print(f"[process] HTTP error writing ProcessRecord: {e}")
        return False


def _get_process_history_length(server: str, submodel_id_b64: str) -> int | None:
    """Return the number of existing ProcessRecord entries, or None if the submodel does not exist."""
    try:
        resp = requests.get(
            f"{server}/submodels/{submodel_id_b64}/submodel-elements/ProcessHistory"
        )
        if resp.status_code == 404:
            return None
        if resp.status_code == 200:
            return len(resp.json().get("value") or [])
        print(f"[process] unexpected status fetching ProcessHistory: {resp.status_code}")
        return None
    except requests.RequestException as e:
        print(f"[process] HTTP error fetching ProcessHistory: {e}")
        return None


def _create_process_tracking_submodel(
    server: str,
    component_shell_iri: str,
    submodel_id: str,
    headers: dict,
) -> bool:
    """Create an empty ProcessTracking submodel and register it on the component shell."""
    submodel = {
        "modelType": "Submodel",
        "kind": "Instance",
        "id": submodel_id,
        "idShort": "ProcessTracking",
        "description": [{"language": "en", "text": "Process history — all operations applied to this asset in order"}],
        "submodelElements": [
            {
                "modelType": "SubmodelElementCollection",
                "idShort": "ProcessHistory",
                "value": [],
            }
        ],
    }
    try:
        resp = requests.post(
            f"{server}/submodels",
            headers=headers,
            data=json.dumps(submodel).encode("utf-8"),
        )
        if resp.status_code not in (200, 201):
            print(f"[process] failed to create ProcessTracking submodel: {resp.status_code} {resp.text[:200]}")
            return False
    except requests.RequestException as e:
        print(f"[process] HTTP error creating ProcessTracking submodel: {e}")
        return False

    # Register on the component shell so the shell knows the submodel exists.
    ref_payload = json.dumps({
        "type": "ExternalReference",
        "keys": [{"type": "Submodel", "value": submodel_id}],
    })
    try:
        resp = requests.post(
            f"{server}/shells/{_b64(component_shell_iri)}/submodel-refs",
            headers=headers,
            data=ref_payload.encode("utf-8"),
        )
        if resp.status_code not in (200, 201, 204):
            # Non-fatal — submodel exists; the ref registration is best-effort.
            print(f"[process] failed to register ProcessTracking ref on shell: {resp.status_code} {resp.text[:200]}")
    except requests.RequestException as e:
        print(f"[process] HTTP error registering submodel ref: {e}")

    print(f"[process] created ProcessTracking submodel for {component_shell_iri}")
    return True


# ── BillOfMaterials ComponentReference ───────────────────────────────────────

def get_bom_entry_for_type(
    aas_server_base: str,
    product_shell_iri: str,
    component_type_iri: str,
) -> str | None:
    """Return the idShort of the BOM entry whose ComponentTypeReference matches the type IRI.

    ComponentTypeReference is the component category IRI (e.g. …/Component/PCB),
    which must equal component_type_iri directly.

    Args:
        aas_server_base: e.g. "http://localhost:8081".
        product_shell_iri: IRI of the product shell that owns BillOfMaterials.
        component_type_iri: ComponentTypeReference IRI of the ingredient.

    Returns:
        idShort of the matching BOM entry, or None if not found. Never raises.
    """
    server = aas_server_base.rstrip("/")
    submodel_id = f"{product_shell_iri.rstrip('/')}/BillOfMaterials"
    try:
        resp = requests.get(
            f"{server}/submodels/{_b64(submodel_id)}/submodel-elements/BOMEntries"
        )
        if resp.status_code != 200:
            print(f"[bom] GET BOMEntries failed: {resp.status_code} for {product_shell_iri}")
            return None
        entries = resp.json().get("value") or []
        for entry in entries:
            id_short = entry.get("idShort")
            if not id_short:
                continue
            type_matches = False
            comp_ref_filled = False
            for elem in entry.get("value") or []:
                if elem.get("idShort") == "ComponentTypeReference":
                    ref_keys = (elem.get("value") or {}).get("keys") or []
                    bom_type = next((k.get("value") for k in ref_keys), None)
                    print(f"[bom]   entry={id_short} bom_type={bom_type} wanted={component_type_iri} match={bom_type == component_type_iri}")
                    if any(k.get("value") == component_type_iri for k in ref_keys):
                        type_matches = True
                if elem.get("idShort") == "ComponentShellReference":
                    ref_val = elem.get("value")
                    if ref_val and (ref_val.get("keys") or []):
                        comp_ref_filled = True
            if type_matches and not comp_ref_filled:
                return id_short
    except requests.RequestException as e:
        print(f"[bom] HTTP error fetching BOM entries: {e}")
    return None


def write_bom_component_instance_ref(
    aas_server_base: str,
    product_shell_iri: str,
    bom_entry_id_short: str,
    instance_iri: str,
) -> bool:
    """Patch the ComponentReference ReferenceElement in a BOM entry.

    Args:
        aas_server_base: e.g. "http://localhost:8081".
        product_shell_iri: IRI of the product shell that owns BillOfMaterials.
        bom_entry_id_short: idShort of the BOM entry collection (e.g. "Bottom_Cover_1").
        instance_iri: IRI of the specific component instance shell.

    Returns:
        True on success, False on any error. Never raises.
    """
    server = aas_server_base.rstrip("/")
    submodel_id = f"{product_shell_iri.rstrip('/')}/BillOfMaterials"
    path = (
        f"{server}/submodels/{_b64(submodel_id)}"
        f"/submodel-elements/BOMEntries.{bom_entry_id_short}.ComponentShellReference"
    )
    headers = {"Content-Type": "application/json"}
    payload = json.dumps({
        "modelType": "ReferenceElement",
        "idShort": "ComponentShellReference",
        "value": {
            "type": "ModelReference",
            "keys": [{"type": "AssetAdministrationShell", "value": instance_iri}],
        },
    })
    try:
        resp = requests.put(path, headers=headers, data=payload.encode("utf-8"))
        if resp.status_code in (200, 201, 204):
            print(f"[bom] {bom_entry_id_short}.ComponentShellReference -> {instance_iri}")
            return True
        print(f"[bom] PUT ComponentShellReference failed: {resp.status_code} {resp.text[:200]}")
        return False
    except requests.RequestException as e:
        print(f"[bom] HTTP error writing ComponentShellReference: {e}")
        return False


def _build_process_record(
    record_id_short: str,
    process_type: str,
    performed_by: str,
    capability_reference_iri: str | None,
    skill_reference_iri: str | None,
    start_time: str | None,
    completion_time: str | None,
    status: str,
    skill_name: str | None = None,
) -> dict:
    elements: list[dict] = [
        {"modelType": "Property", "idShort": "ProcessType", "valueType": "xs:string", "value": process_type},
    ]

    if capability_reference_iri:
        elements.append({
            "modelType": "ReferenceElement",
            "idShort": "CapabilityReference",
            "value": {
                "type": "ModelReference",
                "keys": [{"type": "Submodel", "value": capability_reference_iri}],
            },
        })

    if skill_reference_iri and skill_name:
        elements.append({
            "modelType": "ReferenceElement",
            "idShort": "SkillReference",
            "value": {
                "type": "ModelReference",
                "keys": [
                    {"type": "Submodel", "value": skill_reference_iri},
                    {"type": "SubmodelElementCollection", "value": skill_name},
                ],
            },
        })

    elements.append({"modelType": "Property", "idShort": "PerformedBy", "valueType": "xs:string", "value": performed_by})
    elements.append({"modelType": "Property", "idShort": "Status", "valueType": "xs:string", "value": status})

    if start_time:
        elements.append({"modelType": "Property", "idShort": "StartTime", "valueType": "xs:string", "value": start_time})
    if completion_time:
        elements.append({"modelType": "Property", "idShort": "CompletionTime", "valueType": "xs:string", "value": completion_time})

    return {
        "modelType": "SubmodelElementCollection",
        "idShort": record_id_short,
        "value": elements,
    }
