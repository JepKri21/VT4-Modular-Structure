"""
Load an AAS submodel template from a YAML file and save/upload it.

Usage:
    python yaml_to_template.py <input.yaml>
    python yaml_to_template.py <input.yaml> --output out.json
    python yaml_to_template.py <input.yaml> --upload http://localhost:8081
    python yaml_to_template.py <input.yaml> --output out.json --upload http://localhost:8081

YAML format reference:
    id_short: "MySubmodel"
    id: "https://example.com/SubmodelTemplate/MySubmodel/1/0"
    description: "Optional description"          # optional

    elements:
      - type: property
        id_short: "MyProp"
        value_type: "xs:string"                  # required for property / range
        semantic_id: "https://..."               # optional on all elements
        description: "..."                       # optional on all elements
        cardinality: "One"                       # One | ZeroToOne | ZeroToMany | OneToMany
        qualifiers:                              # optional on all elements
          - type: "range_min"
            value_type: "xs:float"
            value: 1.0
            kind: "TEMPLATE_QUALIFIER"           # TEMPLATE_QUALIFIER (default) | CONCEPT_QUALIFIER | VALUE_QUALIFIER
            semantic_id: "https://..."           # optional

      - type: range
        id_short: "MyRange"
        value_type: "xs:float"
        cardinality: "ZeroToOne"

      - type: multi_language_property
        id_short: "MyMLP"
        cardinality: "ZeroToOne"

      - type: reference_element
        id_short: "MyRef"
        cardinality: "ZeroToOne"

      - type: collection
        id_short: "MyCollection"
        cardinality: "One"
        extensible: true                       # optional — marks collection as extensible;
        entry_template: "Entry{N}Parameters"  # optional name hint for additional entries
        elements:                               # nested elements — same schema
          - type: property
            id_short: "Nested"
            value_type: "xs:int"

      - type: list
        id_short: "MyList"
        element_type: "property"               # property | range | collection |
                                               # multi_language_property | reference_element
        value_type: "xs:string"                # required when element_type is property or range (AASd-109)
        cardinality: "ZeroToMany"

Cardinality defaults: property→One, collection→One, range→ZeroToOne,
                      multi_language_property→ZeroToOne, reference_element→ZeroToOne,
                      list→ZeroToMany
"""

import argparse
import json
import sys
from pathlib import Path

import yaml
from basyx.aas import model

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "type_configs"))

from builders import XS_TYPE_MAP, _convert_value
from template_generator_class import AASTemplateBuilder

import basyx.aas.adapter.json

ELEMENT_TYPE_MAP: dict = {
    "property":                model.Property,
    "range":                   model.Range,
    "collection":              model.SubmodelElementCollection,
    "multi_language_property": model.MultiLanguageProperty,
    "reference_element":       model.ReferenceElement,
}

CARDINALITY_DEFAULTS: dict = {
    "property":                "One",
    "collection":              "One",
    "range":                   "ZeroToOne",
    "multi_language_property": "ZeroToOne",
    "reference_element":       "ZeroToOne",
    "list":                    "ZeroToMany",
}


def _apply_qualifiers(builder: AASTemplateBuilder, element, qualifiers: list) -> None:
    for q in qualifiers:
        q_type = q.get("type")
        if not q_type:
            raise ValueError("Each qualifier must have a 'type' field")
        vt_str = q.get("value_type")
        if not vt_str:
            raise ValueError(f"Qualifier '{q_type}' must have a 'value_type' field")
        vt = XS_TYPE_MAP.get(vt_str)
        if vt is None:
            raise ValueError(f"Unknown value_type '{vt_str}' in qualifier '{q_type}'")
        builder.add_qualifier(
            element,
            type_=q_type,
            value_type=vt,
            value=_convert_value(q.get("value"), vt),  # cast to correct BaSyx type
            kind=q.get("kind", "TEMPLATE_QUALIFIER"),
            semantic_id=q.get("semantic_id"),
        )


def _build_elements(builder: AASTemplateBuilder, parent, elements: list) -> None:
    for elem in elements:
        etype       = elem["type"]
        id_short    = elem["id_short"]
        semantic_id = elem.get("semantic_id")
        description = elem.get("description")
        cardinality = elem.get("cardinality", CARDINALITY_DEFAULTS[etype])

        if etype == "property":
            vt = XS_TYPE_MAP.get(elem["value_type"])
            if vt is None:
                raise ValueError(f"Unknown value_type '{elem['value_type']}' for element '{id_short}'")
            el = builder.add_property(parent, id_short, vt, semantic_id, cardinality)

        elif etype == "range":
            vt = XS_TYPE_MAP.get(elem["value_type"])
            if vt is None:
                raise ValueError(f"Unknown value_type '{elem['value_type']}' for element '{id_short}'")
            el = builder.add_range(parent, id_short, vt, semantic_id, cardinality)

        elif etype == "multi_language_property":
            el = builder.add_multi_language_property(parent, id_short, semantic_id, description, cardinality)

        elif etype == "reference_element":
            el = builder.add_reference_element(parent, id_short, semantic_id, description, cardinality)

        elif etype == "collection":
            el = builder.add_collection(parent, id_short, semantic_id, cardinality)
            if elem.get("extensible"):
                entry_template = elem.get("entry_template", "")
                builder.add_qualifier(el, type_="Extensible", value_type=model.datatypes.String,
                                      value=entry_template or "true", kind="TEMPLATE_QUALIFIER")
            _build_elements(builder, el, elem.get("elements", []))

        elif etype == "list":
            raw_et = elem.get("element_type")
            if raw_et is None:
                raise ValueError(f"'element_type' is required for list element '{id_short}'")
            element_cls = ELEMENT_TYPE_MAP.get(raw_et)
            if element_cls is None:
                raise ValueError(f"Unknown element_type '{raw_et}' for list '{id_short}'")
            vt = None
            if raw_vt := elem.get("value_type"):
                vt = XS_TYPE_MAP.get(raw_vt)
                if vt is None:
                    raise ValueError(f"Unknown value_type '{raw_vt}' for list '{id_short}'")
            elif raw_et in ("property", "range"):
                raise ValueError(
                    f"'value_type' is required for list '{id_short}' when element_type is '{raw_et}' (AASd-109)"
                )
            el = builder.add_list(parent, id_short, semantic_id, element_cls, cardinality, vt)

        else:
            raise ValueError(f"Unknown element type '{etype}' for element '{id_short}'")

        if qualifiers := elem.get("qualifiers"):
            _apply_qualifiers(builder, el, qualifiers)


def load_template_from_yaml(path: str) -> AASTemplateBuilder:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    id_short = cfg.get("id_short")
    id_      = cfg.get("id")
    if not id_short or not id_:
        raise KeyError("YAML must have both 'id_short' and 'id' at the top level")

    builder = AASTemplateBuilder(id_short, id_)

    if desc := cfg.get("description"):
        builder.submodel.description = model.MultiLanguageTextType({"en": desc})

    _build_elements(builder, builder.get(), cfg.get("elements", []))
    return builder


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an AAS submodel template from a YAML file.")
    parser.add_argument("yaml_file", help="Path to the YAML template definition")
    parser.add_argument("--output", "-o", help="Write JSON to this file (default: stdout)")
    parser.add_argument("--upload", "-u", metavar="URL", help="POST JSON to <URL>/submodels")
    args = parser.parse_args()

    try:
        builder = load_template_from_yaml(args.yaml_file)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    json_str = json.dumps(builder.get(), cls=basyx.aas.adapter.json.AASToJsonEncoder, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(json_str, encoding="utf-8")
        print(f"Written to {args.output}")
    else:
        print(json_str)

    if args.upload:
        import requests
        url = args.upload.rstrip("/")
        response = requests.post(
            f"{url}/submodels",
            headers={"Content-Type": "application/json"},
            data=json_str.encode("utf-8"),
        )
        if response.status_code in (200, 201):
            print("Submodel uploaded successfully!")
        else:
            print(f"Upload failed: {response.status_code} - {response.text}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()



