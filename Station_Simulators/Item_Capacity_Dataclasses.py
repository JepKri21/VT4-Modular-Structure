
from dataclasses import dataclass
from typing import List

import sys
from pathlib import Path

# Add Station_Simulators to import path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from Station_Simulators.General_Dataclasses import Property, Range, SubmodelElementCollection, SubmodelElementList

# ---- Leaf level ----
@dataclass
class PartType:
    idShort: str
    part_type_reference: str
    parts_currently_stored: int

    def to_collection(self) -> SubmodelElementCollection:
        return SubmodelElementCollection(
            idShort=self.idShort,
            value=[
                Property(idShort="Part_Type_reference", valueType="xs:string", value=self.part_type_reference),
                Property(idShort="Parts_Currently_Stored", valueType="xs:integer", value=str(self.parts_currently_stored))
            ]
        )

# ---- Collection of part types ----
@dataclass
class PartTypes:
    part_types: List[PartType]

    def to_collection(self) -> SubmodelElementCollection:
        return SubmodelElementCollection(
            idShort="Part_Types",
            value=[pt.to_collection() for pt in self.part_types]
        )

# ---- Internal storage ----
@dataclass
class InternalPartStorage:
    idShort: str
    storage_size: int
    storing_method: str
    storage_type: str
    part_types: PartTypes

    def to_collection(self) -> SubmodelElementCollection:
        return SubmodelElementCollection(
            idShort=self.idShort,
            value=[
                Property(idShort="Storage_Size", valueType="xs:integer", value=str(self.storage_size)),
                Property(idShort="Storing_Method", valueType="xs:string", value=self.storing_method),
                Property(idShort="Storage_Type", valueType="xs:string", value=self.storage_type),
                self.part_types.to_collection()
            ]
        )

# ---- List of storages ----
@dataclass
class InternalPartStorages:
    storages: List[InternalPartStorage]

    def to_list(self) -> SubmodelElementList:
        return SubmodelElementList(
            idShort="Internal_Part_Storages",
            typeValueListElement="SubmodelElementCollection",
            value=[s.to_collection() for s in self.storages]
        )

# ---- Item capacity submodel ----
@dataclass
class ItemCapacitySubmodelData:
    internal_part_storages: InternalPartStorages

    def to_dict(self, shell_id: str):
        return {
            "idShort": "Item_Capacity",
            "id": f"{shell_id}/Item_Capacity",
            "submodelElements": [
                self.internal_part_storages.to_list().to_dict()
            ]
        }