from typing import List
from dataclasses import dataclass
from Shell_Submodel_Dataclasses.Item_Capacity_Dataclasses import *
from Shell_Submodel_Dataclasses.Location_Dataclasses import *
from Shell_Submodel_Dataclasses.Communication_Dataclasses import *
from Shell_Submodel_Dataclasses.Skills_Dataclasses import *
from Shell_Submodel_Dataclasses.Resource_Shell_Dataclasses import *

from Shell_Submodel_Builder import *


class ShellGenerator():
    def __init__(self, shell_data: ResourceShellData, skills: SkillsSubmodelData, communication: CommunicationSubmodelData, location: LocationSubmodelData, item_capacity: ItemCapacitySubmodelData):
        self.shell_data = shell_data
        self.skills = skills
        self.communication = communication
        self.location = location
        self.item_capacity = item_capacity


        self.shell_data_json = self.shell_data.convert_to_dict()
        self.item_capacity_json = self.item_capacity.convert_to_dict()
        self.location_json =self.location.convert_to_dict()
        self.skills_json = self.skills.convert_to_dict()
        self.communication_json = self.communication.convert_to_dict()

    def post_shell_and_submodels(self):
        print("Posting shell and submodels")


##============================================================================================
##============================================================================================
##============================================================================================
#This part does work, I'm not sure how it will work when I try to do it with other stations
#It might need to be remade to be more flexible in case you want to add a collection to your parameters
#Or if you want to have different communicatio methods and so on


config_path = r"C:\Users\silas\Desktop\Manufacturing_Technology_4\Github\VT4-Modular-Structure\Station_Simulators\Resource_Configs\Drill_Station_Config.yaml"

config = load_station_config(config_path)

shell = build_shell(config)
shell_id = config["shell"]["id"]

item_capacity = build_item_capacity(config, shell_id)
communication = build_communication(config, shell_id)
location = build_location(config, shell_id)
skills = build_skills(config, shell_id)

print(shell.convert_to_dict())
print(item_capacity.convert_to_dict())
print(communication.convert_to_dict())
print(location.convert_to_dict())
print(skills.convert_to_dict())