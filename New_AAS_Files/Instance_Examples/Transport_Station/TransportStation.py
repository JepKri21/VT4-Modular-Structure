#This should just create the shell and publish it to the server with the submodels.

from transport_station_resource_zones import TransportStationZones
from handoff_capability import HandoffCapability
from transport_capability import TransportCapability
from transport_skill import TransportStationSkills
from transport_inventory import TransportStationInventory

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
#============================= Transport Station ===============================

asset_information = model.AssetInformation(
    asset_kind=model.AssetKind.INSTANCE,
    global_asset_id='https://aausmartlab.org/Shells/Resources/Transport-12345678'
)

# step 1.2: create the Asset Administration Shell
identifier = 'https://aausmartlab.org/Shells/Resources/Transport-12345678'
aas = model.AssetAdministrationShell(
    id_=identifier,  # set identifier
    id_short="TransportStation",
    asset_information=asset_information
)

aas.submodel.add(model.ModelReference.from_referable(TransportStationZones.get()))

send_shell(aas,server_url)
TransportStationZones.send_submodel(server_url)
HandoffCapability.send_submodel(server_url)
TransportCapability.send_submodel(server_url)
TransportStationSkills.send_submodel(server_url)
TransportStationInventory.send_submodel(server_url)