import sys
from pathlib import Path
import json
import requests
import basyx
from basyx.aas import model
from basyx.aas.adapter import json as basyx_json


sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from BaSyx_AAS_Generator.instance_generator_class import AASInstanceBuilder



StorageStationZones = AASInstanceBuilder(
        "ResourceZones",
        "https://aausmartlab.org/Shells/Resources/Storage-12345678/ResourceZones"
    )

root = StorageStationZones.get()

center = StorageStationZones.add_collection(
    root,
    "CenterPoint"
)

StorageStationZones.add_property(
    center,
    "XPos",
    "xs:float",
    0.0
)


StorageStationZones.add_property(
    center,
    "YPos",
    "xs:float",
    0.0
)



#============================= Resource Zone =======================================

station_zone = StorageStationZones.add_collection(
    root,
    "ResourceGeometry"
)

point1 = StorageStationZones.add_collection(station_zone,"Point1")
StorageStationZones.add_property(point1,"XPos","xs:float",-50.0)
StorageStationZones.add_property(point1,"YPos","xs:float",-50.0)

point2 = StorageStationZones.add_collection(station_zone,"Point2")
StorageStationZones.add_property(point2,"XPos","xs:float",50.0)
StorageStationZones.add_property(point2,"YPos","xs:float",-50.0)

point3 = StorageStationZones.add_collection(station_zone,"Point3")
StorageStationZones.add_property(point3,"XPos","xs:float",50.0)
StorageStationZones.add_property(point3,"YPos","xs:float",50.0)

point4 = StorageStationZones.add_collection(station_zone,"Point4")
StorageStationZones.add_property(point4,"XPos","xs:float",-50.0)
StorageStationZones.add_property(point4,"YPos","xs:float",50.0)


#============================= Input Zones =======================================

input_zones = StorageStationZones.add_collection(
    root,
    "InputZones"
)




#============================= Output Zones =======================================

output_zones = StorageStationZones.add_collection(
    root,
    "OutputZones"
)


#============================= In_Output Zones =======================================

in_output_zones = StorageStationZones.add_collection(
    root,
    "InOutputZones"
)

in_output_zone1 = StorageStationZones.add_collection(
    in_output_zones,
    "Zone1"
)

point1 = StorageStationZones.add_collection(in_output_zone1,"Point1")
StorageStationZones.add_property(point1,"XPos","xs:float",-40.0)
StorageStationZones.add_property(point1,"YPos","xs:float",50.0)

point2 = StorageStationZones.add_collection(in_output_zone1,"Point2")
StorageStationZones.add_property(point2,"XPos","xs:float",40.0)
StorageStationZones.add_property(point2,"YPos","xs:float",50.0)

point3 = StorageStationZones.add_collection(in_output_zone1,"Point3")
StorageStationZones.add_property(point3,"XPos","xs:float",40.0)
StorageStationZones.add_property(point3,"YPos","xs:float",130.0)

point4 = StorageStationZones.add_collection(in_output_zone1,"Point4")
StorageStationZones.add_property(point4,"XPos","xs:float",-40.0)
StorageStationZones.add_property(point4,"YPos","xs:float",130.0)
