"""
BaSyx Python SDK builders for AAS Type shells and submodels.

Converts the plain-dict type configurations (type_configs/*.py) into
basyx.aas model objects, then serialises each object to its own JSON file.

All submodels are created with kind=ModellingKind.TEMPLATE, which marks
them as type-level (template) definitions rather than instance-level data.
SubmodelElements (Property, SubmodelElementCollection, etc.) do not accept
a kind parameter in SDK 2.0.0 — kind is set on the Submodel only.

Requires: basyx-python-sdk >= 2.0.0
    pip install basyx-python-sdk
"""

import json
from pathlib import Path
from typing import Any, Optional

from basyx.aas import model
from basyx.aas.adapter.json import AASToJsonEncoder

# ─────────────────────────── constants ────────────────────────────────

BASE_NS = "https://aausmartlab.org"

# Used only on Submodel constructors — SubmodelElements do not accept kind.
TMPL = model.ModellingKind.TEMPLATE

# Map xs: type strings → basyx datatype classes.
XS_TYPE_MAP: dict[str, Any] = {
    # Text
    "xs:string":             model.datatypes.String,
    # Integers — use xs:int for 32-bit, xs:integer for arbitrary precision
    "xs:integer":            model.datatypes.Integer,
    "xs:int":                model.datatypes.Int,
    "xs:long":               model.datatypes.Long,
    "xs:short":              model.datatypes.Short,
    "xs:byte":               model.datatypes.Byte,
    "xs:nonNegativeInteger": model.datatypes.NonNegativeInteger,
    "xs:positiveInteger":    model.datatypes.PositiveInteger,
    # Floats
    "xs:double":             model.datatypes.Double,
    "xs:float":              model.datatypes.Float,
    # Boolean
    "xs:boolean":            model.datatypes.Boolean,
    # Date / time — values must be ISO 8601 strings, e.g. "2024-01-15"
    "xs:date":               model.datatypes.Date,
    "xs:dateTime":           model.datatypes.DateTime,
    "xs:time":               model.datatypes.Time,
    "xs:duration":           model.datatypes.Duration,
}

# ──────────────────────────── helpers ─────────────────────────────────

def _ext_ref(url: str) -> model.ExternalReference:
    """Create an ExternalReference (semantic ID) from a URL string."""
    return model.ExternalReference(
        key=(model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE, value=url),)
    )


def _sm_ref(sm_id: str) -> model.ModelReference:
    """Create a ModelReference pointing at a Submodel by its ID."""
    return model.ModelReference(
        key=(model.Key(type_=model.KeyTypes.SUBMODEL, value=sm_id),),
        type_=model.Submodel,
    )


def _shell_ref(shell_id: str) -> model.ModelReference:
    """Create a ModelReference pointing at an AssetAdministrationShell by its ID."""
    return model.ModelReference(
        key=(model.Key(type_=model.KeyTypes.ASSET_ADMINISTRATION_SHELL, value=shell_id),),
        type_=model.AssetAdministrationShell,
    )


def _lang(text: str, language: str = "en") -> model.MultiLanguageTextType:
    """Return a one-entry MultiLanguageTextType for description/display fields."""
    return model.MultiLanguageTextType({language: text})


def _convert_value(raw: Any, value_type: Any) -> Any:
    """
    Convert a raw config value (Python literal, YAML scalar, or None) to the
    exact datatype expected by the BaSyx SDK so that JSON serialisation
    produces the correct xs: representation.

    Covers all types in XS_TYPE_MAP:
        String, Integer, Int, Long, Short, Byte, NonNegativeInteger, PositiveInteger,
        Double, Float, Boolean, Date, DateTime
    """
    import datetime

    if raw is None or raw == "":
        return None

    # ── Text ──────────────────────────────────────────────────────────────
    if value_type == model.datatypes.String:
        return model.datatypes.String(raw)

    # ── Integers ──────────────────────────────────────────────────────────
    if value_type in (
        model.datatypes.Integer,
        model.datatypes.Int,
        model.datatypes.Long,
        model.datatypes.Short,
        model.datatypes.Byte,
        model.datatypes.NonNegativeInteger,
        model.datatypes.PositiveInteger,
    ):
        return value_type(int(raw))

    # ── Floats ────────────────────────────────────────────────────────────
    if value_type in (model.datatypes.Double, model.datatypes.Float):
        return value_type(float(raw))

    # ── Boolean ───────────────────────────────────────────────────────────
    if value_type == model.datatypes.Boolean:
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("true", "1", "yes")

    # ── Date / DateTime — expect ISO 8601 strings ("2024-01-15") ──────────
    if value_type == model.datatypes.Date:
        if isinstance(raw, datetime.date):
            return raw
        return datetime.date.fromisoformat(str(raw))

    if value_type == model.datatypes.DateTime:
        if isinstance(raw, datetime.datetime):
            return raw
        return datetime.datetime.fromisoformat(str(raw))

    # ── Duration — expect ISO 8601 duration string ("PT30S", "PT5M") ──────
    if value_type == model.datatypes.Duration:
        return model.datatypes._parse_xsd_duration(str(raw))

    # ── Time — expect ISO 8601 time string ("14:30:00") ───────────────────
    if value_type == model.datatypes.Time:
        if isinstance(raw, datetime.time):
            return raw
        return datetime.time.fromisoformat(str(raw))

    # ── Fallback ──────────────────────────────────────────────────────────
    return value_type(raw)


def _make_property(cfg: dict) -> model.Property:
    """Build a basyx.aas.model.Property from a property config dict."""
    vt = XS_TYPE_MAP.get(cfg.get("value_type", "xs:string"), model.datatypes.String)
    value = _convert_value(cfg.get("value"), vt)

    kwargs: dict[str, Any] = dict(
        id_short=cfg["id_short"],
        value_type=vt,
        value=value,
    )
    if cfg.get("unit_url"):
        kwargs["semantic_id"] = _ext_ref(cfg["unit_url"])
    if cfg.get("description"):
        kwargs["description"] = _lang(cfg["description"])
    return model.Property(**kwargs)


# ──────────────────── Documentation submodel ──────────────────────────

def build_documentation_submodel(type_url: str, cfg: dict) -> model.Submodel:
    """
    Build the Documentation submodel for a type.

    Contains:
      - Product_Name, Product_Type  (fixed strings from config)
      - Description                 (MultiLanguageProperty)
      - Model_Number_Configuration  (collection with template string)
      - Model_Number                (filled at instance creation)
      - Created_Date                (filled at instance creation)
    """
    elements: list[model.SubmodelElement] = [
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
    ]

    if "model_number_template" in cfg:
        elements.append(
            model.SubmodelElementCollection(
                id_short="Model_Number_Configuration",
                description=_lang(
                    "Configurator directive: defines how Model_Number is generated "
                    "at instance creation. Removed from instances."
                ),
                value=[
                    model.Property(
                        id_short="Template",
                        value_type=model.datatypes.String,
                        value=model.datatypes.String(cfg["model_number_template"]),
                        description=_lang(
                            "{key} placeholders are replaced with values from "
                            "the order configuration"
                        ),
                    )
                ],
            )
        )

    elements += [
        model.Property(
            id_short="Model_Number",
            value_type=model.datatypes.String,
            value=None,
            description=_lang("Filled at instance creation"),
        ),
        model.Property(
            id_short="Created_Date",
            value_type=model.datatypes.String,
            value=None,
            description=_lang("Date the instance was created (YYYY-MM-DD)"),
        ),
    ]

    return model.Submodel(
        id_=f"{type_url}/Documentation",
        id_short="Documentation",
        kind=TMPL,
        semantic_id=_ext_ref(f"{BASE_NS}/Data/Documentation"),
        description=_lang(f"Documentation for {cfg['name']} type"),
        submodel_element=elements,
    )


# ──────────────────── Properties submodel ─────────────────────────────

def build_properties_submodel(type_url: str, cfg: dict) -> model.Submodel:
    """
    Build the Properties submodel for a type.

    All properties are wrapped in a single SubmodelElementCollection
    named 'List_Of_Properties', preserving the existing structure and
    allowing named lookup by id_short.
    """
    props = [_make_property(p) for p in cfg.get("properties", [])]

    collection = model.SubmodelElementCollection(
        id_short="List_Of_Properties",
        semantic_id=_ext_ref(f"{BASE_NS}/Submodels/List_Of_Properties"),
        description=_lang(f"Properties for {cfg['name']}"),
        value=props,
    )

    return model.Submodel(
        id_=f"{type_url}/Properties",
        id_short="Properties",
        kind=TMPL,
        semantic_id=_ext_ref(f"{BASE_NS}/Data/Parts/Variants"),
        description=_lang(f"Property structure definition for {cfg['name']} type"),
        submodel_element=[collection],
    )


# ───────────────────── Bill of Materials submodel ─────────────────────

def build_bom_submodel(
    type_url: str,
    cfg: dict,
    include_instance_ref: bool = True,
) -> model.Submodel:
    """
    Build the Bill of Materials submodel for a type.

    Uses SubmodelElementCollection for the Components container so that
    each component entry keeps its id_short for named lookup.

    Args:
        include_instance_ref: Set True for sub-assemblies (instance ref is
            filled during production); False for final products.
    """
    component_collections: list[model.SubmodelElementCollection] = []

    for comp in cfg.get("bom_components", []):
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
        ]

        if "qty_default" in comp:
            comp_props.append(
                model.Property(
                    id_short="Quantity_Default",
                    value_type=model.datatypes.Integer,
                    value=model.datatypes.Integer(comp["qty_default"]),
                )
            )

        conf_kwargs: dict[str, Any] = dict(
            id_short="Is_Configurable",
            value_type=model.datatypes.Boolean,
            value=bool(comp.get("is_configurable", False)),
        )
        if comp.get("is_configurable_note"):
            conf_kwargs["description"] = _lang(comp["is_configurable_note"])
        comp_props.append(model.Property(**conf_kwargs))

        if include_instance_ref:
            comp_props.append(
                model.Property(
                    id_short="Instance_Refference",
                    value_type=model.datatypes.String,
                    value=None,
                    description=_lang(
                        "AAS ID of the physical instance used during assembly. "
                        "Filled during production."
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
        component_collections.append(model.SubmodelElementCollection(**sec_kwargs))

    components = model.SubmodelElementCollection(
        id_short="Components",
        semantic_id=_ext_ref(f"{BASE_NS}/Submodels/BOM/Components"),
        description=_lang("Components and sub-assemblies required"),
        value=component_collections,
    )

    return model.Submodel(
        id_=f"{type_url}/Bill_Of_Materials",
        id_short="Bill_Of_Materials",
        kind=TMPL,
        semantic_id=_ext_ref(f"{BASE_NS}/Data/BOM"),
        description=_lang(f"Bill of Materials structure for {cfg['name']}"),
        submodel_element=[components],
    )


# ───────────────────── Bill of Processes submodel ─────────────────────

def build_bop_submodel(type_url: str, cfg: dict) -> model.Submodel:
    """
    Build the Bill of Processes submodel for a type.

    Each process step becomes a SubmodelElementCollection containing:
      - Process_Constraints  – prerequisite step IDs
      - Required_Components  – component IDs needed by this step
      - Parameters           – Selected_Operation and any extra params
    """
    step_collections: list[model.SubmodelElementCollection] = []

    for step in cfg.get("bop_steps", []):
        # Process_Constraints
        constraints = step.get("constraints", [])
        constraint_props = [
            model.Property(
                id_short=f"Constraint_Id_{i + 1}",
                value_type=model.datatypes.String,
                value=model.datatypes.String(c),
            )
            for i, c in enumerate(constraints)
        ]
        if not constraint_props:
            constraint_props = [
                model.Property(
                    id_short="Constraint_Id_1",
                    value_type=model.datatypes.String,
                    value=None,
                )
            ]

        # Required_Components
        required_props = [
            model.Property(
                id_short=f"Component_Id_{i + 1}",
                value_type=model.datatypes.String,
                value=model.datatypes.String(c),
            )
            for i, c in enumerate(step.get("required_components", []))
        ]

        # Parameters
        param_props = [
            model.Property(
                id_short="Selected_Operation",
                value_type=model.datatypes.String,
                value=model.datatypes.String(step.get("operation", "")),
            )
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
                        value=param_props,
                    ),
                ],
            )
        )

    
    return model.Submodel(
        id_=f"{type_url}/Bill_Of_Processes",
        id_short="Bill_Of_Processes",
        kind=TMPL,
        semantic_id=_ext_ref(f"{BASE_NS}/Data/BillOfOperations"),
        description=_lang(
            "List of manufacturing and assembly operations for the product."
        ),
        submodel_element=step_collections,
    )


# ───────────────────────── AAS Shell builder ──────────────────────────

def build_type_shell(
    type_id: str,
    id_short: str,
    global_asset_id: str,
    submodel_ids: list[str],
) -> model.AssetAdministrationShell:
    """Build an AAS Type shell with ModelReferences to its submodels."""
    return model.AssetAdministrationShell(
        id_=type_id,
        id_short=id_short,
        asset_information=model.AssetInformation(
            asset_kind=model.AssetKind.TYPE,
            global_asset_id=global_asset_id,
        ),
        submodel={_sm_ref(sm_id) for sm_id in submodel_ids},
    )


# ─────────────────────── URL / ID helpers ─────────────────────────────

def type_url_component(name: str, category: str = "") -> str:
    return f"{BASE_NS}/Shells/Component/{name}"


def type_url_sub_assembly(asset_type: str, asset_name: str, category: str = "") -> str:
    return f"{BASE_NS}/Shells/Assembly/{asset_type}/{asset_name}"


def type_url_final_product(asset_type: str, asset_name: str, family: str = "") -> str:
    return f"{BASE_NS}/Shells/Configuration/{asset_type}/{asset_name}"


def global_asset_id(name: str) -> str:
    """Canonical global asset ID — same as the shell ID for this asset."""
    return f"{BASE_NS}/Shells/Component/{name}"


def safe_id_short(name: str, suffix: str = "_Type") -> str:
    """Convert a name with hyphens to a valid AAS idShort."""
    return name.replace("-", "_") + suffix


# ────────────────────────── I/O helpers ───────────────────────────────

def write_json(obj: model.Referable, path: Path) -> None:
    """
    Serialise a single AAS object (shell or submodel) to a JSON file
    using the BaSyx AASToJsonEncoder.

    The output format is AAS v3 compliant and accepted by any BaSyx
    REST server via POST /shells or POST /submodels.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, cls=AASToJsonEncoder, indent=2, ensure_ascii=False)
    print(f"  Written: {path}")
