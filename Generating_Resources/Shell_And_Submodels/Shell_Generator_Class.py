import sys
from pathlib import Path
import json
import requests

sys.path.append(str(Path(__file__).resolve().parent))

from Generic_Config_Decoder import *

class ShellGenerator():
    def __init__(self, yml_config_path: str):

        self.builder = AASYamlBuilder(yml_config_path)
        self.shell_id = self.builder.shell_id
        self.shell_idShort = self.builder.shell_idShort
        # Full AAS
        self.shell = self.builder.get_aas()
        # All submodels
        self.submodels = self.builder.get_submodels()

    def post_shell_and_submodels(self, SHELL_ENDPOINT, SUBMODEL_ENDPOINT):
        print("Posting shell and submodels")
        response = requests.post(SHELL_ENDPOINT, json=self.shell, headers={"Content-Type": "application/json"})
        print(f"Shell POST: {response.status_code}")

        for submodel in self.submodels:
            response = requests.post(SUBMODEL_ENDPOINT, json=submodel, headers={"Content-Type": "application/json"})
            print(f"{submodel['idShort']} Submodel POST: {response.status_code}")
        




