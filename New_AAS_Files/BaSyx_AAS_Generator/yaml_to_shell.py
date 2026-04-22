"""
Build an AAS shell (AssetAdministrationShell) from a shell template YAML file.

The shell template declares the asset kind, ID patterns, and which submodels
the shell must reference.  Concrete values for {name} and {category} are
supplied on the command line.

Usage:
    python yaml_to_shell.py <shell_template.yaml> --name BottomCover --category Enclosure
    python yaml_to_shell.py <shell_template.yaml> --name BottomCover --category Enclosure --output out.json
    python yaml_to_shell.py <shell_template.yaml> --name BottomCover --category Enclosure --upload http://localhost:8081

Shell template YAML format:
    kind: "Type"                    # "Type" or "Instance"
    description: "..."              # optional

    id_pattern: "https://aausmartlab.com/AAS/Component/{category}/{name}/Type"
    id_short_pattern: "{name}_Type"
    global_asset_id_pattern: "https://aausmartlab.com/Assets/Product/AAU/{name}/Type"

    submodels:
      - template_id: "https://aausmartlab.com/SubmodelTemplate/Component/Properties/1/0"
        id_short: "ComponentProperties"
        description: "..."          # optional, informational only
        required: true              # true | false

Placeholders resolved at runtime: {name}, {category}
"""

import argparse
import json
import sys
from pathlib import Path

import yaml
from basyx.aas import model

sys.path.insert(0, str(Path(__file__).parent))

import basyx.aas.adapter.json
from builders import _sm_ref


ASSET_KIND_MAP = {
    "type":     model.AssetKind.TYPE,
    "instance": model.AssetKind.INSTANCE,
}


def _resolve(pattern: str, name: str, category: str) -> str:
    return pattern.replace("{name}", name).replace("{category}", category)


def load_shell_from_yaml(
    path: str,
    name: str,
    category: str,
) -> model.AssetAdministrationShell:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    for key in ("kind", "id_pattern", "id_short_pattern", "global_asset_id_pattern"):
        if not cfg.get(key):
            raise KeyError(f"Shell template YAML must have a '{key}' field")

    kind_str = cfg["kind"].strip().lower()
    asset_kind = ASSET_KIND_MAP.get(kind_str)
    if asset_kind is None:
        raise ValueError(f"Unknown kind '{cfg['kind']}' — expected 'Type' or 'Instance'")

    shell_id       = _resolve(cfg["id_pattern"],            name, category)
    id_short       = _resolve(cfg["id_short_pattern"],      name, category)
    global_asset_id = _resolve(cfg["global_asset_id_pattern"], name, category)

    submodel_refs: set[model.ModelReference] = set()
    for sm in cfg.get("submodels", []):
        template_id = sm.get("template_id")
        if not template_id:
            raise ValueError(f"Each submodel entry must have a 'template_id' field (got: {sm})")
        submodel_refs.add(_sm_ref(template_id))

    shell = model.AssetAdministrationShell(
        id_=shell_id,
        id_short=id_short,
        asset_information=model.AssetInformation(
            asset_kind=asset_kind,
            global_asset_id=global_asset_id,
        ),
        submodel=submodel_refs,
    )

    if desc := cfg.get("description"):
        shell.description = model.MultiLanguageTextType({"en": desc})

    return shell


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an AAS shell from a shell template YAML file."
    )
    parser.add_argument("yaml_file",   help="Path to the shell template YAML")
    parser.add_argument("--name",      required=True, help="Asset name, e.g. BottomCover")
    parser.add_argument("--category",  default="",    help="Asset category, e.g. Enclosure")
    parser.add_argument("--output",    "-o",          help="Write JSON to this file (default: stdout)")
    parser.add_argument("--upload",    "-u", metavar="URL",
                        help="POST JSON to <URL>/shells")
    args = parser.parse_args()

    try:
        shell = load_shell_from_yaml(args.yaml_file, args.name, args.category)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    json_str = json.dumps(shell, cls=basyx.aas.adapter.json.AASToJsonEncoder, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(json_str, encoding="utf-8")
        print(f"Written to {args.output}")
    else:
        print(json_str)

    if args.upload:
        import requests
        url = args.upload.rstrip("/")
        response = requests.post(
            f"{url}/shells",
            headers={"Content-Type": "application/json"},
            data=json_str.encode("utf-8"),
        )
        if response.status_code in (200, 201):
            print("Shell uploaded successfully!")
        else:
            print(f"Upload failed: {response.status_code} - {response.text}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
