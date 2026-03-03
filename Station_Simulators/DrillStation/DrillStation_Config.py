import sys
from pathlib import Path

# Add Station_Simulators to import path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))


from Station_Simulators.Item_Capacity_Dataclasses import *
from Station_Simulators.Location_Dataclasses import *
from Station_Simulators.Communication_Dataclasses import *
from Station_Simulators.Skills_Dataclasses import *
from Station_Simulators.Resource_Shell_Dataclasses import *


from pprint import PrettyPrinter

pp = PrettyPrinter(
    width=200,      # max line width before wrapping
    compact=False,   # pack items onto fewer lines
    depth=None,     # limit nesting if you want (e.g., 3)
    sort_dicts=False,
    indent=2
)


#===============================================================================================================
#=============================================Shell==================================================================
#===============================================================================================================


shell_uuid = "https://aausmartlab.com/Assets/Resource/MADE/Drill_Station/1e1d4a58-e403-4d5e-81fa-19c544835561"

item_capacity_reference = SubmodelReference("Item_Capacity")
location_reference = SubmodelReference("Location")
communication_reference = SubmodelReference("Communication")
skills_reference = SubmodelReference("Skills")
documentation_reference = SubmodelReference("Documentation")

drill_station_shell = ResourceShellData(
    id=shell_uuid,
    idShort = "Drill_Station",
    references=[item_capacity_reference,
     location_reference,
     communication_reference,
     skills_reference,
     documentation_reference]
     )

drill_station_shell_json = drill_station_shell.to_dict()

pp.pprint(drill_station_shell_json)


#===============================================================================================================
#=========================================Item_Capacity======================================================================
#===============================================================================================================

#Now actually, the drill station doesn't really have any storage at all, it only has an input and output, 
# but since this will be on shuttles, it doesn't really own those positions


# define part types
part_type_1 = PartType("Part_Type_1", "https://aausmartlab.com/Assets/Product/Component/AAU/Bottom_Cover", 0)
part_types_in_storage_1 = PartTypes([part_type_1])

# define storage
storage = InternalPartStorage(
    idShort="Internal_Part_Storage_1",
    storage_size=1,
    storing_method="First_In_First_Out",
    storage_type="Input_Output",
    part_types=part_types_in_storage_1
)

storages = InternalPartStorages([storage])
item_capacity_submodel = ItemCapacitySubmodelData(storages)

item_capacity_submodel_json = item_capacity_submodel.to_dict(shell_uuid)

pp.pprint(item_capacity_submodel_json)


#===============================================================================================================
#=============================================Communication==================================================================
#===============================================================================================================

MQTT_com_property_1 = Property("Property","Broker_Adress", "xs:string", "mqtt://broker.company.com:1883")
MQTT_com_property_2 = Property("Property","Protocol", "xs:string", "MQTT")
MQTT_com_property_3 = Property("Property","Topic", "xs:string", "AAU/FIB14/SmartLab/PL1/DrillStation1")
MQTT_com_property_4 = Property("Property","QoS", "xs:string", "2")

MQTT_com_method = CommunicationMethod("UNS_Communication",[MQTT_com_property_1, MQTT_com_property_2,MQTT_com_property_3,MQTT_com_property_4])

communication_submodel = CommunicationSubmodelData([MQTT_com_method])

communication_submodel_json = communication_submodel.to_dict(shell_uuid)

pp.pprint(communication_submodel_json)