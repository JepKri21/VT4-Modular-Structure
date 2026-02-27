from dataclasses import dataclass, field
from typing import List


@dataclass
class Property:
    name: str
    value: str


@dataclass
class PropertiesSubmodel:
    submodel_id: str
    properties: List[Property] = field(default_factory=list)


def parse_properties_submodel(data: dict) -> PropertiesSubmodel:
    submodel_id = data.get("id", "")
    result = PropertiesSubmodel(submodel_id=submodel_id)

    submodel_elements = data.get("submodelElements", [])
    if not submodel_elements:
        return result

    # First element is the SubmodelElementList
    properties_list = submodel_elements[0].get("value", [])

    for property in properties_list:
        name = property.get("idShort", "")
        value = property.get("value", "")
        result.properties.append(Property(name=name, value=value))

    return result