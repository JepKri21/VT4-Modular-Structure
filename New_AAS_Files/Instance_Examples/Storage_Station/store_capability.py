import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from BaSyx_AAS_Generator.instance_generator_class import AASInstanceBuilder



StoreCapability = AASInstanceBuilder(
        "StoreCapability",
        "https://aausmartlab.org/Shells/Resources/Storage-12345678/StoreCapability"
    )

root = StoreCapability.get()

#=======================================================================================
#======================================= Parameters ====================================
#=======================================================================================

#Stays empty for now, we don't know what to add to it
params = StoreCapability.add_collection(
    root,
    "Parameters",
)


#=======================================================================================
#====================================== Supported Components ===========================
#=======================================================================================

supported_components = StoreCapability.add_collection(
    root,
    "SupportedComponents"
)


StoreCapability.add_property(
    supported_components,
    "Component1",
    "xs:string",
    "Bottom_Cover"    
)
StoreCapability.add_property(
    supported_components,
    "Component1",
    "xs:string",
    "Bottom_Cover_Drilled"    
)