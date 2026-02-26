import requests
import base64

PORT = "5001"
SERVER_BASE = f"http://localhost:{PORT}"  # your server base URL
SUBMODEL_ENDPOINT = f"{SERVER_BASE}/submodels"
SHELL_ENDPOINT = f"{SERVER_BASE}/shells"

ALL_ASSETS = []

def base64encode(value: str) -> str:
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def get_all_shell_ids():
    response = requests.get(SHELL_ENDPOINT)
    response.raise_for_status()

    data = response.json()
    shells = data.get("result", [])
    return [shell["id"] for shell in shells]


def get_shell_by_id(shell_id: str):
    encoded_id = base64encode(shell_id)
    response = requests.get(f"{SHELL_ENDPOINT}/{encoded_id}")
    response.raise_for_status()
    return response.json()



class AASShell:
    def __init__(
        self,
        shell_id: str,
        id_short: str,
        global_asset_id: str | None,
        submodel_ids: list[str]
    ):
        self.shell_id = shell_id
        self.id_short = id_short
        self.global_asset_id = global_asset_id
        self.submodel_ids = submodel_ids  # just references for now

    @classmethod
    def from_json(cls, data: dict):
        shell_id = data.get("id")
        id_short = data.get("idShort")

        asset_info = data.get("assetInformation", {})
        global_asset_id = asset_info.get("globalAssetId")

        # Extract submodel references
        submodel_ids = []
        submodels = data.get("submodels", [])

        for sub in submodels:
            keys = sub.get("keys", [])
            if keys:
                submodel_id = keys[0].get("value")
                if submodel_id:
                    submodel_ids.append(submodel_id)

        return cls(shell_id, id_short, global_asset_id, submodel_ids)

    def __repr__(self):
        return f"AASShell(idShort={self.id_short}, submodels={len(self.submodel_ids)})"
    



def load_shell_object(shell_id: str) -> AASShell:
    shell_json = get_shell_by_id(shell_id)
    return AASShell.from_json(shell_json)


if __name__ == "__main__":
    print("Fetching shell IDs from server...")
    shell_ids = get_all_shell_ids()

    if not shell_ids:
        print("No shells found on server")
        exit()

    print(f"Found {len(shell_ids)} shells")

    for shell_id in range(len(shell_ids)):
        shell_obj = load_shell_object(shell_ids[shell_id])
        # Only load one for now (as you requested)
        ALL_ASSETS.append(shell_obj)

        print("Created object:")
        print(shell_obj)
        print("ID:", shell_obj.shell_id)
        print("Short ID:", shell_obj.id_short)
        print(f"Submodels ids: {shell_obj.submodel_ids}")