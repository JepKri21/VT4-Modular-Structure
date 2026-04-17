from basyx.aas import model
import json
import basyx.aas.adapter.xml
import basyx.aas.adapter.json
import requests

from basyx.aas.model import (
    Submodel,
    Property,
    Range,
    SubmodelElementCollection,
    SubmodelElementList,
    Qualifier,
    Key,
    ModelReference,
    KeyTypes,
    ExternalReference
)


class AASTemplateBuilder:


    CARDINALITY_IRI = "https://admin-shell.io/SubmodelTemplates/Cardinality/1/0"

    def __init__(self, id_short: str, identification: str):
        self.submodel = Submodel(
            id_short=id_short,
            id_=identification,
            kind=model.ModellingKind.TEMPLATE
        )

    def _get_container(self, parent):
        if isinstance(parent, Submodel):
            return parent.submodel_element
        return parent.value  # SubmodelElementCollection, SubmodelElementList

    # -------------------------
    # Qualifier helper
    # -------------------------
    def _cardinality(self, value: str) -> Qualifier:
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

    # -------------------------
    # Add Property
    # -------------------------
    def add_property(
        self,
        parent,
        id_short: str,
        value_type,
        semantic_id: str,
        required: bool = True
    ):
        prop = Property(
            id_short=id_short,
            value_type=value_type
        )

        prop.semantic_id = ExternalReference(
            key=(
                Key(
                    type_=KeyTypes.GLOBAL_REFERENCE,
                    value=semantic_id
                ),
            )
        )

        prop.qualifier.add(
            self._cardinality("One" if required else "ZeroToOne")
        )

        self._get_container(parent).add(prop)
        return prop

    # -------------------------
    # Add Range
    # -------------------------
    def add_range(
        self,
        parent,
        id_short: str,
        value_type,
        semantic_id: str,
        required: bool = True
    ):
        rng = Range(
            id_short=id_short,
            value_type=value_type
        )

        rng.semantic_id = ExternalReference(
            key=(
                Key(
                    type_=KeyTypes.GLOBAL_REFERENCE,
                    value=semantic_id
                ),
            )
        )

        rng.qualifier.add(
            self._cardinality("One" if required else "ZeroToOne")
        )

        self._get_container(parent).add(rng)
        return rng

    # -------------------------
    # Add Collection
    # -------------------------
    def add_collection(
        self,
        parent,
        id_short: str,
        semantic_id: str,
        required: bool = True
    ):
        col = SubmodelElementCollection(id_short=id_short)

        col.semantic_id = ExternalReference(
            key=(
                Key(
                    type_=KeyTypes.GLOBAL_REFERENCE,
                    value=semantic_id
                ),
            )
        )

        col.qualifier.add(
            self._cardinality("One" if required else "ZeroToOne")
        )

        self._get_container(parent).add(col)
        return col

    # -------------------------
    # Add List
    # -------------------------
    def add_list(
        self,
        parent,
        id_short: str,
        semantic_id: str,
        element_type: type,
        cardinality: str = "ZeroToMany"
    ):
        lst = SubmodelElementList(
            id_short=id_short,
            type_value_list_element=element_type
        )

        lst.semantic_id = ExternalReference(
            key=(
                Key(
                    type_=KeyTypes.GLOBAL_REFERENCE,
                    value=semantic_id
                ),
            )
        )

        lst.qualifier.add(self._cardinality(cardinality))

        self._get_container(parent).add(lst)
        return lst

    # -------------------------
    # Root access
    # -------------------------
    def get(self) -> Submodel:
        return self.submodel



DrillingCapability = AASTemplateBuilder(
    "DrillingCapability",
    "https://aausmartlab.org/SubmodelTemplate/Capability/BasicDrillingCapability/1/0"
)

root = DrillingCapability.get()

Drilling_params = DrillingCapability.add_collection(
    root,
    "drillingParameters",
    "semantic_id_drillingParameters",
    required=True
)

single_property = DrillingCapability.add_property(
    root,
    "singelProperty",
    model.datatypes.String,
    "random_semantic_id",
    required=False
)

DrillingCapability.add_property(
    Drilling_params,
    "bitSize",
    model.datatypes.Int,
    "semantic_id_bitSize",
    required=True
    )

DrillingCapability.add_range(
    Drilling_params,
    "drillDepth",
    model.datatypes.Int,
    "semantic_id_drillDepth",
    required=False
    )

drill_capability_template = DrillingCapability.get()

submodel_json_string = json.dumps(drill_capability_template, cls=basyx.aas.adapter.json.AASToJsonEncoder)
aas_dict = json.loads(submodel_json_string)

AAS_SERVER_URL = "http://localhost:8081"  # change to your server URL

response = requests.post(
    f"{AAS_SERVER_URL}/submodels",
    headers={"Content-Type": "application/json"},
    json=aas_dict
)

if response.status_code in (200, 201):
    print("Submodel uploaded successfully!")
else:
    print(f"Upload failed: {response.status_code} - {response.text}")



