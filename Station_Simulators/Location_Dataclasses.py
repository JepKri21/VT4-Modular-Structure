from dataclasses import dataclass, field
from typing import List, Optional
from Station_Simulators.General_Dataclasses import *


@dataclass
class GeneralLocationInformation(AutoCollection):
    idShort: str = "General_Location_Information"
    Building: str = ""
    Production_Line: str = ""

@dataclass
class LocationConnectionPoint(AutoCollection):
    idShort: str
    Connection_Point_Id: str
    Connection_Type: str

@dataclass
class LocationConnectionPoints(AutoCollection):
    idShort: str = "Connection_Points"
    Connection_Points: List[LocationConnectionPoint] = field(default_factory=list)


@dataclass
class ResourceConnectionPoint(AutoCollection):
    idShort: str

    Own_Connection_Point_Id: str
    Connected_Resource_Id: str
    Other_Resource_Connection_Point_Id: str

    Connection_Position_X_Value: int
    Connection_Position_Y_Value: int

@dataclass
class ResourceConnectionPoints(AutoCollection):
    idShort: str = "Resource_Connections"
    Resource_Connections: List[ResourceConnectionPoint] = field(default_factory=list)

@dataclass
class LocationSubmodelData(AutoSubmodel):
    idShort: str = "Location"
    submodel_data: AutoCollection = None
    shell_id: Optional[str] = None