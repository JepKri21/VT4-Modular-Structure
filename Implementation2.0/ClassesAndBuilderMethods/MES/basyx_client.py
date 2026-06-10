"""
basyx_client.py — BaSyx v3 REST client for the MES.

Handles upload of shells and submodels, and queries for line controller shells
and their offered capabilities.
"""

import base64
import json
import logging
from typing import Optional

import requests

log = logging.getLogger(__name__)

BASYX_URL = "http://localhost:8081"

# (connect, read) timeout in seconds for every BaSyx call. Without this,
# requests blocks forever if BaSyx stalls — and because the MES pipeline runs
# these calls, an untimed hang freezes the whole order. A bounded timeout turns
# that into a clean RuntimeError the pipeline can recover from.
HTTP_TIMEOUT = (5, 30)


def _b64(iri: str) -> str:
    return base64.urlsafe_b64encode(iri.encode("utf-8")).decode("ascii")


def _headers() -> dict:
    return {"Content-Type": "application/json"}


# ─────────────────────────── upload ───────────────────────────────────────

def upload_shell(shell_json: dict, basyx_url: str = BASYX_URL) -> None:
    url = basyx_url.rstrip("/")
    data = json.dumps(shell_json, ensure_ascii=False).encode("utf-8")
    r = requests.post(f"{url}/shells", headers=_headers(), data=data, timeout=HTTP_TIMEOUT)
    if r.status_code in (200, 201):
        return
    if r.status_code == 409:
        shell_id = shell_json.get("id", "")
        r2 = requests.put(f"{url}/shells/{_b64(shell_id)}", headers=_headers(), data=data, timeout=HTTP_TIMEOUT)
        if r2.status_code not in (200, 201, 204):
            raise RuntimeError(f"Shell PUT failed: {r2.status_code} {r2.text}")
    else:
        raise RuntimeError(f"Shell POST failed: {r.status_code} {r.text}")


def upload_submodel(submodel_json: dict, basyx_url: str = BASYX_URL) -> None:
    url = basyx_url.rstrip("/")
    data = json.dumps(submodel_json, ensure_ascii=False).encode("utf-8")
    r = requests.post(f"{url}/submodels", headers=_headers(), data=data, timeout=HTTP_TIMEOUT)
    if r.status_code in (200, 201):
        return
    if r.status_code == 409:
        sm_id = submodel_json.get("id", "")
        r2 = requests.put(f"{url}/submodels/{_b64(sm_id)}", headers=_headers(), data=data, timeout=HTTP_TIMEOUT)
        if r2.status_code not in (200, 201, 204):
            raise RuntimeError(f"Submodel PUT failed: {r2.status_code} {r2.text}")
    else:
        raise RuntimeError(f"Submodel POST failed: {r.status_code} {r.text}")


def upload_environment(env: dict, basyx_url: str = BASYX_URL) -> None:
    """Upload all shells and submodels from an AAS environment dict."""
    for shell in env.get("assetAdministrationShells", []):
        upload_shell(shell, basyx_url)
    for submodel in env.get("submodels", []):
        upload_submodel(submodel, basyx_url)


# ─────────────────────────── fetch ────────────────────────────────────────

def fetch_submodel(submodel_iri: str, basyx_url: str = BASYX_URL) -> Optional[dict]:
    url = basyx_url.rstrip("/")
    r = requests.get(f"{url}/submodels/{_b64(submodel_iri)}", timeout=HTTP_TIMEOUT)
    if r.status_code == 200:
        return r.json()
    log.debug("fetch_submodel %s → %s", submodel_iri, r.status_code)
    return None


def fetch_shell(shell_iri: str, basyx_url: str = BASYX_URL) -> Optional[dict]:
    url = basyx_url.rstrip("/")
    r = requests.get(f"{url}/shells/{_b64(shell_iri)}", timeout=HTTP_TIMEOUT)
    if r.status_code == 200:
        return r.json()
    log.debug("fetch_shell %s → %s", shell_iri, r.status_code)
    return None


def list_shells(basyx_url: str = BASYX_URL) -> list[dict]:
    """Return all shells from BaSyx (paginated, up to 10000)."""
    url = basyx_url.rstrip("/")
    r = requests.get(f"{url}/shells", params={"limit": 10000}, timeout=HTTP_TIMEOUT)
    if r.status_code == 200:
        data = r.json()
        return data.get("result", data) if isinstance(data, dict) else data
    log.warning("list_shells → %s", r.status_code)
    return []


def find_shell_by_idshort(id_short: str, basyx_url: str = BASYX_URL) -> Optional[dict]:
    """Find a shell by idShort. Returns the first match or None."""
    url = basyx_url.rstrip("/")
    # BaSyx v3 supports filtering by idShort query param
    r = requests.get(f"{url}/shells", params={"idShort": id_short, "limit": 10}, timeout=HTTP_TIMEOUT)
    if r.status_code == 200:
        data = r.json()
        results = data.get("result", data) if isinstance(data, dict) else data
        if isinstance(results, list) and results:
            return results[0]
    # Fallback: scan all shells (slower, but works on all BaSyx versions)
    for shell in list_shells(basyx_url):
        if shell.get("idShort") == id_short:
            return shell
    return None


def resolve_shell(iri: str, basyx_url: str = BASYX_URL) -> Optional[dict]:
    """
    Fetch a shell by its IRI. If the exact lookup fails, fall back to matching
    by the last IRI segment as idShort — handles cases where the stored IRI
    is slightly different from what BaSyx has registered.
    """
    shell = fetch_shell(iri, basyx_url)
    if shell:
        return shell
    id_short = iri.rstrip("/").split("/")[-1]
    shell = find_shell_by_idshort(id_short, basyx_url)
    if not shell:
        log.warning("resolve_shell: not found by IRI or idShort=%s (%s)", id_short, iri)
    return shell


def get_submodel_refs_for_shell(shell_iri: str, basyx_url: str = BASYX_URL) -> list[str]:
    """Return submodel IRIs referenced by a shell."""
    shell = fetch_shell(shell_iri, basyx_url)
    if not shell:
        return []
    refs = shell.get("submodels", [])
    iris = []
    for ref in refs:
        keys = ref.get("keys", [])
        if keys:
            iris.append(keys[-1].get("value", ""))
    return iris


# ─────────────────────────── delete ───────────────────────────────────────

def delete_shell(shell_iri: str, basyx_url: str = BASYX_URL) -> None:
    url = basyx_url.rstrip("/")
    r = requests.delete(f"{url}/shells/{_b64(shell_iri)}", timeout=HTTP_TIMEOUT)
    if r.status_code not in (200, 204, 404):
        log.warning("delete_shell %s → %s %s", shell_iri, r.status_code, r.text)


def delete_submodel(submodel_iri: str, basyx_url: str = BASYX_URL) -> None:
    url = basyx_url.rstrip("/")
    r = requests.delete(f"{url}/submodels/{_b64(submodel_iri)}", timeout=HTTP_TIMEOUT)
    if r.status_code not in (200, 204, 404):
        log.warning("delete_submodel %s → %s %s", submodel_iri, r.status_code, r.text)


def find_element_by_idshort(elements: list, target: str) -> Optional[dict]:
    """Recursively find a submodel element by idShort."""
    for elem in elements:
        if elem.get("idShort") == target:
            return elem
        children = elem.get("value", [])
        if isinstance(children, list):
            found = find_element_by_idshort(children, target)
            if found:
                return found
    return None
