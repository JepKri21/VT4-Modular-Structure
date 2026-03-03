from typing import List
from dataclasses import dataclass
from Station_Simulators.Item_Capacity_Dataclasses import *
from Station_Simulators.Location_Dataclasses import LocationSubmodelData
from Station_Simulators.Communication_Dataclasses import CommunicationSubmodelData
from Station_Simulators.Skills_Dataclasses import SkillsSubmodelData
from Station_Simulators.Resource_Shell_Dataclasses import *



class ShellGenerator():
    def __init__(self, shell_data: ResourceShellData, skills: SkillsSubmodelData, communication: CommunicationSubmodelData, location: LocationSubmodelData, item_capacity: ItemCapacitySubmodelData):
        self.shell_data = shell_data
        self.skills = skills
        self.communication = communication
        self.location = location
        self.item_capacity = item_capacity


        self. item_capacity_json = self.item_capacity.to_dict(shell_id=shell_data.id)