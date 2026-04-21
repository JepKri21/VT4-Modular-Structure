import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from BaSyx_AAS_Generator.instance_generator_class import AASInstanceBuilder



DrillingStationSkills = AASInstanceBuilder(
        "Skills",
        "https://aausmartlab.org/Shells/Resources/Drilling-12345678/Skills"
    )

root = DrillingStationSkills.get()

#=======================================================================================
#====================================== Drilling =======================================
#=======================================================================================



drilling = DrillingStationSkills.add_collection(
    root,
    "Drilling"
)

#================================== Capability Reference ===============================


DrillingStationSkills.add_reference_element(
    drilling,
    "CapabilityReference",
    "https://aausmartlab.org/Shells/Resources/Drilling-12345678/DrillingCapability"
)

#================================== Skill Triggers ====================================


skill_triggers_drilling = DrillingStationSkills.add_collection(
    drilling,
    "SkillTriggers"
)

DrillingStationSkills.add_property(
    skill_triggers_drilling,
    "Start",
    "xs:string",
    "start"
)

DrillingStationSkills.add_property(
    skill_triggers_drilling,
    "Stop",
    "xs:string",
    "stop"
)

DrillingStationSkills.add_property(
    skill_triggers_drilling,
    "Reset",
    "xs:string",
    "reset"
)

DrillingStationSkills.add_property(
    skill_triggers_drilling,
    "Abort",
    "xs:string",
    "abort"
)

DrillingStationSkills.add_property(
    skill_triggers_drilling,
    "Clear",
    "xs:string",
    "Clear"
)

DrillingStationSkills.add_property(
    skill_triggers_drilling,
    "Hold",
    "xs:string",
    "hold"
)

DrillingStationSkills.add_property(
    skill_triggers_drilling,
    "Unhold",
    "xs:string",
    "unhold"
)

DrillingStationSkills.add_property(
    skill_triggers_drilling,
    "Suspend",
    "xs:string",
    "suspend"
)

DrillingStationSkills.add_property(
    skill_triggers_drilling,
    "Unsuspend",
    "xs:string",
    "unsuspend"
)


#================================== Actors =========================================


actors_drilling = DrillingStationSkills.add_collection(
    drilling,
    "Actors"
)

DrillingStationSkills.add_property(
    actors_drilling,
    "Actor1",
    "xs:string",
    "KUKAManipulator"
)



#=======================================================================================
#====================================== Handoff =======================================
#=======================================================================================



handoff = DrillingStationSkills.add_collection(
    root,
    "Handoff"
)

#================================== Capability Reference ===============================


DrillingStationSkills.add_reference_element(
    handoff,
    "CapabilityReference",
    "https://aausmartlab.org/Shells/Resources/Drilling-12345678/HandoffCapability"
)

#================================== Skill Triggers ====================================


skill_triggers_handoff = DrillingStationSkills.add_collection(
    handoff,
    "SkillTriggers"
)

DrillingStationSkills.add_property(
    skill_triggers_handoff,
    "Start",
    "xs:string",
    "start"
)

DrillingStationSkills.add_property(
    skill_triggers_handoff,
    "Stop",
    "xs:string",
    "stop"
)

DrillingStationSkills.add_property(
    skill_triggers_handoff,
    "Reset",
    "xs:string",
    "reset"
)

DrillingStationSkills.add_property(
    skill_triggers_handoff,
    "Abort",
    "xs:string",
    "abort"
)

DrillingStationSkills.add_property(
    skill_triggers_handoff,
    "Clear",
    "xs:string",
    "Clear"
)

DrillingStationSkills.add_property(
    skill_triggers_handoff,
    "Hold",
    "xs:string",
    "hold"
)

DrillingStationSkills.add_property(
    skill_triggers_handoff,
    "Unhold",
    "xs:string",
    "unhold"
)

DrillingStationSkills.add_property(
    skill_triggers_handoff,
    "Suspend",
    "xs:string",
    "suspend"
)

DrillingStationSkills.add_property(
    skill_triggers_handoff,
    "Unsuspend",
    "xs:string",
    "unsuspend"
)


#================================== Actors =========================================


actors_handoff = DrillingStationSkills.add_collection(
    handoff,
    "Actors"
)

DrillingStationSkills.add_property(
    actors_handoff,
    "Actor1",
    "xs:string",
    "KUKAManipulator"
)



