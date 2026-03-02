from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SkillParameterRange:
    name: str
    min_value: Optional[float]
    max_value: Optional[float]
    unit: Optional[str]


@dataclass
class SkillParameterValue:
    name: str
    value: str
    unit: Optional[str]


@dataclass
class Skill:
    name: str
    estimated_duration: Optional[float]
    parameters: Dict[str, object] = field(default_factory=dict)
    supported_components: List[str] = field(default_factory=list)
    connection_points: List[str] = field(default_factory=list)


@dataclass
class AgentSkills:
    agent_name: str
    skills: Dict[str, Skill] = field(default_factory=dict)


@dataclass
class SkillsSubmodel:
    submodel_id: str
    agents: Dict[str, AgentSkills] = field(default_factory=dict)


def parse_skills_submodel(data: dict) -> SkillsSubmodel:
    submodel_id = data.get("id")
    result = SkillsSubmodel(submodel_id=submodel_id)

    elements = data.get("submodelElements", [])
    if not elements:
        return result

    agents_list = elements[0].get("value", [])

    for agent in agents_list:
        agent_name = agent.get("idShort")
        agent_obj = AgentSkills(agent_name=agent_name)

        for skill_collection in agent.get("value", []):
            skill = parse_skill(skill_collection)
            agent_obj.skills[skill.name] = skill

        result.agents[agent_name] = agent_obj

    return result


def parse_skill(collection: dict) -> Skill:
    name = collection.get("idShort")
    estimated_duration = None
    parameters = {}
    supported_components = []
    connection_points = []

    for element in collection.get("value", []):

        if element["modelType"] == "Property" and element["idShort"] == "Estimated_Duration":
            estimated_duration = float(element["value"])

        elif element["idShort"] == "Parameters":
            parameters = parse_skill_parameters(element)

        elif element["idShort"] == "Supported_Components":
            supported_components = [p["value"] for p in element.get("value", [])]

        elif element["idShort"] == "Supported_Connection_Points":
            connection_points = [p["value"] for p in element.get("value", [])]

    return Skill(
        name=name,
        estimated_duration=estimated_duration,
        parameters=parameters,
        supported_components=supported_components,
        connection_points=connection_points,
    )


def parse_skill_parameters(collection: dict) -> Dict[str, object]:
    params = {}

    for p in collection.get("value", []):

        if p["modelType"] == "Range":
            params[p["idShort"]] = SkillParameterRange(
                name=p["idShort"],
                min_value=float(p.get("min")) if p.get("min") else None,
                max_value=float(p.get("max")) if p.get("max") else None,
                unit=_extract_unit(p),
            )

        elif p["modelType"] == "Property":
            params[p["idShort"]] = SkillParameterValue(
                name=p["idShort"],
                value=p.get("value"),
                unit=_extract_unit(p),
            )

    return params

#This should maybe be in utils
def _extract_unit(element: dict):
    semantic = element.get("semanticId", {})
    keys = semantic.get("keys", [])
    return keys[0]["value"] if keys else None