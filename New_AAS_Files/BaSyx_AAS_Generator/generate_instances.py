"""
Generate AAS Instance shells and submodels using the BaSyx Python SDK.

Each instance is driven by an "order dict" that supplies:
  serial         - unique serial number for this physical unit (str)
  created_date   - ISO date string, e.g. "2026-04-16" (str)
  <key>          - configurable property values. The lookup tries (in order):
                     1. order["Material"]               exact id_short
                     2. order["material"]               lowercase id_short
                     3. order["bottom_cover_material"]  {type_name}_{id_short_lower}
                   This means a key like "bottom_cover_material" serves double duty:
                   it fills the model_number_template placeholder AND maps to the
                   Material property, so no duplication is needed.
  quantities     - (optional) dict of BOM component id_short -> actual quantity
                   for components where qty_min != qty_max (e.g. Fuse).
  instance_refs  - (optional) dict of BOM component id_short -> AAS instance ID.
                   Records which physical sub-component was consumed during assembly.
                   Leave absent or None to leave blank (filled during production).

Usage:
    cd BaSyx_AAS_Generator
    python generate_instances.py                      # default output: generated_instances/
    python generate_instances.py --output-dir ../AAS_files/Instances

Output structure:
    <output>/
    ├── Shells/
    │   ├── Component_Types/
    │   ├── Sub_Assembly_Types/
    │   └── Final_Product_Types/
    └── Submodels/
        ├── Component_Types/
        ├── Sub_Assembly_Types/
        └── Final_Product_Types/
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from basyx.aas import model

from builders import (
    _ext_ref,
    _sm_ref,
    _lang,
    write_json,
    XS_TYPE_MAP,
    _convert_value,
)
from type_configs.component_types import COMPONENT_TYPES
from type_configs.sub_assembly_types import SUB_ASSEMBLY_TYPES
from type_configs.final_product_types import FINAL_PRODUCT_TYPES

BASE_NS = "https://aausmartlab.com"
INST = model.ModellingKind.INSTANCE


# ──────────────────────────── URL / ID helpers ────────────────────────────────

def instance_url_component(name: str, category: str, serial: str) -> str:
    return f"{BASE_NS}/Assets/Product/Component/{category}/{name}/Instance/{serial}"


def instance_url_sub_assembly(name: str, category: str, serial: str) -> str:
    return f"{BASE_NS}/Assets/Product/Sub_Assembly/{category}/{name}/Instance/{serial}"


def instance_url_final_product(name: str, family: str, serial: str) -> str:
    return f"{BASE_NS}/Assets/Product/Final_Product/{family}/{name}/Instance/{serial}"


def instance_global_asset_id(name: str, serial: str) -> str:
    return f"{BASE_NS}/Assets/Product/AAU/{name}/Instance/{serial}"


def safe_id_short_instance(name: str, serial: str) -> str:
    safe = serial.replace("-", "_").replace(" ", "_")
    return name.replace("-", "_") + "_" + safe


# ─────────────────────────── order helpers ───────────────────────────────────

def _resolve_model_number(template: str, order: dict) -> str:
    """Fill {key} placeholders in the model number template from the order dict."""
    return template.format_map(defaultdict(str, order))


def _lookup(id_short: str, cfg_name: str, order: dict) -> Any:
    """
    Look up a configurable property value from the order dict.

    Tries (in order):
      1. order["Material"]                  exact id_short
      2. order["material"]                  lowercase id_short
      3. order["bottom_cover_material"]     {type_name_snake}_{id_short_lower}
         (matches the model_number_template placeholder naming convention)
    """
    prefix = cfg_name.lower().replace("-", "_")
    for key in (id_short, id_short.lower(), f"{prefix}_{id_short.lower()}"):
        if key in order:
            return order[key]
    return None


# ──────────────────────────── submodel builders ──────────────────────────────

def build_instance_documentation(inst_url: str, cfg: dict, order: dict) -> model.Submodel:
    model_number = _resolve_model_number(cfg.get("model_number_template", ""), order)
    return model.Submodel(
        id_=f"{inst_url}/Documentation",
        id_short="Documentation",
        kind=INST,
        semantic_id=_ext_ref(f"{BASE_NS}/Data/Documentation"),
        description=_lang(f"Documentation for {cfg['name']} instance {order['serial']}"),
        submodel_element=[
            model.Property(
                id_short="Product_Name",
                value_type=model.datatypes.String,
                value=model.datatypes.String(cfg["display_name"]),
            ),
            model.Property(
                id_short="Product_Type",
                value_type=model.datatypes.String,
                value=model.datatypes.String(cfg["product_type"]),
            ),
            model.MultiLanguageProperty(
                id_short="Description",
                value=_lang(cfg.get("description", "")),
            ),
            # Model_Number_Configuration is intentionally omitted from instances
            model.Property(
                id_short="Model_Number",
                value_type=model.datatypes.String,
                value=model.datatypes.String(model_number),
            ),
            model.Property(
                id_short="Created_Date",
                value_type=model.datatypes.String,
                value=model.datatypes.String(order["created_date"]),
            ),
        ],
    )


def build_instance_properties(inst_url: str, cfg: dict, order: dict) -> model.Submodel:
    props = []
    for p in cfg.get("properties", []):
        vt = XS_TYPE_MAP.get(p.get("value_type", "xs:string"), model.datatypes.String)
        # Fixed default from type config takes precedence; otherwise look in order.
        raw = p.get("value")
        if raw is None:
            raw = _lookup(p["id_short"], cfg["name"], order)
        value = _convert_value(raw, vt)

        kwargs: dict[str, Any] = dict(id_short=p["id_short"], value_type=vt, value=value)
        if p.get("unit_url"):
            kwargs["semantic_id"] = _ext_ref(p["unit_url"])
        if p.get("description"):
            kwargs["description"] = _lang(p["description"])
        props.append(model.Property(**kwargs))

    collection = model.SubmodelElementCollection(
        id_short="List_Of_Properties",
        semantic_id=_ext_ref(f"{BASE_NS}/Submodels/List_Of_Properties"),
        description=_lang(f"Properties for {cfg['name']}"),
        value=props,
    )
    return model.Submodel(
        id_=f"{inst_url}/Properties",
        id_short="Properties",
        kind=INST,
        semantic_id=_ext_ref(f"{BASE_NS}/Data/Parts/Variants"),
        submodel_element=[collection],
    )


def build_instance_bom(
    inst_url: str,
    cfg: dict,
    order: dict,
    include_instance_ref: bool = True,
) -> model.Submodel:
    quantities    = order.get("quantities", {})
    instance_refs = order.get("instance_refs", {})
    collections: list[model.SubmodelElementCollection] = []

    for comp in cfg.get("bom_components", []):
        qty = quantities.get(comp["id_short"], comp.get("qty_min", 1))

        comp_props: list[model.Property] = [
            model.Property(
                id_short="Component_Type",
                value_type=model.datatypes.String,
                value=model.datatypes.String(comp["component_type_url"]),
            ),
            model.Property(
                id_short="Quantity_Min",
                value_type=model.datatypes.Integer,
                value=model.datatypes.Integer(comp.get("qty_min", 1)),
            ),
            model.Property(
                id_short="Quantity_Max",
                value_type=model.datatypes.Integer,
                value=model.datatypes.Integer(comp.get("qty_max", 1)),
            ),
            model.Property(
                id_short="Quantity",
                value_type=model.datatypes.Integer,
                value=model.datatypes.Integer(qty),
                description=_lang("Actual quantity used in this instance"),
            ),
        ]

        if "qty_default" in comp:
            comp_props.append(
                model.Property(
                    id_short="Quantity_Default",
                    value_type=model.datatypes.Integer,
                    value=model.datatypes.Integer(comp["qty_default"]),
                )
            )

        comp_props.append(
            model.Property(
                id_short="Is_Configurable",
                value_type=model.datatypes.Boolean,
                value=bool(comp.get("is_configurable", False)),
            )
        )

        if include_instance_ref:
            ref_val = instance_refs.get(comp["id_short"])
            comp_props.append(
                model.Property(
                    id_short="Instance_Refference",
                    value_type=model.datatypes.String,
                    value=model.datatypes.String(ref_val) if ref_val else None,
                    description=_lang(
                        "AAS ID of the physical instance used during assembly."
                    ),
                )
            )

        sec_kwargs: dict[str, Any] = dict(
            id_short=comp["id_short"],
            description=_lang(comp.get("description", comp["id_short"])),
            value=comp_props,
        )
        if comp.get("semantic_url"):
            sec_kwargs["semantic_id"] = _ext_ref(comp["semantic_url"])
        collections.append(model.SubmodelElementCollection(**sec_kwargs))

    components = model.SubmodelElementCollection(
        id_short="Components",
        semantic_id=_ext_ref(f"{BASE_NS}/Submodels/BOM/Components"),
        description=_lang("Components and sub-assemblies used in this instance"),
        value=collections,
    )
    return model.Submodel(
        id_=f"{inst_url}/Bill_Of_Materials",
        id_short="Bill_Of_Materials",
        kind=INST,
        semantic_id=_ext_ref(f"{BASE_NS}/Data/BOM"),
        submodel_element=[components],
    )


def build_instance_bop(inst_url: str, cfg: dict) -> model.Submodel:
    step_collections: list[model.SubmodelElementCollection] = []

    for step in cfg.get("bop_steps", []):
        constraints = step.get("constraints", [])
        constraint_props = [
            model.Property(
                id_short=f"Constraint_Id_{i + 1}",
                value_type=model.datatypes.String,
                value=model.datatypes.String(c),
            )
            for i, c in enumerate(constraints)
        ] or [
            model.Property(
                id_short="Constraint_Id_1",
                value_type=model.datatypes.String,
                value=None,
            )
        ]

        required_props = [
            model.Property(
                id_short=f"Component_Id_{i + 1}",
                value_type=model.datatypes.String,
                value=model.datatypes.String(c),
            )
            for i, c in enumerate(step.get("required_components", []))
        ]

        step_collections.append(
            model.SubmodelElementCollection(
                id_short=step["id_short"],
                value=[
                    model.SubmodelElementCollection(
                        id_short="Process_Constraints",
                        value=constraint_props,
                    ),
                    model.SubmodelElementCollection(
                        id_short="Required_Components",
                        value=required_props,
                    ),
                    model.SubmodelElementCollection(
                        id_short="Parameters",
                        value=[
                            model.Property(
                                id_short="Selected_Operation",
                                value_type=model.datatypes.String,
                                value=model.datatypes.String(step.get("operation", "")),
                            )
                        ],
                    ),
                ],
            )
        )

    return model.Submodel(
        id_=f"{inst_url}/Bill_Of_Processes",
        id_short="Bill_Of_Processes",
        kind=INST,
        semantic_id=_ext_ref(f"{BASE_NS}/Data/BillOfOperations"),
        description=_lang("Manufacturing and assembly operations for this instance."),
        submodel_element=step_collections,
    )


def build_instance_shell(
    inst_id: str,
    id_short: str,
    global_asset_id: str,
    submodel_ids: list[str],
) -> model.AssetAdministrationShell:
    return model.AssetAdministrationShell(
        id_=inst_id,
        id_short=id_short,
        asset_information=model.AssetInformation(
            asset_kind=model.AssetKind.INSTANCE,
            global_asset_id=global_asset_id,
        ),
        submodel={_sm_ref(sm_id) for sm_id in submodel_ids},
    )


# ─────────────────────────── high-level generators ───────────────────────────

def generate_component_instance(cfg: dict, order: dict, out: Path) -> None:
    name     = cfg["name"]
    category = cfg["category"]
    serial   = order["serial"]
    url      = instance_url_component(name, category, serial)

    doc_sm   = build_instance_documentation(url, cfg, order)
    props_sm = build_instance_properties(url, cfg, order)
    shell    = build_instance_shell(
        inst_id         = url,
        id_short        = safe_id_short_instance(name, serial),
        global_asset_id = instance_global_asset_id(name, serial),
        submodel_ids    = [doc_sm.id, props_sm.id],
    )

    shells_dir    = out / "Shells"    / "Component_Types"
    submodels_dir = out / "Submodels" / "Component_Types"
    base = f"Product-Component-{category}-{name}-Instance-{serial}"
    write_json(shell,    shells_dir    / f"{base}.json")
    write_json(doc_sm,   submodels_dir / f"{base}-Documentation.json")
    write_json(props_sm, submodels_dir / f"{base}-Properties.json")


def generate_sub_assembly_instance(cfg: dict, order: dict, out: Path) -> None:
    name     = cfg["name"]
    category = cfg["category"]
    serial   = order["serial"]
    url      = instance_url_sub_assembly(name, category, serial)

    doc_sm   = build_instance_documentation(url, cfg, order)
    props_sm = build_instance_properties(url, cfg, order)
    bom_sm   = build_instance_bom(url, cfg, order, include_instance_ref=True)
    bop_sm   = build_instance_bop(url, cfg)
    shell    = build_instance_shell(
        inst_id         = url,
        id_short        = safe_id_short_instance(name, serial),
        global_asset_id = instance_global_asset_id(name, serial),
        submodel_ids    = [doc_sm.id, bop_sm.id, bom_sm.id, props_sm.id],
    )

    shells_dir    = out / "Shells"    / "Sub_Assembly_Types"
    submodels_dir = out / "Submodels" / "Sub_Assembly_Types"
    base = f"Product-Sub_Assembly-{category}-{name}-Instance-{serial}"
    write_json(shell,    shells_dir    / f"{base}.json")
    write_json(doc_sm,   submodels_dir / f"{base}-Documentation.json")
    write_json(bom_sm,   submodels_dir / f"{base}-Bill_Of_Materials.json")
    write_json(bop_sm,   submodels_dir / f"{base}-Bill_Of_Processes.json")
    write_json(props_sm, submodels_dir / f"{base}-Properties.json")


def generate_final_product_instance(cfg: dict, order: dict, out: Path) -> None:
    name   = cfg["name"]
    family = cfg.get("family", name)
    serial = order["serial"]
    url    = instance_url_final_product(name, family, serial)

    doc_sm   = build_instance_documentation(url, cfg, order)
    props_sm = build_instance_properties(url, cfg, order)
    bom_sm   = build_instance_bom(url, cfg, order, include_instance_ref=False)
    bop_sm   = build_instance_bop(url, cfg)
    shell    = build_instance_shell(
        inst_id         = url,
        id_short        = safe_id_short_instance(name, serial),
        global_asset_id = instance_global_asset_id(name, serial),
        submodel_ids    = [doc_sm.id, bop_sm.id, bom_sm.id, props_sm.id],
    )

    shells_dir    = out / "Shells"    / "Final_Product_Types"
    submodels_dir = out / "Submodels" / "Final_Product_Types"
    base = f"Product-Final_Product-{family}-{name}-Instance-{serial}"
    write_json(shell,    shells_dir    / f"{base}.json")
    write_json(doc_sm,   submodels_dir / f"{base}-Documentation.json")
    write_json(bom_sm,   submodels_dir / f"{base}-Bill_Of_Materials.json")
    write_json(bop_sm,   submodels_dir / f"{base}-Bill_Of_Processes.json")
    write_json(props_sm, submodels_dir / f"{base}-Properties.json")


# ─────────────────────────── example orders ──────────────────────────────────
#
# One order per defined type. In production these come from an order
# management system; replace or extend EXAMPLE_ORDERS as needed.
#
# Key naming tip: keys that match model_number_template placeholders
# (e.g. "bottom_cover_material") are also picked up automatically as
# property values via _lookup(), so no duplication is required.

EXAMPLE_ORDERS: dict[str, dict] = {
    # ── Components ──────────────────────────────────────────────────────────
    "Bottom_Cover": {
        "serial": "BC-001",
        "created_date": "2026-04-16",
        # Maps to model number template AND Material / Color / Finish properties
        "bottom_cover_material": "Steel",
        "bottom_cover_color": "Black",
        "bottom_cover_finish": "Glossy",
    },
    "Fuse": {
        "serial": "FUSE-001",
        "created_date": "2026-04-16",
        # Maps to model number template AND Type / Current_Rating properties
        "fuse_type": "Fast-acting",
        "fuse_current_rating": "5",
    },
    "PCB": {
        "serial": "PCB-001",
        "created_date": "2026-04-16",
        "pcb_variant": "V1",
        # Length / Width / Layers have fixed defaults in the type config,
        # so no overrides are needed here.
    },
    "Top_Cover": {
        "serial": "TC-001",
        "created_date": "2026-04-16",
        "top_cover_material": "Aluminum",
        "top_cover_color": "Silver",
        "top_cover_finish": "Matte",
    },
    # ── Sub-Assemblies ───────────────────────────────────────────────────────
    "Bottom_Cover-PCB": {
        "serial": "BC-PCB-001",
        "created_date": "2026-04-16",
        "variant": "V1",
        # instance_refs: which physical parts were consumed (fill during production)
        "instance_refs": {
            "Bottom_Cover": f"{BASE_NS}/Assets/Product/Component/AAU/Bottom_Cover/Instance/BC-001",
            "PCB":          f"{BASE_NS}/Assets/Product/Component/AAU/PCB/Instance/PCB-001",
        },
    },
    "Bottom_Cover-PCB-Fuse": {
        "serial": "BC-PCB-F-001",
        "created_date": "2026-04-16",
        # "nr_fuses" satisfies the model number template AND maps to the
        # Nr_Fuses property (lowercase id_short match via _lookup).
        "nr_fuses": 2,
        "quantities": {"Fuse": 2},
        "instance_refs": {
            "Bottom_Cover_PCB": f"{BASE_NS}/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB/Instance/BC-PCB-001",
            "Fuse":             f"{BASE_NS}/Assets/Product/Component/AAU/Fuse/Instance/FUSE-001",
        },
    },
    # ── Final Products ───────────────────────────────────────────────────────
    "Telefon_Pro_Max": {
        "serial": "TEL-001",
        "created_date": "2026-04-16",
        # Model number template:
        # TEL-{bottom_cover_material}-{bottom_cover_color}-{top_cover_material}-{top_cover_color}-{nr_fuses}F
        "bottom_cover_material": "Steel",
        "bottom_cover_color": "Black",
        "top_cover_material": "Aluminum",
        "top_cover_color": "Silver",
        "nr_fuses": 2,          # also maps to Nr_Fuses property
        # Properties with no default in type config and no matching template key:
        "Length": 150,
        "Width": 75,
        "Height": 8,
        "Material": "Steel/Aluminum",
        "Color": "Black/Silver",
    },
}


# ──────────────────────────── entry point ────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate AAS Instance JSON files using the BaSyx Python SDK."
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="generated_instances",
        help="Root output directory (default: generated_instances/)",
    )
    args = parser.parse_args()

    out = Path(args.output_dir)
    print(f"Output directory: {out.resolve()}")

    comp_by_name = {c["name"]: c for c in COMPONENT_TYPES}
    sa_by_name   = {s["name"]: s for s in SUB_ASSEMBLY_TYPES}
    fp_by_name   = {f["name"]: f for f in FINAL_PRODUCT_TYPES}

    print("\n--- Component Instances ---")
    for name, cfg in comp_by_name.items():
        if name in EXAMPLE_ORDERS:
            generate_component_instance(cfg, EXAMPLE_ORDERS[name], out)

    print("\n--- Sub-Assembly Instances ---")
    for name, cfg in sa_by_name.items():
        if name in EXAMPLE_ORDERS:
            generate_sub_assembly_instance(cfg, EXAMPLE_ORDERS[name], out)

    print("\n--- Final Product Instances ---")
    for name, cfg in fp_by_name.items():
        if name in EXAMPLE_ORDERS:
            generate_final_product_instance(cfg, EXAMPLE_ORDERS[name], out)

    print(f"\nDone — all files written to {out.resolve()}")


if __name__ == "__main__":
    main()
