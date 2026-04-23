import sys
from pathlib import Path
import json
import requests
import basyx
from basyx.aas import model
from basyx.aas.adapter import json as basyx_json


sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from BaSyx_AAS_Generator.instance_generator_class import AASInstanceBuilder



DrillingStationZones = AASInstanceBuilder(
        "ResourceZones",
        "https://aausmartlab.org/Shells/Resources/Drilling-12345678/ResourceZones"
    )

root = DrillingStationZones.get()

center = DrillingStationZones.add_collection(
    root,
    "CenterPoint"
)

DrillingStationZones.add_property(
    center,
    "XPos",
    "xs:float",
    0.0
)


DrillingStationZones.add_property(
    center,
    "YPos",
    "xs:float",
    0.0
)



#============================= Resource Zone =======================================

station_zone = DrillingStationZones.add_collection(
    root,
    "ResourceGeometry"
)

point1 = DrillingStationZones.add_collection(station_zone,"Point1")
DrillingStationZones.add_property(point1,"XPos","xs:float",-50.0)
DrillingStationZones.add_property(point1,"YPos","xs:float",-50.0)

point2 = DrillingStationZones.add_collection(station_zone,"Point2")
DrillingStationZones.add_property(point2,"XPos","xs:float",50.0)
DrillingStationZones.add_property(point2,"YPos","xs:float",-50.0)

point3 = DrillingStationZones.add_collection(station_zone,"Point3")
DrillingStationZones.add_property(point3,"XPos","xs:float",50.0)
DrillingStationZones.add_property(point3,"YPos","xs:float",50.0)

point4 = DrillingStationZones.add_collection(station_zone,"Point4")
DrillingStationZones.add_property(point4,"XPos","xs:float",-50.0)
DrillingStationZones.add_property(point4,"YPos","xs:float",50.0)


#============================= Input Zones =======================================

input_zones = DrillingStationZones.add_collection(
    root,
    "InputZones"
)




#============================= Output Zones =======================================

output_zones = DrillingStationZones.add_collection(
    root,
    "OutputZones"
)


#============================= In_Output Zones =======================================

in_output_zones = DrillingStationZones.add_collection(
    root,
    "InOutputZones"
)

in_output_zone1 = DrillingStationZones.add_collection(
    in_output_zones,
    "Zone1"
)

point1 = DrillingStationZones.add_collection(in_output_zone1,"Point1")
DrillingStationZones.add_property(point1,"XPos","xs:float",-40.0)
DrillingStationZones.add_property(point1,"YPos","xs:float",50.0)

point2 = DrillingStationZones.add_collection(in_output_zone1,"Point2")
DrillingStationZones.add_property(point2,"XPos","xs:float",40.0)
DrillingStationZones.add_property(point2,"YPos","xs:float",50.0)

point3 = DrillingStationZones.add_collection(in_output_zone1,"Point3")
DrillingStationZones.add_property(point3,"XPos","xs:float",40.0)
DrillingStationZones.add_property(point3,"YPos","xs:float",130.0)

point4 = DrillingStationZones.add_collection(in_output_zone1,"Point4")
DrillingStationZones.add_property(point4,"XPos","xs:float",-40.0)
DrillingStationZones.add_property(point4,"YPos","xs:float",130.0)



""" An attempt at using the registry, but there didn't seem to be a link between the registry and discovery, which makes it pretty useless unless we make the connection ourselves.

descriptor_json = """
{
    "assetKind": "Instance",
    "endpoints": [
        {
            "interface": "AAS-3.0",
            "protocolInformation": 
                {
                    "href": "http://localhost:8081/shells/aHR0cHM6Ly9hYXVzbWFydGxhYi5vcmcvU2hlbGxzL1Jlc291cmNlcy9EcmlsbGluZy0xMjM0NTY3OA%22",
                    "endpointProtocol": "http"
                }
        }
    ],
    "globalAssetId": "https://aausmartlab.org/Shells/Resources/Drilling-12345678",
    "idShort": "DrillStation",
    "id": "https://aausmartlab.org/Shells/Resources/Drilling-12345678",
    "specificAssetIds": [
        {
            "name": "ProductionLine",
            "value": "ProductionLine1"
        },
        {
            "name": "ShellType",
            "value": "Resource"
        }
    ]
}
"""

aas_dict = json.loads(descriptor_json)

response = requests.put(
    "http://localhost:8082/shell-descriptors/aHR0cHM6Ly9hYXVzbWFydGxhYi5vcmcvU2hlbGxzL1Jlc291cmNlcy9EcmlsbGluZy0xMjM0NTY3OA==",
    headers={"Content-Type": "application/json"},
    json=aas_dict
)

if response.status_code in (200, 201, 204):
    print("Shell uploaded successfully!")
else:
    print(f"Upload failed: {response.status_code} - {response.text}")


"""