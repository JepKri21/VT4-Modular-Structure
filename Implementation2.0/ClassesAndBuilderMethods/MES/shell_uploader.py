"""
shell_uploader.py — Build and upload AAS instance shells to BaSyx.

Generates the final product shell and all required sub-assembly shells from
their preset YAML files, then uploads everything to BaSyx.
Returns a mapping of { asset_name → instance_shell_iri }.
"""

import copy
import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "BaSyx_AAS_Generator"))
from form_to_aas import build_environment

import basyx_client
import preset_loader

log = logging.getLogger(__name__)

PRESETS_DIR = Path(__file__).parent.parent / "BaSyx_AAS_Generator" / "shell_presets"

# Sub-assembly presets to upload for every AAU Mobile Phone order (bottom-up order)
SUB_ASSEMBLY_PRESET_NAMES = [
    "bottom_cover_pcb_assembly",
    "bottom_cover_pcb_fuse_assembly",
]


def _load_preset(name: str) -> dict:
    path = PRESETS_DIR / f"{name}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _inject_order_number(preset: dict, order_id: str) -> dict:
    p = copy.deepcopy(preset)
    (p.setdefault("submodels", {})
      .setdefault("Documentation", {})
      .setdefault("ProductionIdentification", {}))["OrderNumber"] = order_id
    return p


def upload_all(
    final_preset: dict,
    order_id: str,
    fuse_count: int = 1,
    basyx_url: str = basyx_client.BASYX_URL,
) -> tuple[dict[str, str], str]:
    """
    Build and upload all instance shells for one order.

    Args:
        final_preset: merged final product preset dict
        order_id: order ID stored as Documentation/ProductionIdentification/OrderNumber
        fuse_count: number of fuses ordered — expands the fuse sub-assembly so
            the uploaded shell carries one assemble step per physical fuse
        basyx_url: BaSyx server URL

    Returns:
        (shell_iris, final_product_iri)
        shell_iris maps asset_name → instance shell IRI for every uploaded shell.
    """
    shell_iris: dict[str, str] = {}

    # Upload sub-assembly shells (leaf first)
    for preset_name in SUB_ASSEMBLY_PRESET_NAMES:
        raw_preset = preset_loader.expand_fuse_assembly(_load_preset(preset_name), fuse_count)
        preset = _inject_order_number(raw_preset, order_id)
        env, iri = build_environment(preset)
        asset_name = preset.get("asset_name", preset_name)
        try:
            basyx_client.upload_environment(env, basyx_url)
            log.info("Uploaded sub-assembly shell %s → %s", asset_name, iri)
        except RuntimeError as exc:
            log.warning("Sub-assembly upload error (%s): %s", asset_name, exc)
        shell_iris[asset_name] = iri

    # Upload final product shell
    env, final_iri = build_environment(_inject_order_number(final_preset, order_id))
    asset_name = final_preset.get("asset_name", "FinalProduct")
    try:
        basyx_client.upload_environment(env, basyx_url)
        log.info("Uploaded final product shell %s → %s", asset_name, final_iri)
    except RuntimeError as exc:
        log.warning("Final product upload error: %s", exc)
    shell_iris[asset_name] = final_iri

    return shell_iris, final_iri


def delete_all(
    shell_iris: dict[str, str],
    basyx_url: str = basyx_client.BASYX_URL,
) -> None:
    """Delete all shells (and their submodels) that were uploaded for an order."""
    for asset_name, shell_iri in shell_iris.items():
        sm_iris = basyx_client.get_submodel_refs_for_shell(shell_iri, basyx_url)
        for sm_iri in sm_iris:
            basyx_client.delete_submodel(sm_iri, basyx_url)
            log.info("Deleted submodel for %s → %s", asset_name, sm_iri)
        basyx_client.delete_shell(shell_iri, basyx_url)
        log.info("Deleted shell %s → %s", asset_name, shell_iri)
