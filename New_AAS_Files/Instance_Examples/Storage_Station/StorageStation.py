#This should just create the shell and publish it to the server with the submodels.

from storage_station_resource_zone import StorageStationZones
from handoff_capability import HandoffCapability
from retrieve_capability import RetrieveCapability
from store_capability import StoreCapability
from storage_skills import StorageStationSkills
from storage_station_inventory import StorageStationInventory


server_url = "http://localhost:8081"


def send_shell(shell, server_url):

    shell_json_string = json.dumps(shell, cls=basyx.aas.adapter.json.AASToJsonEncoder)
    aas_dict = json.loads(shell_json_string)

    response = requests.post(
        f"{server_url}/shells",
        headers={"Content-Type": "application/json"},
        json=aas_dict
    )

    if response.status_code in (200, 201):
        print("Shell uploaded successfully!")
    else:
        print(f"Upload failed: {response.status_code} - {response.text}")


#===============================================================================
#============================= Storage Station ===============================

asset_information = model.AssetInformation(
    asset_kind=model.AssetKind.INSTANCE,
    global_asset_id='https://aausmartlab.org/Shells/Resources/Storage-12345678'
)

# step 1.2: create the Asset Administration Shell
identifier = 'https://aausmartlab.org/Shells/Resources/Storage-12345678'
aas = model.AssetAdministrationShell(
    id_=identifier,  # set identifier
    id_short="StorageStation",
    asset_information=asset_information
)

aas.submodel.add(model.ModelReference.from_referable(StorageStationZones.get()))

send_shell(aas,server_url)
StorageStationZones.send_submodel(server_url)
HandoffCapability.send_submodel(server_url)
StoreCapability.send_submodel(server_url)
RetrieveCapability.send_submodel(server_url)
StorageStationSkills.send_submodel(server_url)
StorageStationInventory.send_submodel(server_url)