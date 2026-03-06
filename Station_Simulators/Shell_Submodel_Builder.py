import yaml
import sys
from pathlib import Path


from Shell_Submodel_Dataclasses.Item_Capacity_Dataclasses import *
from Shell_Submodel_Dataclasses.Location_Dataclasses import *
from Shell_Submodel_Dataclasses.Communication_Dataclasses import *
from Shell_Submodel_Dataclasses.Skills_Dataclasses import *
from Shell_Submodel_Dataclasses.Resource_Shell_Dataclasses import *


def load_station_config(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def build_shell(config):

    shell_cfg = config["shell"]

    references = [
        SubmodelReference(name)
        for name in shell_cfg["submodels"]
    ]

    shell = ResourceShellData(
        id=shell_cfg["id"],
        idShort=shell_cfg["idShort"],
        references=references
    )

    return shell

def build_item_capacity(config, shell_id):

    storages = []

    for storage_cfg in config["item_capacity"]["internal_part_storages"]:

        part_types = []

        for pt in storage_cfg["part_types"]:
            part_types.append(
                PartType(
                    pt["idShort"],
                    pt["part_type_id"],
                    pt["quantity"]
                )
            )

        part_types_obj = PartTypes(part_types)

        storage = InternalPartStorage(
            idShort=storage_cfg["idShort"],
            Storage_Size=storage_cfg["storage_size"],
            Storing_Method=storage_cfg["storing_method"],
            Storage_Type=storage_cfg["storage_type"],
            Part_Types=part_types_obj
        )

        storages.append(storage)

    storages_obj = InternalPartStorages(storages)

    return ItemCapacitySubmodelData(
        submodel_data=[storages_obj],
        shell_id=shell_id
    )


def build_communication(config, shell_id):

    methods = []

    for method_cfg in config["communication"]["methods"]:

        props = []

        for key, value in method_cfg["properties"].items():

            if isinstance(value, int):
                valueType = "xs:integer"
            else:
                valueType = "xs:string"

            props.append(
                Property(
                    idShort=key,
                    valueType=valueType,
                    value=str(value)
                )
            )

        method = CommunicationMethod(
            idShort=method_cfg["idShort"],
            extra_elements=props
        )

        methods.append(method)

    methods_obj = CommunicationMethods(methods)

    return CommunicationSubmodelData(
        submodel_data=[methods_obj],
        shell_id=shell_id
    )


def build_location(config, shell_id):

    loc = config["location"]

    general_location = GeneralLocationInformation(
        Building=loc["general_information"]["building"],
        Production_Line=loc["general_information"]["production_line"]
    )

    connection_points = []

    for cp in loc["connection_points"]:
        connection_points.append(
            LocationConnectionPoint(
                idShort=cp["idShort"],
                Connection_Point_Id=cp["connection_point_id"],
                Connection_Type=cp["connection_type"]
            )
        )

    cp_obj = LocationConnectionPoints(connection_points)

    resource_connections = []

    for rc in loc["resource_connections"]:

        resource_connections.append(
            ResourceConnectionPoint(
                idShort=rc["idShort"],
                Own_Connection_Point_Id=rc["own_connection_point_id"],
                Connected_Resource_Id=rc["connected_resource_id"],
                Other_Resource_Connection_Point_Id=rc["other_resource_connection_point_id"],
                Connection_Position_X_Value=rc["position"]["x"],
                Connection_Position_Y_Value=rc["position"]["y"]
            )
        )

    rc_obj = ResourceConnectionPoints(resource_connections)

    return LocationSubmodelData(
        submodel_data=[general_location, cp_obj, rc_obj],
        shell_id=shell_id
    )


def build_skills(config, shell_id):

    agents = []

    for agent_cfg in config["skills"]["agents"]:

        skills = []

        for skill_cfg in agent_cfg["skills"]:

            params = []

            for r in skill_cfg["parameters"]["ranges"]:
                params.append(
                    Range(
                        idShort=r["idShort"],
                        valueType=r["value_type"],
                        min=str(r["min"]),
                        max=str(r["max"])
                    )
                )

            for p in skill_cfg["parameters"]["properties"]:
                params.append(
                    Property(
                        idShort=p["idShort"],
                        valueType=p["value_type"],
                        value=str(p["value"])
                    )
                )

            parameters = Parameters(extra_elements=params)

            scp = SkillSupportedConnectionPoints([
                SkillConnectionPoint(
                    Connection_Point_Id=x["connection_point_id"]
                )
                for x in skill_cfg["supported_connection_points"]
            ])

            components = SupportedComponents([
                SupportedComponent(c)
                for c in skill_cfg["supported_components"]
            ])

            skill = Skill(
                idShort=skill_cfg["idShort"],
                Estimated_Duration=skill_cfg["estimated_duration"],
                Parameters=parameters,
                Supported_Connection_Points=scp,
                Supported_Components=components
            )

            skills.append(skill)

        agent = Agent(
            idShort=agent_cfg["idShort"],
            skills=skills
        )

        agents.append(agent)

    agents_obj = Agents(agents)

    return SkillsSubmodelData(
        submodel_data=[agents_obj],
        shell_id=shell_id
    )