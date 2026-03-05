
from dataclasses import dataclass
from typing import List, Union, Optional

import sys
from pathlib import Path

# Add Station_Simulators to import path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from Station_Simulators.General_Dataclasses import AutoCollection, AutoSubmodel


@dataclass
class PartType(AutoCollection):
    idShort: str
    Part_Type_Reference: str
    Parts_Currently_Stored: int


@dataclass
class PartTypes(AutoCollection):
    idShort = "Part_Types"
    part_types: List[PartType]


@dataclass
class InternalPartStorage(AutoCollection):
    idShort: str
    Storage_Size: int
    Storing_Method: str
    Storage_Type: str
    Part_Types: PartTypes


@dataclass
class InternalPartStorages(AutoCollection):
    idShort = "Internal_Part_Storages"
    storages: List[InternalPartStorage]

@dataclass
class ItemCapacitySubmodelData(AutoSubmodel):
    idShort: str = "Item_Capacity"          # enforced submodel name
    submodel_data: AutoCollection = None     # the collection for the submodel
    shell_id: Optional[str] = None          # can be set later
