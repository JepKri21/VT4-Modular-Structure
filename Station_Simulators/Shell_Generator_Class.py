from typing import List
from dataclasses import dataclass
from Station_Simulators.Item_Capacity_Dataclasses import *
from Station_Simulators.Location_Dataclasses import *
from Station_Simulators.Communication_Dataclasses import *
from Station_Simulators.Skills_Dataclasses import *
from Station_Simulators.Resource_Shell_Dataclasses import *



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