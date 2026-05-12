"""Writes traceability data back to the product AAS on the BaSyx server.

After a BoP step retrieves a specific physical component (e.g. Bottom_Cover-BC003)
and runs a process on it, the product's AAS should record which exact
component instances were used. This module patches the product shell on the
BaSyx server with that data.

We append a `UsedComponents` submodel element list to the product shell's
existing data, mapping each ingredient_name to the IRI of the specific
instance that was consumed.

Today this is a best-effort POST/PATCH; if the product shell doesn't exist
on the server (some test orders), we log and continue rather than fail the
whole run.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime

import requests


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


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
