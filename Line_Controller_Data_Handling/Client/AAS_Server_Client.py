import requests
from utils.encoding import base64encode


class AASServerClient:
    def __init__(self, port: int):
        self.base = f"http://localhost:{port}"
        self.shell_endpoint = f"{self.base}/shells"
        self.submodel_endpoint = f"{self.base}/submodels"

    def get_all_shell_ids(self):
        response = requests.get(self.shell_endpoint)
        response.raise_for_status()
        data = response.json()
        return [s["id"] for s in data.get("result", [])]

    def get_shell(self, shell_id: str):
        encoded = base64encode(shell_id)
        response = requests.get(f"{self.shell_endpoint}/{encoded}")
        response.raise_for_status()
        return response.json()

    def get_submodel(self, submodel_id: str):
        try:

            print(f"Getting submodel ID: {submodel_id}")
            encoded = base64encode(submodel_id)
            response = requests.get(f"{self.submodel_endpoint}/{encoded}")
            response.raise_for_status()
            return response.json()
        except:
            print("Submodel does not exist on the server yet")
            return False 