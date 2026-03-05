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

#Hopefully some main script will call this script and upload all the json files
#Meaning this script needs to use the shell_generator class to post them all
#Meaning we configure the station in here and then the generator class will mostly just post them
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

drill_station_shell_json = drill_station_shell.convert_to_dict()

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
storage_1 = InternalPartStorage(
    idShort="Internal_Part_Storage_1",
    Storage_Size=1,
    Storing_Method="First_In_First_Out",
    Storage_Type="Input_Output",
    Part_Types=part_types_in_storage_1
)

storages = InternalPartStorages([storage_1])
item_capacity_submodel = ItemCapacitySubmodelData(submodel_data=[storages],shell_id=shell_uuid)


item_capacity_submodel_json = item_capacity_submodel.convert_to_dict()

pp.pprint(item_capacity_submodel_json)


#===============================================================================================================
#=============================================Communication==================================================================
#===============================================================================================================

# Create a communication method with custom properties
method1 = CommunicationMethod(
    idShort="UNS_Communication",
    extra_elements=[
        Property(idShort="Broker_Adress", valueType="xs:string", value="mqtt://broker.company.com:1883"),
        Property(idShort="Protocol", valueType="xs:string", value="MQTT"),
        Property(idShort="Topic", valueType="xs:string", value="AAU/FIB14/SmartLab/PL1/Stations/Drilling_1"),
        Property(idShort="QoS", valueType="xs:integer", value="2")
    ]
)

# Collection of all methods
methods = CommunicationMethods(communication_methods=[method1])

# Wrap in the submodel
communication_submodel = CommunicationSubmodelData(submodel_data=[methods], shell_id=shell_uuid)

# Generate JSON
communication_submodel_json = communication_submodel.convert_to_dict()

pp.pprint(communication_submodel_json)



#===============================================================================================================
#=============================================Location==================================================================
#===============================================================================================================




general_location = GeneralLocationInformation(
    Building="FIB_14",
    Production_Line="Production_Line_1",
)

cp1 = LocationConnectionPoint(
    idShort="Connection_Point_1",
    Connection_Point_Id="Drill_Station_Connection_Point_1",
    Connection_Type="In-Outfeed"
)

connection_points = LocationConnectionPoints(
    Connection_Points=[cp1]
)

rc1 = ResourceConnectionPoint(
    idShort="Resource_Connection_1",
    Own_Connection_Point_Id="Drill_Station_Connection_Point_1",
    Connected_Resource_Id="https://aausmartlab.com/Assets/Resource/B&R/ACOPOS6D/001",
    Other_Resource_Connection_Point_Id="ACOPOS6D_Connection_Point_7",
    Connection_Position_X_Value=480,
    Connection_Position_Y_Value=120
)

resource_connection_points = ResourceConnectionPoints(
    Resource_Connections=[rc1]
)


location_submodel = LocationSubmodelData(
    submodel_data=[general_location, connection_points,resource_connection_points]
,shell_id=shell_uuid)

location_submodel_json = location_submodel.convert_to_dict()

pp.pprint(location_submodel_json)


#===============================================================================================================
#=============================================Skills==================================================================
#===============================================================================================================



drill_depth = Range(
    idShort="DrillDepth",
    valueType="xs:integer",
    min="1",
    max="20"
)

rot_speed = Range(
    idShort="RotationalSpeed",
    valueType="xs:integer",
    min="1500",
    max="2000"
)

feed = Range(
    idShort="Feed",
    valueType="xs:integer",
    min="100",
    max="200"
)

drill_size = Property(
    idShort="DrillSize",
    valueType="xs:integer",
    value= "5",
)

params = Parameters(
    extra_elements=[drill_depth,rot_speed,feed,drill_size]
)

connection_points = SkillSupportedConnectionPoints([
    SkillConnectionPoint(Connection_Point_Id="Drill_Station_Connection_Point_1")
])

components = SupportedComponents([
    SupportedComponent("https://aausmartlab.com/Assets/Product/Component/AAU/Bottom_Cover")
])

drilling_skill = Skill(
    idShort="Drilling",
    Estimated_Duration=5.0,
    Parameters=params,
    Supported_Connection_Points=connection_points,
    Supported_Components=components
)

agent = Agent(
    idShort="KUKA_Manipulator",
    skills=[drilling_skill]
)

agents = Agents([agent])

skills_submodel = SkillsSubmodelData(
    submodel_data=[agents],
    shell_id=shell_uuid
)

skills_submodel_json = skills_submodel.convert_to_dict()

pp.pprint(skills_submodel_json)