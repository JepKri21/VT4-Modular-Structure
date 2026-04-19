"""
AASTemplateBuilder — fluent builder for BaSyx AAS submodel templates.

All submodels created by this class use ModellingKind.TEMPLATE, meaning they
describe the *structure* of a submodel (what elements it must/may contain) rather
than holding actual instance data.  Instance creation is a separate step.

Typical usage (Python):
    builder = AASTemplateBuilder("MySubmodel", "https://example.com/MySubmodel/1/0")
    root = builder.get()

    params = builder.add_collection(root, "Parameters", cardinality="One")
    builder.add_property(params, "Speed", model.datatypes.Float,
                         semantic_id="https://example.com/Sem/Speed")
    builder.add_range(params, "Temperature", model.datatypes.Float,
                      cardinality="ZeroToOne")

    builder.save_json("output/MySubmodel.json")

Typical usage (YAML — see yaml_to_template.py):
    python yaml_to_template.py submodel_templates/my_submodel.yaml --output out.json

Cardinality values (AAS SMT standard):
    "One"        — exactly one instance required
    "ZeroToOne"  — optional, at most one
    "ZeroToMany" — optional, any number
    "OneToMany"  — at least one required

Qualifier kinds:
    "TEMPLATE_QUALIFIER" — constrains the template structure (default for add_qualifier)
    "CONCEPT_QUALIFIER"  — further qualifies the semantics of an element
    "VALUE_QUALIFIER"    — constrains the value of an element at instance level
"""

import json

import basyx.aas.adapter.json
from basyx.aas import model
from basyx.aas.model import (
    Submodel,
    Property,
    Range,
    SubmodelElementCollection,
    SubmodelElementList,
    MultiLanguageProperty,
    ReferenceElement,
    Qualifier,
    Key,
    ModelReference,
    KeyTypes,
    ExternalReference,
)


class AASTemplateBuilder:
    """Builds a single AAS submodel template incrementally.

    Instantiate once per submodel, then call add_* methods to attach elements.
    Every element automatically receives a cardinality qualifier so instance
    creators know which elements are mandatory vs optional.

    All add_* methods return the created element so it can be passed back as
    'parent' to nest further elements inside it.
    """

    # Semantic ID for the SMT cardinality qualifier — defined by the AAS standard.
    CARDINALITY_IRI = "https://admin-shell.io/SubmodelTemplates/Cardinality/1/0"

    def __init__(self, id_short: str, identification: str):
        """Create a new template submodel.

        Args:
            id_short:       Short identifier used inside the AAS (no spaces).
            identification: Globally unique IRI for this submodel template,
                            e.g. "https://example.com/SubmodelTemplate/Name/1/0".
        """
        self.submodel = Submodel(
            id_short=id_short,
            id_=identification,
            kind=model.ModellingKind.TEMPLATE  # always TEMPLATE — never INSTANCE
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_container(self, parent):
        """Return the mutable element set of a Submodel or collection."""
        if isinstance(parent, Submodel):
            return parent.submodel_element
        return parent.value  # SubmodelElementCollection / SubmodelElementList

    def _cardinality(self, value: str) -> Qualifier:
        """Build the standard SMT/Cardinality TEMPLATE_QUALIFIER."""
        return Qualifier(
            type_="SMT/Cardinality",
            value_type=model.datatypes.String,
            value=value,
            kind=model.QualifierKind.TEMPLATE_QUALIFIER,
            semantic_id=ExternalReference(
                key=(
                    Key(
                        type_=KeyTypes.GLOBAL_REFERENCE,
                        value=self.CARDINALITY_IRI
                    ),
                )
            )
        )

    # ------------------------------------------------------------------
    # Element builders
    # ------------------------------------------------------------------

    def add_property(
        self,
        parent,
        id_short: str,
        value_type,
        semantic_id: str | None = None,
        cardinality: str = "One",
    ):
        """Add a typed Property to parent.

        Args:
            parent:      The submodel root (builder.get()) or a collection returned
                         by add_collection().
            id_short:    Element identifier.
            value_type:  BaSyx datatype, e.g. model.datatypes.String,
                         model.datatypes.Float, model.datatypes.Int.
            semantic_id: Optional IRI linking to a semantic definition (ECLASS, IEC, ...).
            cardinality: How many times this element may/must appear in an instance.
                         Default "One" (required, exactly once).

        Returns:
            The created Property (pass to add_qualifier if needed).

        Example:
            builder.add_property(root, "SerialNumber", model.datatypes.String,
                                  semantic_id="https://example.com/Sem/SerialNumber")
        """
        prop = Property(
            id_short=id_short,
            value_type=value_type
        )
        if semantic_id:
            prop.semantic_id = ExternalReference(
                key=(Key(type_=KeyTypes.GLOBAL_REFERENCE, value=semantic_id),)
            )
        prop.qualifier.add(self._cardinality(cardinality))
        self._get_container(parent).add(prop)
        return prop

    def add_range(
        self,
        parent,
        id_short: str,
        value_type,
        semantic_id: str | None = None,
        cardinality: str = "ZeroToOne",
    ):
        """Add a Range element (min/max pair) to parent.

        Use this when the template should express that instances must provide
        both a minimum and a maximum value, e.g. for drill depth or temperature.

        Args:
            value_type:  Must be a numeric type (Float, Double, Int, Integer).
            cardinality: Default "ZeroToOne" (optional, at most once).

        Returns:
            The created Range.

        Example:
            builder.add_range(params, "DrillDepth_mm", model.datatypes.Float,
                               semantic_id="https://example.com/Sem/DrillDepth")
        """
        rng = Range(
            id_short=id_short,
            value_type=value_type
        )
        if semantic_id:
            rng.semantic_id = ExternalReference(
                key=(Key(type_=KeyTypes.GLOBAL_REFERENCE, value=semantic_id),)
            )
        rng.qualifier.add(self._cardinality(cardinality))
        self._get_container(parent).add(rng)
        return rng

    def add_collection(
        self,
        parent,
        id_short: str,
        semantic_id: str | None = None,
        cardinality: str = "One",
    ):
        """Add a SubmodelElementCollection to parent and return it.

        A collection is an ordered, named group of heterogeneous elements.
        Pass the returned collection as 'parent' to nest elements inside it.

        Args:
            cardinality: Default "One" (the collection is required).

        Returns:
            The created SubmodelElementCollection.

        Example:
            params = builder.add_collection(root, "DrillingParameters",
                                             semantic_id="https://example.com/Sem/DrillParams")
            builder.add_property(params, "BitSize", model.datatypes.Int)
        """
        col = SubmodelElementCollection(id_short=id_short)
        if semantic_id:
            col.semantic_id = ExternalReference(
                key=(Key(type_=KeyTypes.GLOBAL_REFERENCE, value=semantic_id),)
            )
        col.qualifier.add(self._cardinality(cardinality))
        self._get_container(parent).add(col)
        return col

    def add_list(
        self,
        parent,
        id_short: str,
        semantic_id: str | None = None,
        element_type: type = model.Property,
        cardinality: str = "ZeroToMany",
    ):
        """Add a SubmodelElementList to parent.

        A list holds an ordered sequence of elements of the *same* type
        (unlike a collection, which can mix types).  Elements inside the list
        have no id_short — they are identified by their index.

        Args:
            element_type: The BaSyx class of items in the list, e.g.
                          model.Property, model.SubmodelElementCollection.
            cardinality:  Default "ZeroToMany" (optional, any number of items).

        Returns:
            The created SubmodelElementList.

        Example:
            builder.add_list(root, "SupportedComponents",
                              element_type=model.Property,
                              cardinality="ZeroToMany")
        """
        lst = SubmodelElementList(
            id_short=id_short,
            type_value_list_element=element_type
        )
        if semantic_id:
            lst.semantic_id = ExternalReference(
                key=(Key(type_=KeyTypes.GLOBAL_REFERENCE, value=semantic_id),)
            )
        lst.qualifier.add(self._cardinality(cardinality))
        self._get_container(parent).add(lst)
        return lst

    def add_multi_language_property(
        self,
        parent,
        id_short: str,
        semantic_id: str | None = None,
        description: str | None = None,
        cardinality: str = "ZeroToOne",
    ):
        """Add a MultiLanguageProperty to parent.

        Use this for text fields that should be provided in multiple languages
        at instance level (e.g. a human-readable label or description field).

        Args:
            description: English description of what this field represents
                         (stored as element metadata, not the property value).
            cardinality: Default "ZeroToOne" (optional).

        Returns:
            The created MultiLanguageProperty.

        Example:
            builder.add_multi_language_property(root, "OperationLabel",
                                                 description="Human-readable label")
        """
        mlp = MultiLanguageProperty(
            id_short=id_short,
            description=model.MultiLanguageTextType({"en": description}) if description else None,
        )
        if semantic_id:
            mlp.semantic_id = ExternalReference(
                key=(Key(type_=KeyTypes.GLOBAL_REFERENCE, value=semantic_id),)
            )
        mlp.qualifier.add(self._cardinality(cardinality))
        self._get_container(parent).add(mlp)
        return mlp

    def add_reference_element(
        self,
        parent,
        id_short: str,
        semantic_id: str | None = None,
        description: str | None = None,
        cardinality: str = "ZeroToOne",
    ):
        """Add a ReferenceElement to parent.

        Use this when an instance should store a reference to another AAS
        element or external resource (e.g. a link to the physical resource
        that realises this capability).

        The value is left None in the template; it is filled at instance creation.

        Args:
            cardinality: Default "ZeroToOne" (optional).

        Returns:
            The created ReferenceElement.

        Example:
            builder.add_reference_element(root, "ResourceReference",
                                           description="Physical resource for this capability")
        """
        ref = ReferenceElement(
            id_short=id_short,
            value=None,  # filled at instance creation
            description=model.MultiLanguageTextType({"en": description}) if description else None,
        )
        if semantic_id:
            ref.semantic_id = ExternalReference(
                key=(Key(type_=KeyTypes.GLOBAL_REFERENCE, value=semantic_id),)
            )
        ref.qualifier.add(self._cardinality(cardinality))
        self._get_container(parent).add(ref)
        return ref

    def add_qualifier(
        self,
        element,
        type_: str,
        value_type,
        value=None,
        kind: str = "TEMPLATE_QUALIFIER",
        semantic_id: str | None = None,
    ) -> Qualifier:
        """Attach an additional qualifier to any element.

        Qualifiers provide extra metadata or constraints on an element beyond
        the cardinality that is added automatically.  Common uses:

        - range_min / range_max  — constrain the allowed value range of a Property
        - allowed_values         — list permitted enumeration values

        Args:
            element:    The element returned by any add_* method.
            type_:      Free-form qualifier name string, e.g. "range_min".
            value_type: BaSyx datatype for the qualifier value.
            value:      The qualifier value itself (optional).
            kind:       "TEMPLATE_QUALIFIER" (default) — constrains the template.
                        "VALUE_QUALIFIER"    — constrains instance values.
                        "CONCEPT_QUALIFIER"  — adds semantic meaning.
            semantic_id: Optional IRI for the qualifier's semantic definition.

        Returns:
            The created Qualifier.

        Example:
            prop = builder.add_property(params, "BitDiameter_mm", model.datatypes.Float)
            builder.add_qualifier(prop, "range_min", model.datatypes.Float, value=1.0)
            builder.add_qualifier(prop, "range_max", model.datatypes.Float, value=20.0)
        """
        qualifier_kind_map = {
            "VALUE_QUALIFIER":    model.QualifierKind.VALUE_QUALIFIER,
            "CONCEPT_QUALIFIER":  model.QualifierKind.CONCEPT_QUALIFIER,
            "TEMPLATE_QUALIFIER": model.QualifierKind.TEMPLATE_QUALIFIER,
        }
        q = Qualifier(
            type_=type_,
            value_type=value_type,
            value=value,
            kind=qualifier_kind_map.get(kind, model.QualifierKind.TEMPLATE_QUALIFIER),
        )
        if semantic_id:
            q.semantic_id = ExternalReference(
                key=(Key(type_=KeyTypes.GLOBAL_REFERENCE, value=semantic_id),)
            )
        element.qualifier.add(q)
        return q

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def save_json(self, path: str) -> None:
        """Serialise the template submodel to a BaSyx-compatible JSON file.

        Args:
            path: Output file path, e.g. "generated_types/MySubmodel.json".
        """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.submodel, f, cls=basyx.aas.adapter.json.AASToJsonEncoder, indent=2, ensure_ascii=False)

    def get(self) -> Submodel:
        """Return the underlying Submodel object.

        Use this to:
        - Pass as 'parent' to add top-level elements.
        - Serialise manually with json.dumps(..., cls=AASToJsonEncoder).
        - Upload directly to an AAS server.
        """
        return self.submodel


# ----------------------------------------------------------------------
# Direct execution demo — runs only when called as a script, not on import
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import requests

    # Build a small drilling capability template as a demonstration.
    # For YAML-driven creation use: python yaml_to_template.py <file.yaml>

    DrillingCapability = AASTemplateBuilder(
        "DrillingCapability",
        "https://aausmartlab.org/SubmodelTemplate/Capability/BasicDrillingCapability/1/0"
    )

    root = DrillingCapability.get()

    # Add a required collection — pass it back as parent for nested elements
    Drilling_params = DrillingCapability.add_collection(
        root,
        "drillingParameters",
        "semantic_id_drillingParameters",
        cardinality="One"
    )

    # Optional top-level property
    single_property = DrillingCapability.add_property(
        root,
        "singelProperty",
        model.datatypes.String,
        "random_semantic_id",
        cardinality="ZeroToOne"
    )

    # Required property inside the collection
    DrillingCapability.add_property(
        Drilling_params,
        "bitSize",
        model.datatypes.Int,
        "semantic_id_bitSize",
        cardinality="One"
    )

    # Optional range inside the collection
    DrillingCapability.add_range(
        Drilling_params,
        "drillDepth",
        model.datatypes.Int,
        "semantic_id_drillDepth",
        cardinality="ZeroToOne"
    )

    drill_capability_template = DrillingCapability.get()

    submodel_json_string = json.dumps(drill_capability_template, cls=basyx.aas.adapter.json.AASToJsonEncoder)
    aas_dict = json.loads(submodel_json_string)

    AAS_SERVER_URL = "http://localhost:8081"

    response = requests.post(
        f"{AAS_SERVER_URL}/submodels",
        headers={"Content-Type": "application/json"},
        json=aas_dict
    )

    if response.status_code in (200, 201):
        print("Submodel uploaded successfully!")
    else:
        print(f"Upload failed: {response.status_code} - {response.text}")
