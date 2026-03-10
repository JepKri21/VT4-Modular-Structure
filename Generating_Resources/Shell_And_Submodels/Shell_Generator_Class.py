#from typing import List
#from dataclasses import dataclass
#from Shell_Submodel_Dataclasses.Item_Capacity_Dataclasses import *
#from Shell_Submodel_Dataclasses.Location_Dataclasses import *
#from Shell_Submodel_Dataclasses.Communication_Dataclasses import *
#from Shell_Submodel_Dataclasses.Skills_Dataclasses import *
#from Shell_Submodel_Dataclasses.Resource_Shell_Dataclasses import *

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from Shell_Submodel_Builder import *

class ShellGenerator():
    def __init__(self, yml_config_path: str):
        self.config = load_station_config(yml_config_path)
        self.shell = build_shell(self.config)
        self.shell_id = self.config["shell"]["id"]
        self.item_capacity = build_item_capacity(self.config, self.shell_id)
        self.communication = build_communication(self.config, self.shell_id)
        self.location = build_location(self.config, self.shell_id)
        self.skills = build_skills(self.config, self.shell_id)

    def post_shell_and_submodels(self):
        print("Posting shell and submodels")
        print(self.shell.convert_to_dict())
        print(self.item_capacity.convert_to_dict())
        print(self.communication.convert_to_dict())
        print(self.location.convert_to_dict())
        print(self.skills.convert_to_dict())


    #This one doesn't really work yet
    def find_value(self, obj, id_short):
        if isinstance(obj, dict):
            if obj.get("idShort") == id_short:
                return obj.get("value")
            for v in obj.values():
                result = self.find_value(v, id_short)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = self.find_value(item, id_short)
                if result:
                    return result
        return None



