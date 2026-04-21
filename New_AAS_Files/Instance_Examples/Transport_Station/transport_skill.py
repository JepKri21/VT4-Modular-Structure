import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from BaSyx_AAS_Generator.instance_generator_class import AASInstanceBuilder



TransportStationSkills = AASInstanceBuilder(
        "Skills",
        "https://aausmartlab.org/Shells/Resources/Transport-12345678/Skills"
    )

root = TransportStationSkills.get()


#================================= Transport Capability ========================================

transport = TransportStationSkills.add_collection(
    root,
    "Transport"
)

TransportStationSkills.add_reference_element(
    transport,
    "CapabilityReference",
    "https://aausmartlab.org/Shells/Resources/Transport-12345678/TransportCapability"
)

skill_triggers_transport = TransportStationSkills.add_collection(
    transport,
    "SkillTriggers"
)


TransportStationSkills.add_property(
    skill_triggers_transport,
    "Start",
    "xs:string",
    "start"
)

TransportStationSkills.add_property(
    skill_triggers_transport,
    "Stop",
    "xs:string",
    "stop"
)

TransportStationSkills.add_property(
    skill_triggers_transport,
    "Reset",
    "xs:string",
    "reset"
)

TransportStationSkills.add_property(
    skill_triggers_transport,
    "Abort",
    "xs:string",
    "abort"
)

TransportStationSkills.add_property(
    skill_triggers_transport,
    "Clear",
    "xs:string",
    "Clear"
)

TransportStationSkills.add_property(
    skill_triggers_transport,
    "Hold",
    "xs:string",
    "hold"
)

TransportStationSkills.add_property(
    skill_triggers_transport,
    "Unhold",
    "xs:string",
    "unhold"
)

TransportStationSkills.add_property(
    skill_triggers_transport,
    "Suspend",
    "xs:string",
    "suspend"
)

TransportStationSkills.add_property(
    skill_triggers_transport,
    "Unsuspend",
    "xs:string",
    "unsuspend"
)


actors_transport = TransportStationSkills.add_collection(
    transport,
    "Actors"
)

# How to add this, when we don't know how many shuttles are available?
TransportStationSkills.add_property(
    actors_transport,
    "Actor1",
    "xs:string",
    "Shuttle1"
)

TransportStationSkills.add_property(
    actors_transport,
    "Actor2",
    "xs:string",
    "Shuttle2"
)


#================================= Handoff Capability ========================================

handoff = TransportStationSkills.add_collection(
    root,
    "Handoff"
)

TransportStationSkills.add_reference_element(
    handoff,
    "CapabilityReference",
    "https://aausmartlab.org/Shells/Resources/Transport-12345678/HandoffCapability"
)

skill_triggers_handoff = TransportStationSkills.add_collection(
    handoff,
    "SkillTriggers"
)


TransportStationSkills.add_property(
    skill_triggers_handoff,
    "Start",
    "xs:string",
    "start"
)

TransportStationSkills.add_property(
    skill_triggers_handoff,
    "Stop",
    "xs:string",
    "stop"
)

TransportStationSkills.add_property(
    skill_triggers_handoff,
    "Reset",
    "xs:string",
    "reset"
)

TransportStationSkills.add_property(
    skill_triggers_handoff,
    "Abort",
    "xs:string",
    "abort"
)

TransportStationSkills.add_property(
    skill_triggers_handoff,
    "Clear",
    "xs:string",
    "Clear"
)

TransportStationSkills.add_property(
    skill_triggers_handoff,
    "Hold",
    "xs:string",
    "hold"
)

TransportStationSkills.add_property(
    skill_triggers_handoff,
    "Unhold",
    "xs:string",
    "unhold"
)

TransportStationSkills.add_property(
    skill_triggers_handoff,
    "Suspend",
    "xs:string",
    "suspend"
)

TransportStationSkills.add_property(
    skill_triggers_handoff,
    "Unsuspend",
    "xs:string",
    "unsuspend"
)


actors_handoff = TransportStationSkills.add_collection(
    handoff,
    "Actors"
)

# How to add this, when we don't know how many shuttles are available?
TransportStationSkills.add_property(
    actors_handoff,
    "Actor1",
    "xs:string",
    "Shuttle1"
)

TransportStationSkills.add_property(
    actors_handoff,
    "Actor2",
    "xs:string",
    "Shuttle2"
)

