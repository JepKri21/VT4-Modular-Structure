import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from BaSyx_AAS_Generator.instance_generator_class import AASInstanceBuilder



RetrieveCapability = AASInstanceBuilder(
        "RetrieveCapability",
        "https://aausmartlab.org/Shells/Resources/Storage-12345678/RetrieveCapability"
    )

root = RetrieveCapability.get()

#=======================================================================================
#======================================= Parameters ====================================
#=======================================================================================

#Stays empty for now, we don't know what to add to it
params = RetrieveCapability.add_collection(
    root,
    "Parameters",
)


#=======================================================================================
#====================================== Supported Components ===========================
#=======================================================================================

supported_components = RetrieveCapability.add_collection(
    root,
    "SupportedComponents"
)


RetrieveCapability.add_property(
    supported_components,
    "Component1",
    "xs:string",
    "Bottom_Cover"    
)
RetrieveCapability.add_property(
    supported_components,
    "Component1",
    "xs:string",
    "Bottom_Cover_Drilled"    
)