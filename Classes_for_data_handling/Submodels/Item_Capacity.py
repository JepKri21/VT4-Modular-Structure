from dataclasses import dataclass, field
from typing import List


@dataclass
class PartTypeCapacity:
    part_type_reference: str
    parts_currently_stored: int


@dataclass
class InternalPartStorage:
    storing_method: str
    storage_size: int
    storage_type: str
    part_types: List[PartTypeCapacity] = field(default_factory=list)


@dataclass
class ItemCapacitySubmodel:
    submodel_id: str
    internal_part_storages: List[InternalPartStorage] = field(default_factory=list)


def parse_item_capacity_submodel(data: dict) -> ItemCapacitySubmodel:
    result = ItemCapacitySubmodel(submodel_id=data.get("id", ""))

    elements = data.get("submodelElements", [])
    if not elements:
        return result

    internal_storages = elements[0].get("value", [])

    for storage_col in internal_storages:
        storing_method = ""
        storage_size = 0
        storage_type = ""
        part_types_list = []

        for element in storage_col.get("value", []):
            id_short = element.get("idShort")

            if id_short == "Storing_Method":
                storing_method = element.get("value", "")

            elif id_short == "Storage_Size":
                storage_size = int(element.get("value", 0))

            elif id_short == "Storage_Type":
                storage_type = element.get("value", "")

            elif id_short == "Part_Types":
                for part_type_col in element.get("value", []):
                    part_ref = ""
                    parts_current = 0

                    for prop in part_type_col.get("value", []):
                        if prop["idShort"] == "Part_Type_reference":
                            part_ref = prop.get("value", "")
                        elif prop["idShort"] == "Parts_Currently_Stored":
                            parts_current = int(prop.get("value", 0))

                    part_types_list.append(
                        PartTypeCapacity(
                            part_type_reference=part_ref,
                            parts_currently_stored=parts_current
                        )
                    )

        result.internal_part_storages.append(
            InternalPartStorage(
                storing_method=storing_method,
                storage_size=storage_size,
                storage_type=storage_type,
                part_types=part_types_list
            )
        )

    return result