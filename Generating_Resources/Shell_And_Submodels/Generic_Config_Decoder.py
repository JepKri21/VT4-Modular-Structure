from typing import List, Union
from dataclasses import dataclass
import json
import yaml


@dataclass
class Property:
    idShort: str
    valueType: str
    value: str

    def to_dict(self):
        return {
            "modelType": "Property",
            "idShort": self.idShort,
            "valueType": self.valueType,
            "value": self.value
        }


@dataclass
class Range:
    idShort: str
    valueType: str
    min: str
    max: str

    def to_dict(self):
        return {
            "modelType": "Range",
            "idShort": self.idShort,
            "valueType": self.valueType,
            "min": self.min,
            "max": self.max
        }


@dataclass
class SubmodelElementCollection:
    idShort: str
    value: List[Union['Property', 'Range', 'SubmodelElementCollection']]

    def to_dict(self):
        return {
            "modelType": "SubmodelElementCollection",
            "idShort": self.idShort,
            "value": [v.to_dict() for v in self.value]
        }


class AASYamlBuilder:

    python_to_aas_type = {
        str: "xs:string",
        int: "xs:integer",
        float: "xs:float",
        bool: "xs:boolean"
    }

    def __init__(self, yaml_file_path: str):

        with open(yaml_file_path, "r") as f:
            self.yaml_data = yaml.safe_load(f)

        shell_info = self.yaml_data["shell"]

        self.shell_id = shell_info["id"]["value"]
        self.shell_idShort = shell_info["idShort"]["value"]

        self.submodels = []
        self.submodels_by_idShort = {}
        self.aas = None

        self._build()

    # --------------------------
    # Recursive parser
    # --------------------------
    def parse_element(self, idShort: str, data):

        if isinstance(data, dict) and "value" in data:
            val = data["value"]
            value_type = self.python_to_aas_type.get(type(val), "xs:string")

            return Property(idShort, value_type, str(val))

        if isinstance(data, dict) and "min" in data and "max" in data:
            value_type = self.python_to_aas_type.get(type(data["min"]), "xs:string")

            return Range(
                idShort=idShort,
                valueType=value_type,
                min=str(data["min"]),
                max=str(data["max"])
            )

        if isinstance(data, dict):

            elements = []

            for key, value in data.items():
                elements.append(self.parse_element(key, value))

            return SubmodelElementCollection(idShort, elements)

        if isinstance(data, list):

            elements = []

            for item in data:

                if isinstance(item, dict) and len(item) == 1:

                    name = next(iter(item))
                    value = item[name]

                    elements.append(self.parse_element(name, value))

                else:
                    raise ValueError(f"Invalid YAML list structure under '{idShort}'")

            return SubmodelElementCollection(idShort, elements)

        value_type = self.python_to_aas_type.get(type(data), "xs:string")

        return Property(idShort, value_type, str(data))

    # --------------------------
    # Submodel builder
    # --------------------------
    def _build_submodel(self, submodel_name: str, data: dict):

        submodel_id = f"{self.shell_id}/{submodel_name}"

        elements = []

        for key, value in data.items():
            elem = self.parse_element(key, value)
            elements.append(elem.to_dict())

        return {
            "idShort": submodel_name,
            "id": submodel_id,
            "submodelElements": elements
        }

    # --------------------------
    # Build everything
    # --------------------------
    def _build(self):

        for submodel_name, content in self.yaml_data.get("submodels", {}).items():

            submodel = self._build_submodel(submodel_name, content)

            self.submodels.append(submodel)
            self.submodels_by_idShort[submodel_name] = submodel

        self.aas = {
            "idShort": self.shell_idShort,
            "id": self.shell_id,
            "modelType": "AssetAdministrationShell",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": self.shell_id
            },
            "submodels": [
                {
                    "type": "ModelReference",
                    "keys": [{"type": "Submodel", "value": sm["id"]}]
                }
                for sm in self.submodels
            ]
        }

    # --------------------------
    # Public API
    # --------------------------

    def get_aas(self):
        return self.aas

    def get_submodels(self):
        return self.submodels

    def get_submodel(self, idShort: str):
        return self.submodels_by_idShort.get(idShort)

    def get_submodel_ids(self):
        return [sm["id"] for sm in self.submodels]

    def to_json(self):
        return json.dumps(self.aas, indent=2)

