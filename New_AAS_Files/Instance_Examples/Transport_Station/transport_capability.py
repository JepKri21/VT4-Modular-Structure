import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from BaSyx_AAS_Generator.instance_generator_class import AASInstanceBuilder



TransportCapability = AASInstanceBuilder(
        "TransportCapability",
        "https://aausmartlab.org/Shells/Resources/Transport-12345678/TransportCapability"
    )

root = TransportCapability.get()

params = TransportCapability.add_collection(
    root,
    "Parameters",
)

sup_compo = TransportCapability.add_collection(
    root,
    "SupportedComponents"
)


speed_constrant_ms = TransportCapability.add_range(
    params,
    "SpeedConstraint_m_per_s",
    "xs:float",
    0,
    3,
)

acceleration_constrant_ms = TransportCapability.add_range(
    params,
    "AccelerationConstraint",
    "xs:float",
    0,
    20,
)

target_position = TransportCapability.add_property(
    params,
    "TargetPosition",
    "xs:string",
    ""              #<-- Controlled by the LineController
)


TransportCapability.add_property(
    sup_compo,
    "Component1",
    "xs:string",
    "Bottom_Cover"    
)

TransportCapability.add_property(
    sup_compo,
    "Component2",
    "xs:string",
    "Top_Cover"    
)

TransportCapability.add_property(
    sup_compo,
    "Component3",
    "xs:string",
    "Bottom_Cover_PCB"    
)

TransportCapability.add_property(
    sup_compo,
    "Component4",
    "xs:string",
    "Bottom_Cover_PCB_Fuse"
)

TransportCapability.add_property(
    sup_compo,
    "Component5",
    "xs:string",
    "Telefon_Pro_Max"
)

TransportCapability.add_property(
    sup_compo,
    "Component6",
    "xs:string",
    "Bottom_Cover_Drilled"
)

