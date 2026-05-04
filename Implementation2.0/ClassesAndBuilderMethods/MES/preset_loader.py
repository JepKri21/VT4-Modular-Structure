"""
preset_loader.py — Load and merge a shell preset with customer order configuration.

Maps product name → preset file, then overrides only customer-configurable fields.
BOP structure is never modified — it comes entirely from the preset.
"""

import copy
import logging
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

PRESETS_DIR = Path(__file__).parent.parent / "BaSyx_AAS_Generator" / "shell_presets"

PRODUCT_PRESET_MAP: dict[str, str] = {
    "AAU Mobile Phone": "AAU-Mobile-Phone",
}

# Maps slot label (case-insensitive prefix) → preset submodel field to patch
SLOT_PROPERTY_MAP: dict[str, dict] = {
    "bottom cover": {
        "submodel": "Properties",
        "group": "MaterialProperties",
        "fields": {"material": "Material", "color": "Color", "finish": "Finish"},
    },
    "top cover": {
        "submodel": "Properties",
        "group": "MaterialProperties",
        "fields": {"material": "Material", "color": "Color", "finish": "Finish"},
    },
}


def _load_preset(preset_name: str) -> dict:
    path = PRESETS_DIR / f"{preset_name}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


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

    # Patch material properties per slot
    props_sm = preset["submodels"].setdefault("Properties", {})

    for slot_cfg in configuration:
        slot_label = (slot_cfg.get("slot") or "").lower()
        customer_props = slot_cfg.get("properties") or {}

        for slot_key, mapping in SLOT_PROPERTY_MAP.items():
            if slot_label.startswith(slot_key):
                group = props_sm.setdefault(mapping["group"], {})
                for prop_key, field_name in mapping["fields"].items():
                    val = customer_props.get(prop_key)
                    if val is not None:
                        group[field_name] = val
                break

    log.info("Loaded preset %r, merged %d slot configs", preset_name, len(configuration))
    return preset
