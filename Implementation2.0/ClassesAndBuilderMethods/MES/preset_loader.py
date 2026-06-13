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


def _ordered_count(configuration: list[dict], category: str) -> int:
    """Sum quantities for all slots whose category matches (alphanumeric, case-insensitive)."""
    norm = re.sub(r"[^A-Za-z0-9]", "", category).lower()
    return sum(
        slot_cfg.get("quantity", 1)
        for slot_cfg in configuration
        if re.sub(r"[^A-Za-z0-9]", "", slot_cfg.get("category") or "").lower() == norm
    )


def fuse_count(configuration: list[dict]) -> int:
    """Number of fuses selected in the webstore order (>= 1).

    The fuse sub-assembly always mounts at least one fuse, so a configuration
    with no explicit Fuse slot still yields 1.
    """
    return max(1, _ordered_count(configuration, "Fuse"))


# IRIs referenced when expanding the per-fuse process steps.
_BOTTOM_COVER_PCB_IRI = "https://aausmartlab.org/Shells/Assembly/BottomCoverPCB"
_BOTTOM_COVER_PCB_FUSE_IRI = "https://aausmartlab.org/Shells/Assembly/BottomCoverPCBFuse"
_FUSE_COMPONENT_IRI = "https://aausmartlab.org/Shells/Component/Fuse"


def _expand_fuse_step(template: dict, index: int) -> dict:
    """Build the i-th concrete 'Assemble Fuse {i}' step from the PerFuseUnit template.

    Fuse 1 consumes the BottomCoverPCB sub-assembly + a fuse; fuses 2..N build on
    the partial BottomCoverPCBFuse + a fuse. TargetPosition.YPos is offset per
    fuse so each lands in a distinct physical slot.
    """
    step = copy.deepcopy({k: v for k, v in template.items() if k != "PerFuseUnit"})
    step["Operation"] = f"Assemble Fuse {index}"
    step["ProcessType"] = "Assemble"

    if index == 1:
        step["RequiredComponents"] = ["BottomCoverPCB", "Fuse"]
        input_refs = [_BOTTOM_COVER_PCB_IRI, _FUSE_COMPONENT_IRI]
    else:
        step["RequiredComponents"] = ["Fuse"]
        input_refs = [_BOTTOM_COVER_PCB_FUSE_IRI, _FUSE_COMPONENT_IRI]

    base_y = (
        template.get("CapabilityParams", {})
        .get("Parameters", {})
        .get("TargetPosition", {})
        .get("YPos", -10.0)
    )
    base_x = (
        template.get("CapabilityParams", {})
        .get("Parameters", {})
        .get("TargetPosition", {})
        .get("XPos", 5.0)
    )

    params = step.setdefault("CapabilityParams", {}).setdefault("Parameters", {})
    params["TargetPosition"] = {"XPos": base_x, "YPos": base_y * index}
    params["OperationLabel"] = [
        {"language": "en", "text": f"Assemble fuse {index} onto PCB"},
        {"language": "da", "text": f"Monter sikring {index} på PCB"},
    ]
    step["CapabilityParams"]["ProcessTransformations"] = {
        f"AssembleFuse{index}": {
            "InputTypes": {"ComponentTypeReference": list(input_refs)},
            "OutputTypes": {"ComponentTypeReference": [_BOTTOM_COVER_PCB_FUSE_IRI]},
        }
    }
    step["CapabilityParams"]["SupportedComponents"] = list(input_refs)
    return step


def expand_fuse_assembly(preset: dict, count: int) -> dict:
    """Expand a fuse sub-assembly preset to exactly `count` fuses.

    Replaces every BOM entry / process step flagged `PerFuseUnit: true` with
    `count` concrete copies (one per physical fuse). Returns a deep copy; presets
    without PerFuseUnit markers are returned unchanged (cheap no-op).

    Both the shell uploader (so BaSyx carries N steps) and the workorder builder
    (so it traverses N steps) call this with the same count, guaranteeing the
    generated operation names line up for BaSyx lookups.
    """
    submodels = preset.get("submodels", {})
    bom = submodels.get("BillOfMaterials", {})
    bop = submodels.get("BillOfProcesses", {})

    bom_entries = bom.get("BOMEntries", [])
    bop_steps = bop.get("ProcessSteps", [])
    fuse_template = next((e for e in bom_entries if e.get("PerFuseUnit")), None)
    has_markers = fuse_template is not None or any(
        s.get("PerFuseUnit") for s in bop_steps
    )
    if not has_markers:
        return preset

    # Clamp to the template's allowed range — the single source of truth for how
    # many fuses a phone may have (also enforced webshop-side, but this guards
    # any order that reaches the MES out of range).
    lo = fuse_template.get("MinQuantity", 1) if fuse_template else 1
    hi = fuse_template.get("MaxQuantity") if fuse_template else None
    clamped = max(lo, count)
    if hi is not None:
        clamped = min(hi, clamped)
    if clamped != count:
        log.warning("Requested %d fuse(s) out of range [%s, %s] — clamped to %d",
                    count, lo, hi, clamped)
    count = clamped

    preset = copy.deepcopy(preset)
    submodels = preset["submodels"]
    bom = submodels["BillOfMaterials"]
    bop = submodels["BillOfProcesses"]

    _marker_keys = {"PerFuseUnit", "MinQuantity", "MaxQuantity"}
    new_entries: list[dict] = []
    for entry in bom.get("BOMEntries", []):
        if entry.get("PerFuseUnit"):
            for i in range(1, count + 1):
                fe = {k: v for k, v in entry.items() if k not in _marker_keys}
                fe["Description"] = f"Fuse Slow Blow {i}"
                fe["Quantity"] = 1
                new_entries.append(fe)
        else:
            new_entries.append(entry)
    bom["BOMEntries"] = new_entries

    new_steps: list[dict] = []
    for step in bop.get("ProcessSteps", []):
        if step.get("PerFuseUnit"):
            new_steps.extend(_expand_fuse_step(step, i) for i in range(1, count + 1))
        else:
            new_steps.append(step)
    bop["ProcessSteps"] = new_steps

    if "ProcessTracking" in bop:
        bop["ProcessTracking"] = [
            {"StepRef": f"Assemble_Fuse_{i}", "StepStatus": "Pending"}
            for i in range(1, count + 1)
        ]

    log.info("Expanded fuse sub-assembly to %d fuse(s)", count)
    return preset


def _prune_conditional_entries(entries: list[dict], ordered_count: int) -> list[dict]:
    """Remove entries where MinOrderedQuantity > ordered_count, and strip the marker from survivors."""
    result = []
    for e in entries:
        if e.get("MinOrderedQuantity", 1) <= ordered_count:
            result.append({k: v for k, v in e.items() if k != "MinOrderedQuantity"})
    return result


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

    # Prune BOM entries and BOP steps that require more fuses than ordered
    fuse_count = _ordered_count(configuration, "Fuse")
    if fuse_count > 0:
        bom = preset.get("submodels", {}).get("BillOfMaterials", {})
        bop = preset.get("submodels", {}).get("BillOfProcesses", {})
        if bom:
            bom["BOMEntries"] = _prune_conditional_entries(bom.get("BOMEntries", []), fuse_count)
        if bop:
            bop["ProcessTracking"] = _prune_conditional_entries(bop.get("ProcessTracking", []), fuse_count)
            bop["ProcessSteps"] = _prune_conditional_entries(bop.get("ProcessSteps", []), fuse_count)
        log.info("Fuse count from order: %d — preset pruned accordingly", fuse_count)

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
