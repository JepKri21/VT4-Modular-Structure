"""
preset_loader.py — Load and merge a shell preset with customer order configuration.

Maps product name → preset file, then overrides only customer-configurable fields.
BOP structure is never modified — it comes entirely from the preset.
"""

import copy
import logging
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "BaSyx_AAS_Generator"))
from shell_type_utils import resolve_type

log = logging.getLogger(__name__)

PRESETS_DIR = Path(__file__).parent.parent / "BaSyx_AAS_Generator" / "shell_presets"

PRODUCT_PRESET_MAP: dict[str, str] = {
    "AAU Mobile Phone": "AAU-Mobile-Phone",
}


def _parse_numeric(val):
    """Strip unit suffix from strings like '16A' or '250V' → numeric."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    s = re.sub(r"[^0-9.]", "", str(val))
    if not s:
        return None
    try:
        f = float(s)
        return int(f) if f == int(f) else f
    except ValueError:
        return None


def _required_props_from_slot(props: dict) -> dict:
    """Convert MES order slot properties into RequiredProperties submodel form data."""
    data = {}

    material = {k: v for k, v in {
        "Material": props.get("material"),
        "Color": props.get("color"),
        "Finish": props.get("finish"),
    }.items() if v is not None}
    if material:
        data["MaterialProperties"] = material

    if props.get("weight") is not None:
        data["PhysicalDimensions"] = {"Weight": props["weight"]}

    electrical = {k: v for k, v in {
        "CurrentRating": _parse_numeric(props.get("currentRating")),
        "VoltageRating": _parse_numeric(props.get("voltageRating")),
        "Type": props.get("type"),
    }.items() if v is not None}
    if electrical:
        data["ElectricalProperties"] = electrical

    return data


def _load_preset(preset_name: str) -> dict:
    path = PRESETS_DIR / f"{preset_name}.yaml"
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return resolve_type(raw)


def load_and_merge(product_name: str, configuration: list[dict], order_number: str) -> dict:
    """
    Load the preset for product_name and merge customer configuration.

    configuration: list of { slot, componentTypeId, category, quantity, properties }
    order_number: e.g. "ORD-ABCD1234"

    Returns the merged preset dict (deep copy, original on disk untouched).
    BOP is never modified.
    """
    preset_name = PRODUCT_PRESET_MAP.get(product_name)
    if not preset_name:
        raise ValueError(f"No preset found for product: {product_name!r}")

    preset = copy.deepcopy(_load_preset(preset_name))

    # Patch Documentation ModelNumber with the order number
    doc = preset.get("submodels", {}).get("Documentation", {})
    prod_id = doc.get("ProductionIdentification", {})
    prod_id["ModelNumber"] = order_number
    doc["ProductionIdentification"] = prod_id
    preset.setdefault("submodels", {})["Documentation"] = doc

    # Build a RequiredProperties submodel per order slot and link from BOM entries
    bom_entries = (
        preset.get("submodels", {})
              .get("BillOfMaterials", {})
              .get("BOMEntries", [])
    )
    for slot_cfg in configuration:
        category = re.sub(r"[^A-Za-z0-9]", "", slot_cfg.get("category") or "")
        if not category:
            continue
        props = slot_cfg.get("properties") or {}
        req_data = _required_props_from_slot(props)
        if not req_data:
            continue
        sm_id_short = f"RequiredProperties_{category}"
        preset["submodels"][sm_id_short] = req_data
        log.info("Built %s from slot %r", sm_id_short, slot_cfg.get("slot"))

        # Link to the BOM entry whose ComponentTypeReference last segment matches
        for entry in bom_entries:
            ref_iri = entry.get("ComponentTypeReference", "")
            last_seg = ref_iri.rstrip("/").rsplit("/", 1)[-1]
            if last_seg.lower() == category.lower():
                entry["RequiredPropertiesReference"] = sm_id_short
                break

    log.info("Loaded preset %r, merged %d slot configs", preset_name, len(configuration))
    return preset
