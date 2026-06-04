import sys
from pathlib import Path
import json
import basyx.aas.adapter.json as aas_json

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from BaSyx_AAS_Generator.instance_generator_class import AASInstanceBuilder
from basyx.aas.model import ModelReference, Key, KeyTypes, AssetAdministrationShell as AASShell

#IMPORTANT NOTE: Global Reference Frame is the (0,0,0) position for the entire production line configuration


Configuration = AASInstanceBuilder(
        "LineConfiguration",
        "https://aausmartlab.org/Shells/Configuration/ProductionLine1-12345678"
    )


root = Configuration.get()


#Resource Locations:
    #Resource Name
        # Center X, Y position relative to Global Reference Frame
        # Theta angle relative relative to center of resource.

#Connection Points:
    #Connection Point 1
        #Location
            # X, Y position of point relative to Global Reference Frame
        #ConnectedResources
            #Reference to the resources (In theory it could be more than 2)


resource_locations = Configuration.add_collection(
    root,
    "ResourceLocations"
)

connection_points = Configuration.add_collection(
    root,
    "ConnectionPoints"
)

#============================================================================================================
#================================== Drill Station Location ==================================================
#============================================================================================================

drill_station = Configuration.add_collection(
    resource_locations,
    "DrillStation"
)

Configuration.add_reference_element(
    drill_station,
    "ResourceReference",
    value=ModelReference(
        key=(Key(type_=KeyTypes.ASSET_ADMINISTRATION_SHELL,
                 value="https://aausmartlab.org/Shells/Resources/Drilling-12345678"),),
        type_=AASShell,
    ),
)

location_drill_station = Configuration.add_collection(
    drill_station,
    "GlobalLocation"
)

Configuration.add_property(
    location_drill_station,
    "XPos",
    "xs:float",
    50.0
)

Configuration.add_property(
    location_drill_station,
    "YPos",
    "xs:float",
    50.0
)

Configuration.add_property(
    location_drill_station,
    "ThetaAngle",
    "xs:integer",
    90
)


#============================================================================================================
#================================== Transport Location ======================================================
#============================================================================================================

transport_station = Configuration.add_collection(
    resource_locations,
    "TransportStation"
)

Configuration.add_reference_element(
    transport_station,
    "ResourceReference",
    value=ModelReference(
        key=(Key(type_=KeyTypes.ASSET_ADMINISTRATION_SHELL,
                 value="https://aausmartlab.org/Shells/Resources/Transport-12345678"),),
        type_=AASShell,
    ),
)


location_transport_station = Configuration.add_collection(
    transport_station,
    "GlobalLocation"
)

Configuration.add_property(
    location_transport_station,
    "XPos",
    "xs:float",
    25.0
)

Configuration.add_property(
    location_transport_station,
    "YPos",
    "xs:float",
    75.0
)

Configuration.add_property(
    location_transport_station,
    "ThetaAngle",
    "xs:integer",
    0
)


#============================================================================================================
#================================== Storage Station Location ================================================
#============================================================================================================

storage_station = Configuration.add_collection(
    resource_locations,
    "StorageStation"
)

Configuration.add_reference_element(
    storage_station,
    "ResourceReference",
    value=ModelReference(
        key=(Key(type_=KeyTypes.ASSET_ADMINISTRATION_SHELL,
                 value="https://aausmartlab.org/Shells/Resources/Storage-12345678"),),
        type_=AASShell,
    ),
)

location_storage_station = Configuration.add_collection(
    storage_station,
    "GlobalLocation"
)

Configuration.add_property(
    location_storage_station,
    "XPos",
    "xs:float",
    10.0
)

Configuration.add_property(
    location_storage_station,
    "YPos",
    "xs:float",
    20.0
)

Configuration.add_property(
    location_storage_station,
    "ThetaAngle",
    "xs:integer",
    180
)

#============================================================================================================
#================================== Connection Points =======================================================
#============================================================================================================

#============================ Drill To Transport - Global ==========================================

conncetion_point_1 = Configuration.add_collection(
    connection_points,
    "ConnectionPoint1"
)

conncetion_point_1_location = Configuration.add_collection(
    conncetion_point_1,
    "GlobalLocation"
)

Configuration.add_property(
    conncetion_point_1_location,
    "XPos",
    "xs:float",
    10.0
)

Configuration.add_property(
    conncetion_point_1_location,
    "YPos",
    "xs:float",
    20.0
)

Configuration.add_property(
    conncetion_point_1_location,
    "ThetaAngle",
    "xs:integer",
    180
)


conncetion_point_1_connceted_resources = Configuration.add_collection(
    conncetion_point_1,
    "ConnectedResources"
)

#============================ Drill To Transport - Drill Local ==========================================

conncetion_point_1_connceted_resource1 = Configuration.add_collection(
    conncetion_point_1_connceted_resources,
    "Resource1"
)

Configuration.add_reference_element(
    conncetion_point_1_connceted_resource1,
    "ResourceReference",
    value=ModelReference(
        key=(Key(type_=KeyTypes.ASSET_ADMINISTRATION_SHELL,
                 value="https://aausmartlab.org/Shells/Resources/Drilling-12345678"),),
        type_=AASShell,
    ),
)

Configuration.add_property(
    conncetion_point_1_connceted_resource1,
    "WorkAreaType",
    "xs:string",
    "in_outfeed"
)

conncetion_point_1_connceted_resource1_local_coords = Configuration.add_collection(
    conncetion_point_1_connceted_resource1,
    "LocalLocation"
)

Configuration.add_property(
    conncetion_point_1_connceted_resource1_local_coords,
    "XPos",
    "xs:float",
    100
)

Configuration.add_property(
    conncetion_point_1_connceted_resource1_local_coords,
    "YPos",
    "xs:float",
    150
)

#============================ Drill To Transport - Transport Local ==========================================

conncetion_point_1_connceted_resource2 = Configuration.add_collection(
    conncetion_point_1_connceted_resources,
    "Resource2",
)

Configuration.add_reference_element(
    conncetion_point_1_connceted_resource2,
    "ResourceReference",
    value=ModelReference(
        key=(Key(type_=KeyTypes.ASSET_ADMINISTRATION_SHELL,
                 value="https://aausmartlab.org/Shells/Resources/Transport-12345678"),),
        type_=AASShell,
    ),
)

Configuration.add_property(
    conncetion_point_1_connceted_resource2,
    "WorkAreaType",
    "xs:string",
    "in_outfeed"
)

conncetion_point_1_connceted_resource2_local_coords = Configuration.add_collection(
    conncetion_point_1_connceted_resource2,
    "LocalLocation"
)

Configuration.add_property(
    conncetion_point_1_connceted_resource2_local_coords,
    "XPos",
    "xs:float",
    350
)

Configuration.add_property(
    conncetion_point_1_connceted_resource2_local_coords,
    "YPos",
    "xs:float",
    400
)




#====================================== Storage To Transport - Global =========================

conncetion_point_2 = Configuration.add_collection(
    connection_points,
    "ConnectionPoint2"
)

conncetion_point_2_location = Configuration.add_collection(
    conncetion_point_2,
    "GlobalLocation"
)

Configuration.add_property(
    conncetion_point_2_location,
    "XPos",
    "xs:float",
    30.0
)

Configuration.add_property(
    conncetion_point_2_location,
    "YPos",
    "xs:float",
    20.0
)

Configuration.add_property(
    conncetion_point_2_location,
    "ThetaAngle",
    "xs:integer",
    180
)


conncetion_point_2_connceted_resources = Configuration.add_collection(
    conncetion_point_2,
    "ConnectedResources"
)

#====================================== Storage To Transport - Storage Local =========================


conncetion_point_2_connceted_resource1 = Configuration.add_collection(
    conncetion_point_2_connceted_resources,
    "Resource1"
)

Configuration.add_reference_element(
    conncetion_point_2_connceted_resource1,
    "ResourceReference",
    value=ModelReference(
        key=(Key(type_=KeyTypes.ASSET_ADMINISTRATION_SHELL,
                 value="https://aausmartlab.org/Shells/Resources/Storage-12345678"),),
        type_=AASShell,
    ),
)

Configuration.add_property(
    conncetion_point_2_connceted_resource1,
    "WorkAreaType",
    "xs:string",
    "in_outfeed"
)

conncetion_point_2_connceted_resource1_local_coords = Configuration.add_collection(
    conncetion_point_2_connceted_resource1,
    "LocalLocation"
)

Configuration.add_property(
    conncetion_point_2_connceted_resource1_local_coords,
    "XPos",
    "xs:float",
    100
)

Configuration.add_property(
    conncetion_point_2_connceted_resource1_local_coords,
    "YPos",
    "xs:float",
    150
)


#====================================== Storage To Transport - Transport Local =========================


conncetion_point_2_connceted_resource2 = Configuration.add_collection(
    conncetion_point_2_connceted_resources,
    "Resource2"
)

Configuration.add_reference_element(
    conncetion_point_2_connceted_resource2,
    "ResourceReference",
    value=ModelReference(
        key=(Key(type_=KeyTypes.ASSET_ADMINISTRATION_SHELL,
                 value="https://aausmartlab.org/Shells/Resources/Transport-12345678"),),
        type_=AASShell,
    ),
)

Configuration.add_property(
    conncetion_point_2_connceted_resource2,
    "WorkAreaType",
    "xs:string",
    "in_outfeed"
)

conncetion_point_2_connceted_resource2_local_coords = Configuration.add_collection(
    conncetion_point_2_connceted_resource2,
    "LocalLocation"
)

Configuration.add_property(
    conncetion_point_2_connceted_resource2_local_coords,
    "XPos",
    "xs:float",
    100
)

Configuration.add_property(
    conncetion_point_2_connceted_resource2_local_coords,
    "YPos",
    "xs:float",
    150
)

submodel = Configuration.get()
submodel_json_string = json.dumps(submodel, cls=aas_json.AASToJsonEncoder)
aas_dict = json.loads(submodel_json_string)

print(submodel_json_string)

#AAS_SERVER_URL = "http://localhost:8081"
#Configuration.send_submodel(AAS_SERVER_URL)