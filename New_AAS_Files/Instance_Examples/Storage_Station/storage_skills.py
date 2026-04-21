import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from BaSyx_AAS_Generator.instance_generator_class import AASInstanceBuilder



StorageStationSkills = AASInstanceBuilder(
        "Skills",
        "https://aausmartlab.org/Shells/Resources/Storage-12345678/Skills"
    )

root = StorageStationSkills.get()

#=======================================================================================
#====================================== Retrieve =======================================
#=======================================================================================



retrieve = StorageStationSkills.add_collection(
    root,
    "Retrieve"
)


#================================== Capability Reference ===============================


StorageStationSkills.add_reference_element(
    retrieve,
    "CapabilityReference",
    "https://aausmartlab.org/Shells/Resources/Storage-12345678/RetrieveCapability"
)

#================================== Skill Triggers ====================================


skill_triggers_retrieve = StorageStationSkills.add_collection(
    retrieve,
    "SkillTriggers"
)

StorageStationSkills.add_property(
    skill_triggers_retrieve,
    "Start",
    "xs:string",
    "start"
)

StorageStationSkills.add_property(
    skill_triggers_retrieve,
    "Stop",
    "xs:string",
    "stop"
)

StorageStationSkills.add_property(
    skill_triggers_retrieve,
    "Reset",
    "xs:string",
    "reset"
)

StorageStationSkills.add_property(
    skill_triggers_retrieve,
    "Abort",
    "xs:string",
    "abort"
)

StorageStationSkills.add_property(
    skill_triggers_retrieve,
    "Clear",
    "xs:string",
    "Clear"
)

StorageStationSkills.add_property(
    skill_triggers_retrieve,
    "Hold",
    "xs:string",
    "hold"
)

StorageStationSkills.add_property(
    skill_triggers_retrieve,
    "Unhold",
    "xs:string",
    "unhold"
)

StorageStationSkills.add_property(
    skill_triggers_retrieve,
    "Suspend",
    "xs:string",
    "suspend"
)

StorageStationSkills.add_property(
    skill_triggers_retrieve,
    "Unsuspend",
    "xs:string",
    "unsuspend"
)


#================================== Actors =========================================


actors_retrieve = StorageStationSkills.add_collection(
    retrieve,
    "Actors"
)

StorageStationSkills.add_property(
    actors_retrieve,
    "Actor1",
    "xs:string",
    "UR5"
)


#=======================================================================================
#====================================== Handoff ========================================
#=======================================================================================



handoff = StorageStationSkills.add_collection(
    root,
    "Handoff"
)

#================================== Capability Reference ===============================


StorageStationSkills.add_reference_element(
    handoff,
    "CapabilityReference",
    "https://aausmartlab.org/Shells/Resources/Storage-12345678/HandoffCapability"
)

#================================== Skill Triggers ====================================


skill_triggers_handoff = StorageStationSkills.add_collection(
    handoff,
    "SkillTriggers"
)

StorageStationSkills.add_property(
    skill_triggers_handoff,
    "Start",
    "xs:string",
    "start"
)

StorageStationSkills.add_property(
    skill_triggers_handoff,
    "Stop",
    "xs:string",
    "stop"
)

StorageStationSkills.add_property(
    skill_triggers_handoff,
    "Reset",
    "xs:string",
    "reset"
)

StorageStationSkills.add_property(
    skill_triggers_handoff,
    "Abort",
    "xs:string",
    "abort"
)

StorageStationSkills.add_property(
    skill_triggers_handoff,
    "Clear",
    "xs:string",
    "Clear"
)

StorageStationSkills.add_property(
    skill_triggers_handoff,
    "Hold",
    "xs:string",
    "hold"
)

StorageStationSkills.add_property(
    skill_triggers_handoff,
    "Unhold",
    "xs:string",
    "unhold"
)

StorageStationSkills.add_property(
    skill_triggers_handoff,
    "Suspend",
    "xs:string",
    "suspend"
)

StorageStationSkills.add_property(
    skill_triggers_handoff,
    "Unsuspend",
    "xs:string",
    "unsuspend"
)


#================================== Actors =========================================


actors_handoff = StorageStationSkills.add_collection(
    handoff,
    "Actors"
)

StorageStationSkills.add_property(
    actors_handoff,
    "Actor1",
    "xs:string",
    "UR5"
)



#========================================================================================
#================================== Store Skill =========================================
#========================================================================================


store = StorageStationSkills.add_collection(
    root,
    "Store"
)


#================================== Capability Reference ===============================


StorageStationSkills.add_reference_element(
    handoff,
    "CapabilityReference",
    "https://aausmartlab.org/Shells/Resources/Storage-12345678/StoreCapability"
)

#================================== Skill Triggers ====================================


skill_triggers_store = StorageStationSkills.add_collection(
    store,
    "SkillTriggers"
)

StorageStationSkills.add_property(
    skill_triggers_store,
    "Start",
    "xs:string",
    "start"
)

StorageStationSkills.add_property(
    skill_triggers_store,
    "Stop",
    "xs:string",
    "stop"
)

StorageStationSkills.add_property(
    skill_triggers_store,
    "Reset",
    "xs:string",
    "reset"
)

StorageStationSkills.add_property(
    skill_triggers_store,
    "Abort",
    "xs:string",
    "abort"
)

StorageStationSkills.add_property(
    skill_triggers_store,
    "Clear",
    "xs:string",
    "Clear"
)

StorageStationSkills.add_property(
    skill_triggers_store,
    "Hold",
    "xs:string",
    "hold"
)

StorageStationSkills.add_property(
    skill_triggers_store,
    "Unhold",
    "xs:string",
    "unhold"
)

StorageStationSkills.add_property(
    skill_triggers_store,
    "Suspend",
    "xs:string",
    "suspend"
)

StorageStationSkills.add_property(
    skill_triggers_store,
    "Unsuspend",
    "xs:string",
    "unsuspend"
)

#================================== Actors =========================================


actors_store = StorageStationSkills.add_collection(
    store,
    "Actors"
)

StorageStationSkills.add_property(
    actors_store,
    "Actor1",
    "xs:string",
    "UR5"
)
