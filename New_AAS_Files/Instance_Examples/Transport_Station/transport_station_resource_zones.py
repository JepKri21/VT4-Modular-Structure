import sys
from pathlib import Path
import json
import requests
import basyx
from basyx.aas import model
from basyx.aas.adapter import json as basyx_json


sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from BaSyx_AAS_Generator.instance_generator_class import AASInstanceBuilder



TransportStationZones = AASInstanceBuilder(
        "ResourceZones",
        "https://aausmartlab.org/Shells/Resources/Transport-12345678/ResourceZones"
    )

root = TransportStationZones.get()

center = TransportStationZones.add_collection(
    root,
    "CenterPoint"
)

TransportStationZones.add_property(
    center,
    "XPos",
    "xs:float",
    0.0
)


TransportStationZones.add_property(
    center,
    "YPos",
    "xs:float",
    0.0
)



#============================= Resource Zone =======================================

station_zone = TransportStationZones.add_collection(
    root,
    "ResourceGeometry"
)

point1 = TransportStationZones.add_collection(station_zone,"Point1")
TransportStationZones.add_property(point1,"XPos","xs:float",0.0)
TransportStationZones.add_property(point1,"YPos","xs:float",0.0)

point2 = TransportStationZones.add_collection(station_zone,"Point2")
TransportStationZones.add_property(point2,"XPos","xs:float",960.0)
TransportStationZones.add_property(point2,"YPos","xs:float",0.0)

point3 = TransportStationZones.add_collection(station_zone,"Point3")
TransportStationZones.add_property(point3,"XPos","xs:float",960.0)
TransportStationZones.add_property(point3,"YPos","xs:float",720.0)

point4 = TransportStationZones.add_collection(station_zone,"Point4")
TransportStationZones.add_property(point4,"XPos","xs:float",0.0)
TransportStationZones.add_property(point4,"YPos","xs:float",720.0)


#============================= Input Zones =======================================

input_zones = TransportStationZones.add_collection(
    root,
    "InputZones"
)




#============================= Output Zones =======================================

output_zones = TransportStationZones.add_collection(
    root,
    "OutputZones"
)


#============================= In_Output Zones =======================================

in_output_zones = TransportStationZones.add_collection(
    root,
    "InOutputZones"
)

in_output_zone1 = TransportStationZones.add_collection(
    in_output_zones,
    "Zone1"
)

point1 = TransportStationZones.add_collection(in_output_zone1,"Point1")
TransportStationZones.add_property(point1,"XPos","xs:float",60.0)
TransportStationZones.add_property(point1,"YPos","xs:float",60.0)

point2 = TransportStationZones.add_collection(in_output_zone1,"Point2")
TransportStationZones.add_property(point2,"XPos","xs:float",900.0)
TransportStationZones.add_property(point2,"YPos","xs:float",60.0)

point3 = TransportStationZones.add_collection(in_output_zone1,"Point3")
TransportStationZones.add_property(point3,"XPos","xs:float",900.0)
TransportStationZones.add_property(point3,"YPos","xs:float",660.0)

point4 = TransportStationZones.add_collection(in_output_zone1,"Point4")
TransportStationZones.add_property(point4,"XPos","xs:float",60.0)
TransportStationZones.add_property(point4,"YPos","xs:float",660.0)
