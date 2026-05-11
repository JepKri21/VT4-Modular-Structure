import enum
from pydantic import BaseModel, model_validator, field_validator
from uuid import UUID
from datetime import datetime
from typing import List, Dict
import sys
from pathlib import Path
import time


sys.path.append(str(Path(__file__).resolve().parent.parent))

#Different between "seq_no: int | None = None" and "seq_no: int | None" is that the first has None as the default, while the second only allows it as a value for the field

#=============================================================================
#=================================== Command =================================
#=============================================================================

class CommandType(str, enum.Enum):
    START = "START"
    STOP = "STOP"
    RESET = "RESET"
    ABORT = "ABORT"
    HOLD = "HOLD"
    CLEAR = "CLEAR"
    SUSPEND = "SUSPEND"
    UNHOLD = "UNHOLD"
    UNSUSPEND = "UNSUSPEND"


class CommandMessage(BaseModel):
    timestamp: datetime
    resource_id: str
    skill: str
    actor_name: str
    skill_trigger: CommandType
    order_id: str | None
    job_id: str | None
    component_reference: str| List[str] | None = None
    parameters: Dict[str, str | int | float | Dict] | None
    seq_no: int | None = None


#=============================================================================
#=================================== State ===================================
#=============================================================================

#The PackMLState class is in the PackMLMachineClass

class PackMLState(enum.Enum):
    # Main states
    IDLE = "IDLE"
    STARTING = "STARTING"
    EXECUTE = "EXECUTE"
    COMPLETING = "COMPLETING"
    COMPLETE = "COMPLETE"
    RESETTING = "RESETTING"

    # Hold states
    HOLDING = "HOLDING"
    HELD = "HELD"
    UNHOLDING = "UNHOLDING"

    # Suspend states
    SUSPENDING = "SUSPENDING"
    SUSPENDED = "SUSPENDED"
    UNSUSPENDING = "UNSUSPENDING"

    # Stop and abort states
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ABORTING = "ABORTING"
    ABORTED = "ABORTED"
    CLEARING = "CLEARING"

class StateMessage(BaseModel):
    timestamp: datetime
    resource_id: str
    state: PackMLState
    seq_no: int | None = None

#=============================================================================
#=================================== Submodel Elements =======================
#=============================================================================

class PropertyElement(BaseModel):
    id_short: str
    value: int | str | float | None
    semantic_id: str | None = None

class RangeElement(BaseModel):
    id_short: str
    min: int | str | float | None
    max: int | str | float | None
    semantic_id: str | None = None

class CollectionElement(BaseModel):
    id_short: str
    elements: List[PropertyElement | RangeElement]
    semantic_id: str | None = None


#=============================================================================
#=================================== Job Result ==============================
#=============================================================================

class Result(enum.Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"

class Quality(enum.Enum):
    GOOD = "GOOD"
    BAD = "BAD"
    NA = "NA"

class JobResultMessage(BaseModel):
    timestamp: datetime
    resource_id: str
    order_id: str
    job_id: str
    ideal_cycle_time_ms: int
    actual_cycle_time_ms: int
    result: Result
    quality: Quality
    component_reference: str | None = None
    output_parameters: Dict[str, str | int | float | Dict] | None = None
    seq_no: int | None = None

#=============================================================================
#============================== Acknowledgement ==============================
#=============================================================================

class AcknowledgementErrorCodes(enum.Enum):
    SEQ_TOO_LOW = "SEQ_TOO_LOW" 
    SEQ_TOO_HIGH = "SEQ_TOO_HIGH" 
    NO_ERROR = "NO_ERROR"
    


class AcknowledgementMessage(BaseModel):
    timestamp: datetime
    error_code: AcknowledgementErrorCodes
    resource_id: str
    seq_no: int | None = None


#=============================================================================
#============================== Alarms =======================================
#=============================================================================

class AlarmsMessage(BaseModel):
    timestamp: datetime
    resource_id: str
    actor_id: str
    alarm_ids: List[str]
    seq_no: int | None = None


#=============================================================================
#============================== Inventory Level ==============================
#=============================================================================

class ComponentLevel(BaseModel):
    ComponentReference: str
    Amount: int


class InventoryLevelMessage(BaseModel):
    timestamp: datetime
    resource_id: str
    
    # Inventory name → list of component summaries
    inventory: Dict[str, List[ComponentLevel]]
    
    # Flat list of all item URLs
    AllItems: List[str]
    
    seq_no: int | None = None
    

#=============================================================================
#============================== Response and Request =========================
#=============================================================================

#We were thinking that it would be smart to simple say that, any controller can request any topic of the resource to be updated 
#(topics which can be found in the communication submodel)
#Also, whenever a request is put through, there will be no direct response, the topic where an update was requested will just be updated
#Then it is up to the controller to reach that topic.
#this means we don't have to define any specific request types and we don't have to make specific structures for EVERY kind of response
#It is already baked into the topic messages that we are sending, using the definitions above.


#class StandardRequestType(str, enum.Enum):
#    STATE = "STATE"
#    ALARMS = "ALARMS"
#    INVENTORY_LEVELS = "INVENTORY_LEVELS"

class RequestMessage(BaseModel):
    timestamp: datetime
    requested_topic_update: str
    resource_id: str
    seq_no: int | None = None


#class StateResponse(BaseModel):
#    state: PackMLState
#
#class AlarmResponse(BaseModel):
#    alarm_ids: List[str]
#
#class InventoryResponse(BaseModel):
#    inventory: Dict[str, Dict[str, int]]
#
#class ResponseMessage(BaseModel):
#    timestamp: datetime
#    requested_data: StandardRequestType
#    resource_id: str
#    data: StateResponse | AlarmResponse | InventoryResponse
#    seq_no: int | None = None
#
#    @model_validator(mode="after")
#    def validate_data_matches_request(self):
#        match self.requested_data:
#            case StandardRequestType.STATE:
#                if not isinstance(self.data, StateResponse):
#                    raise ValueError("STATE request requires StateResponse")
#                
#            case StandardRequestType.ALARMS:
#                if not isinstance(self.data, AlarmResponse):
#                    raise ValueError("STATE request requires AlarmResponse")
#            
#            case StandardRequestType.INVENTORY_LEVELS:
#                if not isinstance(self.data, InventoryResponse):
#                    raise ValueError("STATE request requires InventoryResponse")
#        
#        return self





#=============================================================================
#============================== MES WorkOrder ================================
#=============================================================================

class WorkOrderStatus(str, enum.Enum):
    ACCEPTED    = "ACCEPTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE    = "COMPLETE"
    FAILED      = "FAILED"
    REJECTED    = "REJECTED"
    PENDING     = "PENDING"


class WorkOrderMessage(BaseModel):
    timestamp: datetime
    order_id: str
    priority: int
    issue_date: datetime
    product_reference: str          # AAS IRI of the uploaded final product instance shell
    ingredients: Dict[str, Dict]    # flat: Ingredient_N -> { ComponentReference: <IRI> }
    properties: Dict[str, Dict]     # flat: Ingredient_N -> { MaterialProperties, PhysicalDimensions }
    assemblies: Dict[str, Dict]     # flat: Ingredient_N -> { Ingredients: [dep1, dep2] }
    process_steps: Dict[str, Dict]  # flat: Ingredient_N -> { StepName: { CapabilityReference, ... } }
    seq_no: int | None = None


class WorkOrderStatusMessage(BaseModel):
    timestamp: datetime
    order_id: str
    line_id: str
    status: WorkOrderStatus
    message: str | None = None
    seq_no: int | None = None


#=============================================================================
#============================== Resource Heartbeat ===========================
#=============================================================================

class ResourceReachability(enum.Enum):
    UNREACHABLE = "UNREACHABLE"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"

class OccupancyMessage(BaseModel):
    timestamp: datetime
    job_id: str
    occupied: bool
    resource_id: str
    seq_no: int | None = None



#=============================================================================
#============================== Helpers ======================================
#=============================================================================

#A small helper function to read the json strings:
def find_by_idshort(elements, target):
    for element in elements:
        if element.get("idShort") == target:
            return element
    return None

