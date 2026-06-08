from __future__ import annotations
import enum
from pydantic import BaseModel, model_validator, field_validator
from uuid import UUID
from datetime import datetime
from typing import List, Dict, Any, Optional
import sys
from pathlib import Path
import time

#I don't even think we actually use this here anymore
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


#class CommandMessage(BaseModel):
#    timestamp: datetime
#    resource_id: str
#    skill: str
#    actor_name: str
#    skill_trigger: CommandType
#    order_id: str | None
#    job_id: str | None
#    component_reference: str| List[str] | None = None
#    parameters: Dict[str, str | int | float | Dict] | None
#    seq_no: int | None = None

class CommandMessage(BaseModel):
    timestamp: datetime
    resource_id: str
    skill: str
    actor_name: str
    skill_trigger: CommandType
    order_id: str | None
    job_id: str | None
    process_transformation: Dict[str, List[str] | None]
    parameters: Dict[str, str | int | float | Dict] | None
    seq_no: int | None = None
    # Set to True on a retransmission. The original (seq_no, payload) is
    # otherwise byte-for-byte identical to the first attempt. Stations
    # should dedupe based on seq_no + this flag — a retransmission with a
    # seq_no the station has already acted on must be re-ACKed but not
    # re-executed.
    retransmission: bool = False

"""
NOTE that capabilities will require ComponentTypeReferences to check if the capability is compatible
WHILE actual ComponentReferences are required in the command, it has to be full shell ids of the component/assembly/product
ALSO resource require ALL fields defined in the capability to be filled out in the command, both input and output
BELOW are examples of what the process_transformation varaible can look like when sending a command:

Transformations:
    Drilling:
    {
        "InputTypes": ["https://aausmartlab.org/Shells/Component/BottomCover/BottomCover_id"],
        "OutputTypes": ["https://aausmartlab.org/Shells/Component/BottomCover/BottomCover_id"]
    }
    Assemble:
    {
        "InputTypes": ["https://aausmartlab.org/Shells/Component/BottomCover/BottomCover_id", "https://aausmartlab.org/Shells/Component/PCB/PCB_id"],
        "OutputTypes": ["https://aausmartlab.org/Shells/Assembly/BCPCB/BCPCB_id"]
    }
    Retrieve:
    {
        "InputTypes": None,
        "OutputTypes": ["https://aausmartlab.org/Shells/Assembly/BottomCover/BottomCover_id"]
    },
    {
        "InputTypes": None,
        "OutputTypes": ["https://aausmartlab.org/Shells/Assembly/TopCover/TopCover_id"]
    },
    {
        "InputTypes": None,
        "OutputTypes": ["https://aausmartlab.org/Shells/Assembly/BCPCB/BCPCB_id"]
    }
    Transport:
    {
        "InputTypes": ["https://aausmartlab.org/Shells/Component/BottomCover/BottomCover_id"],
        "OutputTypes": ["https://aausmartlab.org/Shells/Assembly/BottomCover/BottomCover_id"]
    },
    {
        "InputTypes": ["https://aausmartlab.org/Shells/Component/TopCover/TopCover_id"],
        "OutputTypes": ["https://aausmartlab.org/Shells/Assembly/TopCover/TopCover_id"]
    },
    {
        "InputTypes": ["https://aausmartlab.org/Shells/Component/BCPCB/BCPCB_id"],
        "OutputTypes": ["https://aausmartlab.org/Shells/Assembly/BCPCB/BCPCB_id"]
    },
    {
        "InputTypes": None,
        "OutputTypes": None
    }
    Store:
    {
        "InputTypes": ["https://aausmartlab.org/Shells/Component/BottomCover/BottomCover_id"],
        "OutputTypes": None
    },
    {
        "InputTypes": ["https://aausmartlab.org/Shells/Component/TopCover/TopCover_id"],
        "OutputTypes": None
    },
    {
        "InputTypes": ["https://aausmartlab.org/Shells/Component/BCPCB/BCPCB_id"],
        "OutputTypes": None
    }
    Handoff:
    IF BOTH RESOURCES HAVE HANDOFF:
    { #This resource currently has the product
        "InputTypes": None,
        "OutputTypes": [https://aausmartlab.org/Shells/Component/BottomCover/BottomCover_id]
    },
    { #This resource currently does NOT have the product
        "InputTypes": [https://aausmartlab.org/Shells/Component/BottomCover/BottomCover_id],
        "OutputTypes": None
    }
    IF RECIEVING RESOURCE HAS HANDOFF:
    { #This resource currently does NOT have the product BUT it has a handoff capability 
        "InputTypes": [https://aausmartlab.org/Shells/Component/BottomCover/BottomCover_id],
        "OutputTypes": None
    }
    IF PROVIDING RESOURCE HAS HANDOFF:
    { #This resource currently has the product AND a handoff capability 
        "InputTypes": None,
        "OutputTypes": [https://aausmartlab.org/Shells/Component/BottomCover/BottomCover_id]
    }



"""


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
    elements: List[PropertyElement | RangeElement | CollectionElement]
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
    ideal_cycle_time_ms: int | None
    actual_cycle_time_ms: int | None
    result: Result
    quality: Quality
    process_transformation: Dict[str, List[str] | None]
    output_parameters: CollectionElement | None = None
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


class AlarmSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AlarmCategory(str, enum.Enum):
    RESOURCE_OFFLINE = "RESOURCE_OFFLINE"
    JOB_INCOMPLETE = "JOB_INCOMPLETE"
    CMD_NO_ACK = "CMD_NO_ACK"
    NO_ALTERNATIVE = "NO_ALTERNATIVE"
    ORDER_RESTARTED = "ORDER_RESTARTED"
    STUCK_CARGO = "STUCK_CARGO"


#=============================================================================
#============================== Performance Metrics ==========================
#=============================================================================

class OrderStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class OrderCompletedMessage(BaseModel):
    """Emitted by the controller when an order leaves the scheduler — either
    after a successful finish or an abort. Consumed by the metrics bridge
    to populate order-level KPIs (throughput, lead time)."""
    timestamp: datetime
    order_id: str
    product_ref: str | None = None
    started_at: datetime
    completed_at: datetime
    status: OrderStatus
    attempt_count: int = 1
    seq_no: int | None = None


#=============================================================================
#============================== Resilience Testing ===========================
#=============================================================================

class TestInjectionCommand(str, enum.Enum):
    DROP_ACKS = "DROP_ACKS"            # drop next N outbound ACKs
    NEXT_INCOMPLETE = "NEXT_INCOMPLETE" # flip the next JobResult to INCOMPLETE
    GO_SILENT = "GO_SILENT"            # suppress all publishes for N seconds


class TestInjectionMessage(BaseModel):
    """Published by the MES dashboard to a station's TestInjection topic to
    deterministically trigger a failure for RR1/RR2/RR3 demos. Stations
    opt in by calling `mqtt_client.enable_fault_injection()` in their
    setup code."""
    timestamp: datetime
    command: TestInjectionCommand
    count: int | None = None       # DROP_ACKS only
    duration_s: int | None = None  # GO_SILENT only
    seq_no: int | None = None


class ReceiveShipmentMessage(BaseModel):
    """Restock notification — published by the MES when an MRP-driven
    purchase order is marked RECEIVED. The destination station appends
    fresh instances to its inventory (one per quantity) and re-publishes
    its InventoryLevel.

    `inventory_name` lets the dashboard target a specific bin in stations
    that maintain more than one (e.g. Storage has Inventory1 for raw
    components and Inventory2 for finished goods). When null, the station
    picks the first inventory whose `SupportedComponents` matches.
    """
    timestamp: datetime
    component_type_iri: str
    quantity: int
    purchase_order_id: int | None = None
    inventory_name: str | None = None
    seq_no: int | None = None


class ControllerAlarmMessage(BaseModel):
    timestamp: datetime
    category: AlarmCategory
    severity: AlarmSeverity
    message: str
    resource_id: str | None = None
    # Per-actor alarms (STUCK_CARGO is the only one today) carry the
    # actor_name so the operator's Resolve action can free the right one
    # via OccupancyManager.clear_stuck.
    actor_name: str | None = None
    order_id: str | None = None
    seq_no: int | None = None
    # When True, this message asks the bridge to mark any *active* alarm
    # matching (category, resource_id, actor_name, order_id) as cleared
    # rather than inserting a new row. Used for auto-clear-on-reconnect, etc.
    cleared: bool = False


#=============================================================================
#============================== Inventory Level ==============================
#=============================================================================

#class ComponentLevel(BaseModel):
#    ComponentReference: str
#    Amount: int
#
#
#class InventoryLevelMessage(BaseModel):
#    timestamp: datetime
#    resource_id: str
#    # Inventory name → list of components
#    inventory: Dict[str, List[str]]
#    # Flat list of all item URLs
#    #AllItems: List[str]
#    seq_no: int | None = None
    
class InventorySlot(BaseModel):
    component_id: str | None

class InventoryData(BaseModel):
    inventory_size: int
    supported_components: list[str]
    accessible_actors: list[str]
    storage: dict[str, InventorySlot]

class InventoryLevelMessage(BaseModel):
    timestamp: datetime
    resource_id: str
    inventory: dict[str, InventoryData]
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


# Published by the Line Controller whenever an actor's physical cargo state
# changes (after Retrieve / Handoff / Store completes). `component_reference`
# is the IRI of the part being carried, or None when the actor was just
# emptied. Actor identity is in the topic path, not the payload — same
# convention as StateMessage / JobResultMessage.
class CargoMessage(BaseModel):
    timestamp: datetime
    resource_id: str
    component_reference: str | None
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


#============================
#ALL FOR THE PRODUCT MATCHER
#============================

# ============================================================
# Indexed Runtime Component
# ============================================================

class IndexedComponent(BaseModel):
    component_id: str

    component_category: str
    component_type: str
    component_instance: str

    component_type_reference: str

    resource_shell_id: str
    inventory_name: str
    slot_id: str

    accessible_actors: List[str]

    reserved: bool = False

# ============================================================
# Normalizing property submodel
# ============================================================
class NormalizedProperty(BaseModel):
    name: str
    semantic_id: str | None
    value: Any
    value_type: str | None
    unit: str | None = None


class PropertyCollection(BaseModel):
    name: str
    semantic_id: str | None
    properties: dict[str, NormalizedProperty]


class ComponentProperties(BaseModel):
    component_id: str
    collections: dict[str, PropertyCollection]

# ============================================================
# Normalizing Requested Properties from Order
# ============================================================

class RequestedProperty(BaseModel):
    name: str
    semantic_id: str | None
    value: Any

class RequestedCollection(BaseModel):
    name: str
    properties: dict[str, RequestedProperty]

class RequestedConstraints(BaseModel):
    ingredient_id: str
    collections: dict[str, RequestedCollection]

# ============================================================
# The Result Of A Property Matching
# ============================================================

class PropertyMatchFailure(BaseModel):
    collection_name: str
    property_name: str
    reason: str
    requested_value: Any | None = None
    actual_value: Any | None = None

class ConstraintMatchResult(BaseModel):
    matches: bool
    matched_properties: list[str]
    failed_properties: list[PropertyMatchFailure]
    missing_properties: list[PropertyMatchFailure]

class ComponentLocation(BaseModel):
    component_id: str
    resource_shell_id: str
    inventory_name: str
    slot_id: str
    actor_names: List[str] | None = None