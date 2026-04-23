"""
form_to_aas.py — Build a full AAS environment JSON from UI form data.

Reads a JSON payload from stdin, outputs AAS environment JSON to stdout.

Input schema:
{
  "shell_type":      "component_shell",
  "name":            "FuseBox_A1",
  "category":        "Electrical",
  "shell_id":        "https://aausmartlab.com/AAS/.../FuseBox_A1/Instance/<uuid>",
  "global_asset_id": "https://aausmartlab.com/Assets/.../FuseBox_A1/Instance/<uuid>",
  "submodels": [
    {
      "template_file": "component_properties",
      "id_short":      "ComponentProperties",
      "id":            "https://.../Submodel/ComponentProperties/0",
      "form_data":     { "ModelNumber": "FM-A-001", ... }
    }
  ]
}

Output: AAS environment JSON compatible with BaSyx v3 REST API.

Exit codes: 0 = success, 1 = error (traceback on stderr).
"""

import json
import re
import sys
from pathlib import Path

import yaml
from basyx.aas import model

sys.path.insert(0, str(Path(__file__).parent))

import basyx.aas.adapter.json
from builders import XS_TYPE_MAP, _convert_value, _sm_ref
from instance_generator_class import AASInstanceBuilder

BASE_DIR = Path(__file__).parent
SHELL_TEMPLATES_DIR = BASE_DIR / "shell_templates"
SUBMODEL_TEMPLATES_DIR = BASE_DIR / "submodel_templates"


# ─────────────────────────────── helpers ──────────────────────────────────

def _ext_ref(url: str) -> model.ExternalReference:
    return model.ExternalReference(
        key=(model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE, value=url),)
    )


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _to_json(obj) -> dict:
    """Serialise a basyx model object to a plain dict via the JSON encoder."""
    return json.loads(json.dumps(obj, cls=basyx.aas.adapter.json.AASToJsonEncoder))


# ──────────────────────────── element builder ─────────────────────────────

def build_elements_from_form(
    builder: AASInstanceBuilder,
    parent,
    template_elements: list,
    form_data: dict,
) -> None:
    """Recursively build AAS submodel elements from a template + form data dict."""
    if not form_data:
        return

    for elem in template_elements:
        etype    = elem.get("type")
        id_short = elem.get("id_short")
        sem_id   = elem.get("semantic_id")
        val      = form_data.get(id_short)

        if etype == "property":
            if val is None or val == "":
                continue
            vt = XS_TYPE_MAP.get(elem.get("value_type", "xs:string"))
            if vt is None:
                continue
            el = builder.add_property(parent, id_short, vt, _convert_value(val, vt), sem_id)
            for q in elem.get("qualifiers", []):
                q_vt = XS_TYPE_MAP.get(q.get("value_type", "xs:string"))
                if q_vt:
                    builder.add_qualifier(
                        el, q["type"], q_vt,
                        _convert_value(q.get("value"), q_vt),
                        q.get("kind", "VALUE_QUALIFIER"),
                        q.get("semantic_id"),
                    )

        elif etype == "range":
            if not isinstance(val, dict):
                continue
            vt = XS_TYPE_MAP.get(elem.get("value_type", "xs:float"))
            if vt is None:
                continue
            builder.add_range(
                parent, id_short, vt,
                _convert_value(val.get("min"), vt),
                _convert_value(val.get("max"), vt),
                sem_id,
            )

        elif etype == "collection":
            if elem.get("extensible"):
                entries = val if isinstance(val, list) else []
                if not entries:
                    continue
                col = builder.add_collection(parent, id_short, sem_id)
                entry_template = elem.get("entry_template", "Entry{N}")
                child_elems = elem.get("elements", [])
                # Unwrap single non-extensible collection wrapper (e.g. BOMEntry inside
                # BOMEntries) so flat preset dicts map directly to the inner fields.
                if (len(child_elems) == 1
                        and child_elems[0].get("type") == "collection"
                        and not child_elems[0].get("extensible")):
                    child_elems = child_elems[0].get("elements", [])
                for i, entry in enumerate(entries):
                    entry_dict = entry if isinstance(entry, dict) else {}

                    def _fill(m, _d=entry_dict, _i=i):
                        token = m.group(1)
                        if token == "N":
                            return str(_i + 1)
                        val = _d.get(token)
                        if val is not None and str(val).strip():
                            return re.sub(r"[^A-Za-z0-9]", "_", str(val))
                        return str(_i + 1)

                    raw = re.sub(r"\{(\w+)\}", _fill, entry_template)
                    label = re.sub(r"_+", "_", raw).strip("_")
                    if not label or not label[0].isalpha():
                        label = f"Entry{i + 1}"
                    entry_col = builder.add_collection(col, label)
                    build_elements_from_form(
                        builder, entry_col, child_elems,
                        entry if isinstance(entry, dict) else {},
                    )
            else:
                if not isinstance(val, dict):
                    continue
                col = builder.add_collection(parent, id_short, sem_id)
                build_elements_from_form(builder, col, elem.get("elements", []), val)

        elif etype == "multi_language_property":
            if not val:
                continue
            if isinstance(val, list):
                mlp_val = {e["language"]: e["text"] for e in val
                           if e.get("language") and e.get("text")}
            elif isinstance(val, dict):
                mlp_val = val
            else:
                continue
            if not mlp_val:
                continue
            builder.add_multi_language_property(parent, id_short, value=mlp_val, semantic_id=sem_id)

        elif etype == "reference_element":
            cardinality = (elem.get("cardinality") or "One").lower()
            is_optional = cardinality in ("zerotoone", "zerotomany")
            if not val:
                if is_optional:
                    continue
                builder.add_reference_element(parent, id_short, value=None, semantic_id=sem_id)
                continue
            ref = _sm_ref(str(val)) if elem.get("reference_type") == "model" else _ext_ref(str(val))
            builder.add_reference_element(parent, id_short, value=ref, semantic_id=sem_id)

        elif etype == "list":
            if not isinstance(val, list) or not val:
                continue
            raw_et = elem.get("element_type", "property")

            if raw_et == "reference_element":
                lst = builder.add_list(parent, id_short, semantic_id=sem_id, element_type=model.ReferenceElement)
                for item in val:
                    if not isinstance(item, dict):
                        continue
                    sm_id = item.get("submodel_id", "")
                    path = item.get("path", [])
                    if not sm_id or not path:
                        continue
                    keys = [model.Key(type_=model.KeyTypes.SUBMODEL, value=sm_id)]
                    for segment in path:
                        keys.append(model.Key(
                            type_=model.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                            value=str(segment),
                        ))
                    ref = model.ModelReference(
                        key=tuple(keys),
                        type_=model.SubmodelElementCollection,
                    )
                    lst.value.append(model.ReferenceElement(id_short=None, value=ref))
                continue

            vt = XS_TYPE_MAP.get(elem.get("value_type", "xs:string"))
            if vt is None:
                continue
            element_cls = (
                model.SubmodelElementCollection
                if raw_et == "collection"
                else model.Property
            )
            lst = builder.add_list(parent, id_short, semantic_id=sem_id, element_type=element_cls, value_type=vt)
            for item in val:
                prop = model.Property(id_short=None, value_type=vt, value=_convert_value(item, vt))
                lst.value.append(prop)


# ───────────────────────────── submodel builder ───────────────────────────

def build_submodel(
    template_file: str,
    submodel_id: str,
    id_short: str,
    form_data: dict,
) -> model.Submodel:
    tmpl = _load_yaml(SUBMODEL_TEMPLATES_DIR / f"{template_file}.yaml")
    builder = AASInstanceBuilder(id_short, submodel_id)
    if desc := tmpl.get("description"):
        builder.submodel.description = model.MultiLanguageTextType({"en": desc})
    build_elements_from_form(builder, builder.get(), tmpl.get("elements", []), form_data or {})
    return builder.get()


# ────────────────────────────────── main ──────────────────────────────────

def main() -> None:
    payload = json.loads(sys.stdin.read())

    shell_type      = payload["shell_type"]
    name            = payload["name"]
    category        = payload["category"]
    shell_id        = payload["shell_id"]
    global_asset_id = payload["global_asset_id"]
    submodel_inputs = payload["submodels"]

    # Load shell YAML for description and id_short pattern; IDs come from the UI payload.
    shell_cfg = _load_yaml(SHELL_TEMPLATES_DIR / f"{shell_type}.yaml")
    id_short = name.replace(" ", "_")

    shell = model.AssetAdministrationShell(
        id_=shell_id,
        id_short=id_short,
        asset_information=model.AssetInformation(
            asset_kind=model.AssetKind.INSTANCE,
            global_asset_id=global_asset_id,
        ),
        submodel={_sm_ref(sm["id"]) for sm in submodel_inputs},
    )
    if desc := shell_cfg.get("description"):
        shell.description = model.MultiLanguageTextType({"en": desc})

    submodels = [
        build_submodel(
            sm["template_file"],
            sm["id"],
            sm["id_short"],
            sm.get("form_data", {}),
        )
        for sm in submodel_inputs
    ]

    env = {
        "assetAdministrationShells": [_to_json(shell)],
        "submodels": [_to_json(sm) for sm in submodels],
        "conceptDescriptions": [],
    }

    print(json.dumps(env, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
