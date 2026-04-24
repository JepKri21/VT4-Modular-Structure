"""
Load an AAS submodel instance from a YAML file and save/upload it.

Usage:
    python yaml_to_instance.py <input.yaml>
    python yaml_to_instance.py <input.yaml> --output out.json
    python yaml_to_instance.py <input.yaml> --upload http://localhost:8081
    python yaml_to_instance.py <input.yaml> --output out.json --upload http://localhost:8081

YAML format reference:
    id_short: "DrillingCapability"
    id: "https://aausmartlab.org/SubmodelInstance/Capability/Drilling/DrillingStation1"
    description: "Optional description"

    elements:
      - type: property
        id_short: "BitDiameter_mm"
        value_type: "xs:float"
        value: 5.0
        semantic_id: "https://..."               # optional on all elements
        qualifiers:                              # optional on all elements
          - type: "range_min"
            value_type: "xs:float"
            value: 1.0
            kind: "VALUE_QUALIFIER"              # VALUE_QUALIFIER (default) | CONCEPT_QUALIFIER | INSTANCE_QUALIFIER

      - type: range
        id_short: "DrillDepth_mm"
        value_type: "xs:float"
        min: 0.0
        max: 200.0

      - type: multi_language_property
        id_short: "OperationLabel"
        value:
          en: "Drilling Operation"
          de: "Bohrvorgang"

      - type: reference_element
        id_short: "ResourceReference"
        value: "https://some-resource-url"        # ExternalReference string

      - type: collection
        id_short: "DrillingParameters"
        elements:                                 # nested elements — same schema
          - type: property
            id_short: "BitSize"
            value_type: "xs:int"
            value: 5

      - type: list
        id_short: "SupportedComponents"
        element_type: "property"                 # property | collection
        value_type: "xs:string"                  # required when element_type is property
        items:                                   # list of scalar values
          - "Bottom Cover"
          - "Top Cover"
"""

import argparse
import json
import sys
from pathlib import Path

import yaml
from basyx.aas import model

sys.path.insert(0, str(Path(__file__).parent))

from builders import XS_TYPE_MAP, _convert_value
from instance_generator_class import AASInstanceBuilder

_HERE = Path(__file__).parent
SUBMODELS = [
    _HERE / "../Instance_Examples/Drilling_Station/drilling_capability_offered.yaml",
    _HERE / "../Instance_Examples/Drilling_Station/drilling_skills.yaml",
    _HERE / "../Instance_Examples/Drilling_Station/HandoffCapabilityOffered.yaml",
    _HERE / "../Instance_Examples/Drilling_Station/drilling_station_resource_zones.yaml",
    _HERE / "../Instance_Examples/Storage_Station/Inventory.yaml",
    _HERE / "../Instance_Examples/Storage_Station/HandoffCapabilityOffered.yaml",
    _HERE / "../Instance_Examples/Storage_Station/RetrieveCapabilityOffered.yaml",
    _HERE / "../Instance_Examples/Storage_Station/StoreCapbilityOffered.yaml",
    _HERE / "../Instance_Examples/Storage_Station/Skills.yaml",
    _HERE / "../Instance_Examples/Storage_Station/ResourceZones.yaml",
    _HERE / "../Instance_Examples/Transport_Station/transport_skills.yaml",
    _HERE / "../Instance_Examples/Transport_Station/TransportCapabilityOffered.yaml",
    _HERE / "../Instance_Examples/Transport_Station/ResourceZones.yaml",
]

import basyx.aas.adapter.json

ELEMENT_TYPE_MAP: dict = {
    "property":                model.Property,
    "range":                   model.Range,
    "collection":              model.SubmodelElementCollection,
    "multi_language_property": model.MultiLanguageProperty,
    "reference_element":       model.ReferenceElement,
}


def _apply_qualifiers(builder: AASInstanceBuilder, element, qualifiers: list) -> None:
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
            value=_convert_value(q.get("value"), vt),
            kind=q.get("kind", "VALUE_QUALIFIER"),
            semantic_id=q.get("semantic_id"),
        )


def _make_ref(value):
    """Build an ExternalReference or ModelReference from a YAML value field."""
    if value is None:
        return None
    if isinstance(value, str):
        return model.ExternalReference(
            key=(model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE, value=value),)
        )
    if isinstance(value, dict):
        keys = tuple(
            model.Key(type_=model.KeyTypes[k["type"].upper()], value=k["value"])
            for k in value.get("keys", [])
        )
        return model.ModelReference(keys=keys, type_=model.Submodel)
    raise ValueError(f"Unsupported reference_element value format: {value!r}")


def _build_elements(builder: AASInstanceBuilder, parent, elements: list) -> None:
    for elem in (elements or []):
        etype       = elem["type"]
        id_short    = elem["id_short"]
        semantic_id = elem.get("semantic_id")

        if etype == "property":
            vt = XS_TYPE_MAP.get(elem["value_type"])
            if vt is None:
                raise ValueError(f"Unknown value_type '{elem['value_type']}' for element '{id_short}'")
            el = builder.add_property(
                parent, id_short, vt,
                value=_convert_value(elem.get("value"), vt),
                semantic_id=semantic_id,
            )

        elif etype == "range":
            vt = XS_TYPE_MAP.get(elem["value_type"])
            if vt is None:
                raise ValueError(f"Unknown value_type '{elem['value_type']}' for element '{id_short}'")
            el = builder.add_range(
                parent, id_short, vt,
                min_value=_convert_value(elem.get("min"), vt),
                max_value=_convert_value(elem.get("max"), vt),
                semantic_id=semantic_id,
            )

        elif etype == "multi_language_property":
            el = builder.add_multi_language_property(
                parent, id_short,
                value=elem.get("value"),
                semantic_id=semantic_id,
                description=elem.get("description"),
            )

        elif etype == "reference_element":
            el = builder.add_reference_element(
                parent, id_short,
                value=_make_ref(elem.get("value")),
                semantic_id=semantic_id,
                description=elem.get("description"),
            )

        elif etype == "collection":
            el = builder.add_collection(parent, id_short, semantic_id=semantic_id)
            _build_elements(builder, el, elem.get("elements") or [])

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
            elif raw_et == "property":
                raise ValueError(f"'value_type' is required for list '{id_short}' when element_type is 'property'")
            el = builder.add_list(parent, id_short, semantic_id=semantic_id, element_type=element_cls, value_type=vt)
            for item in elem.get("items", []):
                prop = model.Property(id_short=None, value_type=vt, value=_convert_value(item, vt))
                el.value.append(prop)

        else:
            raise ValueError(f"Unknown element type '{etype}' for element '{id_short}'")

        if qualifiers := elem.get("qualifiers"):
            _apply_qualifiers(builder, el, qualifiers)


def load_instance_from_yaml(path: str) -> AASInstanceBuilder:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    id_short = cfg.get("id_short")
    id_      = cfg.get("id")
    if not id_short or not id_:
        raise KeyError("YAML must have both 'id_short' and 'id' at the top level")

    builder = AASInstanceBuilder(id_short, id_)

    if desc := cfg.get("description"):
        builder.submodel.description = model.MultiLanguageTextType({"en": desc})

    _build_elements(builder, builder.get(), cfg.get("elements") or [])
    return builder


def _upload_submodel(json_str: str, submodel_id: str, url: str) -> None:
    import base64
    import requests
    headers = {"Content-Type": "application/json"}
    response = requests.post(f"{url}/submodels", headers=headers, data=json_str.encode("utf-8"))
    if response.status_code in (200, 201):
        print("Submodel uploaded successfully!")
    elif response.status_code == 409:
        encoded_id = base64.urlsafe_b64encode(submodel_id.encode("utf-8")).decode("ascii")
        response = requests.put(f"{url}/submodels/{encoded_id}", headers=headers, data=json_str.encode("utf-8"))
        if response.status_code in (200, 201, 204):
            print("Submodel updated successfully (PUT)!")
        else:
            print(f"Upload failed on PUT: {response.status_code} - {response.text}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Upload failed: {response.status_code} - {response.text}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an AAS submodel instance from one or more YAML files.")
    parser.add_argument("yaml_file", nargs="*", help="Path(s) to YAML instance definition(s); omit to use built-in SUBMODELS list")
    parser.add_argument("--output", "-o", help="Write JSON to this file (single file only; ignored for multiple inputs)")
    parser.add_argument("--upload", "-u", metavar="URL", help="POST JSON to <URL>/submodels")
    args = parser.parse_args()

    files = [str(p) for p in args.yaml_file] if args.yaml_file else [str(p) for p in SUBMODELS]
    multi = len(files) > 1

    for yaml_path in files:
        if multi:
            print(f"\n--- {yaml_path} ---")
        try:
            builder = load_instance_from_yaml(yaml_path)
        except (KeyError, ValueError, FileNotFoundError) as exc:
            print(f"Error ({yaml_path}): {exc}", file=sys.stderr)
            sys.exit(1)

        json_str = json.dumps(builder.get(), cls=basyx.aas.adapter.json.AASToJsonEncoder, indent=2, ensure_ascii=False)

        if args.output and not multi:
            Path(args.output).write_text(json_str, encoding="utf-8")
            print(f"Written to {args.output}")
        else:
            print(json_str)

        if args.upload:
            _upload_submodel(json_str, builder.get().id, args.upload.rstrip("/"))


if __name__ == "__main__":
    main()
