import sys
from pathlib import Path
import json
import requests

sys.path.append(str(Path(__file__).resolve().parent))

from Shell_Submodel_Builder import *

class ShellGenerator():
    def __init__(self, yml_config_path: str):
        self.config = load_station_config(yml_config_path)
        self.shell = build_shell(self.config)
        self.shell_id = self.config["shell"]["id"]
        self.shell_idShort = self.config["shell"]["idShort"]
        self.item_capacity = build_item_capacity(self.config, self.shell_id)
        self.communication = build_communication(self.config, self.shell_id)
        self.location = build_location(self.config, self.shell_id)
        self.skills = build_skills(self.config, self.shell_id)


    def post_shell_and_submodels(self, SHELL_ENDPOINT, SUBMODEL_ENDPOINT):
        print("Posting shell and submodels")
        response = requests.post(SHELL_ENDPOINT, json=self.shell.convert_to_dict(), headers={"Content-Type": "application/json"})
        print(f"Shell POST: {response.status_code}")

        response = requests.post(SUBMODEL_ENDPOINT, json=self.communication.convert_to_dict(), headers={"Content-Type": "application/json"})
        print(f"Communication Submodel POST: {response.status_code}")

        response = requests.post(SUBMODEL_ENDPOINT, json=self.location.convert_to_dict(), headers={"Content-Type": "application/json"})
        print(f"Location Submodel POST: {response.status_code}")

        response = requests.post(SUBMODEL_ENDPOINT, json=self.skills.convert_to_dict(), headers={"Content-Type": "application/json"})
        print(f"Skills Submodel POST: {response.status_code}")

        response = requests.post(SUBMODEL_ENDPOINT, json=self.item_capacity.convert_to_dict(), headers={"Content-Type": "application/json"})
        print(f"Item_Capacity Submodel POST: {response.status_code}")
        




