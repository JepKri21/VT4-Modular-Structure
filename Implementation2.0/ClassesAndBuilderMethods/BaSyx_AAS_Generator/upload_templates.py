"""
Upload all AAS submodel templates and category type shells to a BaSyx server.

Scans two directories by default:
  submodel_templates/ — uploaded as ModellingKind.TEMPLATE submodels  → POST /submodels
  shell_templates/    — category type shells (those with a concrete `id:` field)
                        uploaded as AssetKind.TYPE shells             → POST /shells

Abstract blueprint shells (those with `id_pattern:` instead of `id:`) are skipped
because they have no concrete IRI and are only used as structural guides.

Existing resources are updated via PUT (409 → PUT upsert).

Usage:
    python upload_templates.py --url http://localhost:8081
    python upload_templates.py --url http://localhost:8081 --dry-run
    python upload_templates.py --url http://localhost:8081 --submodels-dir submodel_templates
    python upload_templates.py --url http://localhost:8081 --shells-dir shell_templates
"""

import argparse
import base64
import json
import sys
from pathlib import Path

import yaml
import basyx.aas.adapter.json
from basyx.aas import model

sys.path.insert(0, str(Path(__file__).parent))

from builders import _sm_ref
from yaml_to_template import load_template_from_yaml, upload_submodel
from yaml_to_shell import upload_shell
from form_to_aas import build_submodel, SM_TEMPLATE_MAP

_HERE = Path(__file__).parent


# ---------------------------------------------------------------------------
# Category type shell loader
# ---------------------------------------------------------------------------

def _build_valued_template(
    template_file: str, sm_iri: str, id_short: str, form_data: dict
) -> model.Submodel:
    """Build a TEMPLATE-kind submodel populated with static values.

    Uses build_submodel (which fills in actual values from form_data) but then
    marks the result as ModellingKind.TEMPLATE — a category-level template that
    carries default values shared by every variant in that category (e.g. fixed
    physical dimensions for all Bottom Cover shells), rather than a blank skeleton.
    """
    sm = build_submodel(template_file, sm_iri, id_short, form_data)
    sm.kind = model.ModellingKind.TEMPLATE
    return sm


def load_type_shell_from_yaml(
    path: Path,
) -> tuple[model.AssetAdministrationShell | None, list[model.Submodel]]:
    """Build an AAS type shell and its category-level template submodels.

    For each submodel listed under ``submodels:`` in the YAML a TEMPLATE-kind
    submodel is built at ``{shell_id}/{sm_id_short}`` so BaSyx stores the static
    default values (e.g. PhysicalDimensions) for that whole category.  Submodels
    without static data keep a reference to the global template IRI.

    Returns (None, []) for abstract blueprints (those with ``id_pattern:``).
    """
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if not cfg:
        return None, []

    # Abstract blueprints use id_pattern — skip them.
    if "id_pattern" in cfg:
        return None, []

    shell_id = cfg.get("id")
    if not shell_id:
        return None, []

    asset_type = cfg.get("asset_type", "")
    id_short = asset_type.replace(" ", "_") if asset_type else Path(path).stem

    submodel_refs: set[model.ModelReference] = set()
    built_submodels: list[model.Submodel] = []

    # Build category-level template submodels for each entry with static values.
    # Stored at {shell_id}/{sm_id_short} — e.g. …/Bottom_Cover/Properties.
    static_data = cfg.get("submodels") or {}
    for sm_id_short, form_data in static_data.items():
        template_file = SM_TEMPLATE_MAP.get(sm_id_short)
        if not template_file or not form_data:
            continue
        sm_iri = f"{shell_id}/{sm_id_short}"
        try:
            sm = _build_valued_template(template_file, sm_iri, sm_id_short, form_data)
            built_submodels.append(sm)
            submodel_refs.add(_sm_ref(sm_iri))
        except Exception as exc:
            print(f"  WARN   {path.name}: could not build template {sm_id_short} — {exc}")

    # Submodels without static values still reference the global template IRI.
    for sm_id_short, tmpl_iri in (cfg.get("submodel_templates") or {}).items():
        if sm_id_short not in static_data:
            submodel_refs.add(_sm_ref(tmpl_iri))

    shell = model.AssetAdministrationShell(
        id_=shell_id,
        id_short=id_short,
        asset_information=model.AssetInformation(
            asset_kind=model.AssetKind.TYPE,
            global_asset_id=shell_id,
        ),
        submodel=submodel_refs,
    )

    asset_category = cfg.get("asset_category", "")
    base_desc = cfg.get("description") or f"{asset_type} type shell"
    tag = f"[Type Shell | {asset_category}] " if asset_category else "[Type Shell] "
    shell.description = model.MultiLanguageTextType({"en": tag + base_desc})

    return shell, built_submodels


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload AAS submodel templates and category type shells to a BaSyx server."
    )
    parser.add_argument(
        "--url", "-u", default="http://localhost:8081", metavar="URL",
        help="BaSyx server base URL (default: http://localhost:8081)",
    )
    parser.add_argument(
        "--submodels-dir", metavar="DIR",
        help="Directory of submodel template YAMLs (default: submodel_templates/)",
    )
    parser.add_argument(
        "--shells-dir", metavar="DIR",
        help="Directory of shell template YAMLs (default: shell_templates/)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Build and validate everything but do not upload.",
    )
    args = parser.parse_args()

    submodels_dir = Path(args.submodels_dir) if args.submodels_dir else _HERE / "submodel_templates"
    shells_dir    = Path(args.shells_dir)    if args.shells_dir    else _HERE / "shell_templates"

    counts = {"created": 0, "updated": 0, "failed": 0, "skipped": 0}

    # ------------------------------------------------------------------
    # 1. Submodel templates
    # ------------------------------------------------------------------
    print(f"── Submodel templates ({submodels_dir.name}/)")
    sm_files = sorted(submodels_dir.glob("*.yaml")) if submodels_dir.is_dir() else []
    if not sm_files:
        print("   (no YAML files found)\n")
    else:
        for path in sm_files:
            label = path.name
            try:
                builder = load_template_from_yaml(str(path))
            except (KeyError, ValueError, FileNotFoundError) as exc:
                print(f"  SKIP   {label}  —  {exc}")
                counts["skipped"] += 1
                continue

            if args.dry_run:
                print(f"  OK     {label}")
                continue

            json_str = json.dumps(
                builder.get(),
                cls=basyx.aas.adapter.json.AASToJsonEncoder,
                indent=2,
                ensure_ascii=False,
            )
            try:
                result = upload_submodel(json_str, builder.get().id, args.url)
                tag = "CREATE" if result == "created" else "UPDATE"
                print(f"  {tag}   {label}")
                counts[result] += 1
            except RuntimeError as exc:
                print(f"  FAIL   {label}  —  {exc}")
                counts["failed"] += 1

    # ------------------------------------------------------------------
    # 2. Category type shells
    # ------------------------------------------------------------------
    print(f"\n── Shell type definitions ({shells_dir.name}/)")
    sh_files = sorted(shells_dir.glob("*.yaml")) if shells_dir.is_dir() else []
    if not sh_files:
        print("   (no YAML files found)\n")
    else:
        for path in sh_files:
            label = path.name
            try:
                shell, shell_submodels = load_type_shell_from_yaml(path)
            except Exception as exc:
                print(f"  FAIL   {label}  —  {exc}")
                counts["failed"] += 1
                continue

            if shell is None:
                print(f"  SKIP   {label}  —  abstract blueprint, no concrete id")
                counts["skipped"] += 1
                continue

            if args.dry_run:
                sm_note = f"  +{len(shell_submodels)} template(s)" if shell_submodels else ""
                print(f"  OK     {label}  ({shell.id}){sm_note}")
                continue

            # Upload category-level template submodels before the shell so the
            # shell's submodel references can be resolved immediately.
            for sm in shell_submodels:
                sm_json = json.dumps(
                    sm,
                    cls=basyx.aas.adapter.json.AASToJsonEncoder,
                    indent=2,
                    ensure_ascii=False,
                )
                try:
                    result = upload_submodel(sm_json, sm.id, args.url)
                    tag = "CREATE" if result == "created" else "UPDATE"
                    print(f"  {tag}   {label}  → {sm.id_short} template")
                    counts[result] += 1
                except RuntimeError as exc:
                    print(f"  FAIL   {label}  → {sm.id_short} template — {exc}")
                    counts["failed"] += 1

            json_str = json.dumps(
                shell,
                cls=basyx.aas.adapter.json.AASToJsonEncoder,
                indent=2,
                ensure_ascii=False,
            )
            try:
                result = upload_shell(json_str, args.url)
                tag = "CREATE" if result == "created" else "UPDATE"
                print(f"  {tag}   {label}  ({shell.id})")
                counts[result] += 1
            except RuntimeError as exc:
                print(f"  FAIL   {label}  —  {exc}")
                counts["failed"] += 1

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(
        f"\nDone: {counts['created']} created, {counts['updated']} updated, "
        f"{counts['failed']} failed, {counts['skipped']} skipped."
        if not args.dry_run else
        f"\nDry run complete — {counts['skipped']} file(s) skipped."
    )


if __name__ == "__main__":
    main()
