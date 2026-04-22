"""
Generate AAS Type shells and submodels using the BaSyx Python SDK.

Reads type definitions from type_configs/ and writes individual JSON files
to the output directory, mirroring the folder layout of AAS_files/.

Usage:
    cd BaSyx_AAS_Generator
    python generate_types.py                      # default output: generated_types/
    python generate_types.py --output-dir ../AAS_files/Generated

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
from pathlib import Path

# Allow running from the project root as well as from this directory
sys.path.insert(0, str(Path(__file__).parent))

from builders import (
    build_documentation_submodel,
    build_properties_submodel,
    build_bom_submodel,
    build_bop_submodel,
    build_type_shell,
    write_json,
    type_url_component,
    type_url_sub_assembly,
    type_url_final_product,
    global_asset_id,
    safe_id_short,
)
from type_configs.component_types import COMPONENT_TYPES
from type_configs.sub_assembly_types import SUB_ASSEMBLY_TYPES
from type_configs.final_product_types import FINAL_PRODUCT_TYPES


# ─────────────────────────── generators ───────────────────────────────

def generate_component_types(out: Path) -> None:
    """Generate shell + Documentation + Properties for every component type."""
    print("\n--- Component Types ---")
    shells_dir    = out / "Shells"    / "Component_Types"
    submodels_dir = out / "Submodels" / "Component_Types"

    for cfg in COMPONENT_TYPES:
        name     = cfg["name"]
        category = cfg["category"]
        url      = type_url_component(name, category)

        doc_sm   = build_documentation_submodel(url, cfg)
        props_sm = build_properties_submodel(url, cfg)

        shell = build_type_shell(
            type_id        = url,
            id_short       = safe_id_short(name),
            global_asset_id= global_asset_id(name),
            submodel_ids   = [doc_sm.id, props_sm.id],
        )

        base = f"Product-Component-{category}-{name}-Type"
        write_json(shell,    shells_dir    / f"{base}.json")
        write_json(doc_sm,   submodels_dir / f"{base}-Documentation.json")
        write_json(props_sm, submodels_dir / f"{base}-Properties.json")


def generate_sub_assembly_types(out: Path) -> None:
    """Generate shell + Documentation + BOM + BOP + Properties for every sub-assembly type."""
    print("\n--- Sub-Assembly Types ---")
    shells_dir    = out / "Shells"    / "Sub_Assembly_Types"
    submodels_dir = out / "Submodels" / "Sub_Assembly_Types"

    for cfg in SUB_ASSEMBLY_TYPES:
        name     = cfg["name"]
        category = cfg["category"]
        url      = type_url_sub_assembly(name, category)

        doc_sm   = build_documentation_submodel(url, cfg)
        props_sm = build_properties_submodel(url, cfg)
        bom_sm   = build_bom_submodel(url, cfg, include_instance_ref=True)
        bop_sm   = build_bop_submodel(url, cfg)

        shell = build_type_shell(
            type_id        = url,
            id_short       = safe_id_short(name),
            global_asset_id= global_asset_id(name),
            submodel_ids   = [doc_sm.id, bop_sm.id, bom_sm.id, props_sm.id],
        )

        base = f"Product-Sub_Assembly-{category}-{name}-Type"
        write_json(shell,    shells_dir    / f"{base}.json")
        write_json(doc_sm,   submodels_dir / f"{base}-Documentation.json")
        write_json(bom_sm,   submodels_dir / f"{base}-Bill_Of_Materials.json")
        write_json(bop_sm,   submodels_dir / f"{base}-Bill_Of_Processes.json")
        write_json(props_sm, submodels_dir / f"{base}-Properties.json")


def generate_final_product_types(out: Path) -> None:
    """Generate shell + Documentation + BOM + BOP + Properties for every final product type."""
    print("\n--- Final Product Types ---")
    shells_dir    = out / "Shells"    / "Final_Product_Types"
    submodels_dir = out / "Submodels" / "Final_Product_Types"

    for cfg in FINAL_PRODUCT_TYPES:
        name   = cfg["name"]
        family = cfg.get("family", name)
        url    = type_url_final_product(name, family)

        doc_sm   = build_documentation_submodel(url, cfg)
        props_sm = build_properties_submodel(url, cfg)
        bom_sm   = build_bom_submodel(url, cfg, include_instance_ref=False)
        bop_sm   = build_bop_submodel(url, cfg)

        shell = build_type_shell(
            type_id        = url,
            id_short       = safe_id_short(name),
            global_asset_id= global_asset_id(name),
            submodel_ids   = [doc_sm.id, bop_sm.id, bom_sm.id, props_sm.id],
        )

        base = f"Product-Final_Product-{family}-{name}-Type"
        write_json(shell,    shells_dir    / f"{base}.json")
        write_json(doc_sm,   submodels_dir / f"{base}-Documentation.json")
        write_json(bom_sm,   submodels_dir / f"{base}-Bill_Of_Materials.json")
        write_json(bop_sm,   submodels_dir / f"{base}-Bill_Of_Processes.json")
        write_json(props_sm, submodels_dir / f"{base}-Properties.json")


# ──────────────────────────── entry point ─────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate AAS Type JSON files using the BaSyx Python SDK."
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="generated_types",
        help="Root output directory (default: generated_types/)",
    )
    args = parser.parse_args()

    out = Path(args.output_dir)
    print(f"Output directory: {out.resolve()}")

    generate_component_types(out)
    generate_sub_assembly_types(out)
    generate_final_product_types(out)

    print(f"\nDone — all files written to {out.resolve()}")


if __name__ == "__main__":
    main()
