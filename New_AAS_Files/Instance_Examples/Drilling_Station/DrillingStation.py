#This should just create the shell and publish it to the server with the submodels.

from drilling_station_resource_zones import DrillingStationZones
from drilling_Capability import DrillingCapability
from handoff_capability import HandoffCapability
from drilling_station_inventory import DrillingStationInventory
from drilling_station_skills import DrillingStationSkills

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
#============================= Drilling Station ===============================

asset_information = model.AssetInformation(
    asset_kind=model.AssetKind.INSTANCE,
    global_asset_id='https://aausmartlab.org/Shells/Resources/Drilling-12345678'
)

# step 1.2: create the Asset Administration Shell
identifier = 'https://aausmartlab.org/Shells/Resources/Drilling-12345678'
aas = model.AssetAdministrationShell(
    id_=identifier,  # set identifier
    id_short="DrillingStation",
    asset_information=asset_information
)

aas.submodel.add(model.ModelReference.from_referable(DrillingStationZones.get()))

send_shell(aas,server_url)
DrillingStationZones.send_submodel(server_url)
HandoffCapability.send_submodel(server_url)
DrillingCapability.send_submodel(server_url)
DrillingStationSkills.send_submodel(server_url)
DrillingStationInventory.send_submodel(server_url)