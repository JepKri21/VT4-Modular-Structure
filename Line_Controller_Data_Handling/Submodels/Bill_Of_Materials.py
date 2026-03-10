from dataclasses import dataclass, field
from typing import List


@dataclass
class Material:
    name: str
    component_variant: str


@dataclass
class BillOfMaterialsSubmodel:
    submodel_id: str
    materials: List[Material] = field(default_factory=list)


def parse_bill_of_materials_submodel(data: dict) -> BillOfMaterialsSubmodel:
    submodel_id = data.get("id")
    result = BillOfMaterialsSubmodel(submodel_id=submodel_id)

    elements = data.get("submodelElements", [])
    if not elements:
        return result

    list_of_materials = elements[0].get("value", [])

    for material_col in list_of_materials:
        name = material_col.get("idShort")
        component_variant = None
        for prop in material_col.get("value", []):
            if prop["idShort"] == "Component_Variant":
                component_variant = prop.get("value")
        result.materials.append(Material(name=name, component_variant=component_variant))

    return result