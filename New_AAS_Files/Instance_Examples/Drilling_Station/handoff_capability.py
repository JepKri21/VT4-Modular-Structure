import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from BaSyx_AAS_Generator.instance_generator_class import AASInstanceBuilder



HandoffCapability = AASInstanceBuilder(
        "HandoffCapability",
        "https://aausmartlab.org/Shells/Resources/Drilling-12345678/HandoffCapability"
    )

root = HandoffCapability.get()

#=======================================================================================
#======================================= Parameters ====================================
#=======================================================================================

#Stays empty for now, we don't know what to add to it
params = HandoffCapability.add_collection(
    root,
    "Parameters",
)




#=======================================================================================
#====================================== Supported Components ===========================
#=======================================================================================

supported_components = HandoffCapability.add_collection(
    root,
    "SupportedComponents"
)


HandoffCapability.add_property(
    supported_components,
    "Component1",
    "xs:string",
    "Bottom_Cover"    
)

HandoffCapability.add_property(
    supported_components,
    "Component2",
    "xs:string",
    "Bottom_Cover_Drilled"    
)

