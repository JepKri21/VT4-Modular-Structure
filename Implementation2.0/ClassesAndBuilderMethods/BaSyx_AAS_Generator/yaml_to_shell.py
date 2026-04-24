"""
Build an AAS shell (AssetAdministrationShell) from a shell template YAML file.

The shell template declares the asset kind, ID patterns, and which submodels
the shell must reference.  If the YAML contains {name}/{category} placeholders,
supply them on the command line; otherwise they can be omitted entirely.

Usage:
    python yaml_to_shell.py <shell_template.yaml>
    python yaml_to_shell.py <shell_template.yaml> --output out.json
    python yaml_to_shell.py <shell_template.yaml> --upload http://localhost:8081
    python yaml_to_shell.py <shell_template.yaml> --name BottomCover --category Enclosure --upload http://localhost:8081

Shell template YAML format:
    kind: "Type"                    # "Type" or "Instance"
    description: "..."              # optional

    id_pattern: "https://aausmartlab.org/Shells/Component/{name}"
    id_short_pattern: "{name}"
    global_asset_id_pattern: "https://aausmartlab.org/Shells/Component/{name}"

    submodels:
      - template_id: "https://aausmartlab.org/Submodels/Templates/ProductProperties"
        id_short: "Properties"
        description: "..."          # optional, informational only
        required: true              # true | false

Placeholders {name} and {category} are optional — omit --name/--category when IDs are already concrete.
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

_HERE = Path(__file__).parent
SHELLS = [
    _HERE / "../Instance_Examples/Drilling_Station/Drilling_Station.yaml",
    _HERE / "../Instance_Examples/Storage_Station/Shell.yaml",
    _HERE / "../Instance_Examples/Transport_Station/Transport_Shell.yaml",
]


ASSET_KIND_MAP = {
    "type":     model.AssetKind.TYPE,
    "instance": model.AssetKind.INSTANCE,
}


def _resolve(pattern: str, name: str, category: str) -> str:
    return pattern.replace("{name}", name).replace("{category}", category)


def load_shell_from_yaml(
    path: str,
    name: str = "",
    category: str = "",
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


def upload_shell(json_str: str, url: str) -> str:
    """Upload an AAS shell JSON payload to a BaSyx server.

    The shell ID is extracted from the JSON payload itself.

    Returns:
        "created" if POST created the shell,
        "updated" if POST returned 409 and PUT succeeded.

    Raises:
        RuntimeError: If upload/update fails.
    """
    import base64
    import requests
    shell_id = json.loads(json_str).get("id", "")
    url = url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    response = requests.post(f"{url}/shells", headers=headers, data=json_str.encode("utf-8"))
    if response.status_code in (200, 201):
        return "created"
    elif response.status_code == 409:
        encoded_id = base64.urlsafe_b64encode(shell_id.encode("utf-8")).decode("ascii")
        response = requests.put(f"{url}/shells/{encoded_id}", headers=headers, data=json_str.encode("utf-8"))
        if response.status_code in (200, 201, 204):
            return "updated"
        else:
            raise RuntimeError(f"Upload failed on PUT: {response.status_code} - {response.text}")
    else:
        raise RuntimeError(f"Upload failed: {response.status_code} - {response.text}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an AAS shell from one or more shell template YAML files."
    )
    parser.add_argument("yaml_file",   nargs="*", help="Path(s) to shell template YAML(s); omit to use built-in SHELLS list")
    parser.add_argument("--name",      default="", help="Asset name for {name} placeholder")
    parser.add_argument("--category",  default="", help="Asset category for {category} placeholder")
    parser.add_argument("--output",    "-o",       help="Write JSON to this file (single file only; ignored for multiple inputs)")
    parser.add_argument("--upload",    "-u", metavar="URL",
                        help="POST JSON to <URL>/shells")
    args = parser.parse_args()

    files = [str(p) for p in args.yaml_file] if args.yaml_file else [str(p) for p in SHELLS]
    multi = len(files) > 1

    for yaml_path in files:
        if multi:
            print(f"\n--- {yaml_path} ---")
        try:
            shell = load_shell_from_yaml(str(yaml_path), args.name, args.category)
        except (KeyError, ValueError, FileNotFoundError) as exc:
            print(f"Error ({yaml_path}): {exc}", file=sys.stderr)
            sys.exit(1)

        json_str = json.dumps(shell, cls=basyx.aas.adapter.json.AASToJsonEncoder, indent=2, ensure_ascii=False)

        if args.output and not multi:
            Path(args.output).write_text(json_str, encoding="utf-8")
            print(f"Written to {args.output}")
        else:
            print(json_str)

        if args.upload:
            try:
                result = upload_shell(json_str, args.upload)
            except RuntimeError as exc:
                print(str(exc), file=sys.stderr)
                sys.exit(1)

            if result == "updated":
                print("Shell updated successfully (PUT)!")
            else:
                print("Shell uploaded successfully!")


if __name__ == "__main__":
    main()
