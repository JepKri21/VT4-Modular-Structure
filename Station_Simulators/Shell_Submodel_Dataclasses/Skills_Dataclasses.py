from dataclasses import dataclass, field
from .General_Dataclasses import *

@dataclass
class Parameters(AutoCollection):
    idShort = "Parameters",
    extra_elements: List[Union[Property, Range, SubmodelElementCollection]] = field(default_factory=list)

@dataclass
class SkillConnectionPoint(AutoCollection):
    Connection_Point_Id: str


@dataclass
class SkillSupportedConnectionPoints(AutoCollection):
    idShort: str = "Supported_Connection_Points"
    connection_points: list[SkillConnectionPoint] = field(default_factory=list)

@dataclass
class SupportedComponent(AutoCollection):
    Component_Type: str


@dataclass
class SupportedComponents(AutoCollection):
    idShort: str = "Supported_Components"
    components: list[SupportedComponent] = field(default_factory=list)


@dataclass
class Skill(AutoCollection):
    idShort: str
    Estimated_Duration: float
    Parameters: Parameters
    Supported_Connection_Points: SkillSupportedConnectionPoints
    Supported_Components: SupportedComponents

@dataclass
class Agent(AutoCollection):
    idShort: str
    skills: list[Skill] = field(default_factory=list)

@dataclass
class Agents(AutoCollection):
    idShort: str = "Agents"
    agents: list[Agent] = field(default_factory=list)


@dataclass
class SkillsSubmodelData(AutoSubmodel):
    idShort: str = "Skills"
    submodel_data: AutoCollection = None
    shell_id: Optional[str] = None