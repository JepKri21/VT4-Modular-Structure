import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from BaSyx_AAS_Generator.instance_generator_class import AASInstanceBuilder


DrillingCapability = AASInstanceBuilder(
        "DrillingCapability",
        "https://aausmartlab.org/Shells/Resources/Drilling-12345678/DrillingCapability"
    )

root = DrillingCapability.get()

#=======================================================================================
#======================================= Parameters ====================================
#=======================================================================================


params = DrillingCapability.add_collection(
    root,
    "Parameters",
)

DrillingCapability.add_property(
    params,
    "BitDiameter_mm",
    "xs:integer",
    5
)

DrillingCapability.add_range(
    params,
    "DrillDepth_mm",
    "xs:integer",
    0,
    200
)

DrillingCapability.add_range(
    params,
    "SpindleSpeed_RPM",
    "xs:integer",
    0,
    1200
)

DrillingCapability.add_range(
    params,
    "SpindleFeed_mm_per_s",
    "xs:integer",
    0,
    50
)


#=======================================================================================
#====================================== Supported Components ===========================
#=======================================================================================

supported_components = DrillingCapability.add_collection(
    root,
    "SupportedComponents"
)


DrillingCapability.add_property(
    supported_components,
    "Component1",
    "xs:string",
    "Bottom_Cover"    
)

DrillingCapability.add_property(
    supported_components,
    "Component2",
    "xs:string",
    "Top_Cover"    
)



#=======================================================================================
#========================================= Allowed Materials ===========================
#=======================================================================================

allowed_materials = DrillingCapability.add_collection(
    root,
    "AllowedMaterials"
)

DrillingCapability.add_property(
    allowed_materials,
    "Material1",
    "xs:string",
    "PLA"
)

DrillingCapability.add_property(
    allowed_materials,
    "Material2",
    "xs:string",
    "ABS"
)


AAS_SERVER_URL = "http://localhost:8081"
DrillingCapability.send_submodel(AAS_SERVER_URL)