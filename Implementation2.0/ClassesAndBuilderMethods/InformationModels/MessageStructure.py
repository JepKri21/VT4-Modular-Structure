import enum
from pydantic import BaseModel, model_validator, field_validator
from uuid import UUID
from datetime import datetime
from typing import List, Dict
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from PackML.PackMLMachineClass import PackMLState

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
    command_type: CommandType
    order_id: str | None
    job_id: str | None
    parameters: Dict[str, str | int | float] | None
    seq_no: int | None = None


#=============================================================================
#=================================== State ===================================
#=============================================================================

#The PackMLState class is in the PackMLMachineClass

class StateMessage(BaseModel):
    timestamp: datetime
    resource_id: str
    state: PackMLState
    seq_no: int | None = None


#=============================================================================
#=================================== Job Result ==============================
#=============================================================================

class Result(enum.Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"

class Quality(enum.Enum):
    GOOD = "GOOD"
    BAD = "BAD"

class JobResultMessage(BaseModel):
    timestamp: datetime
    resource_id: str
    order_id: str
    job_id: str
    ideal_cycle_time_ms: int
    actual_cycle_time_ms: int
    result: Result
    quality: Quality
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


class InventoryLevelMessage(BaseModel):
    timestamp: datetime
    resource_id: str
    inventory: Dict[str, Dict[str,int]] # [Resource, [Component Type, Amount] 
    seq_no: int | None = None
    

#=============================================================================
#============================== Response and Request =========================
#=============================================================================

class StandardRequestType(str, enum.Enum):
    STATE = "STATE"
    ALARMS = "ALARMS"
    INVENTORY_LEVELS = "INVENTORY_LEVELS"

class RequestMessage(BaseModel):
    timestamp: datetime
    requested_data: StandardRequestType
    resource_id: str
    seq_no: int | None = None


class StateResponse(BaseModel):
    state: PackMLState

class AlarmResponse(BaseModel):
    alarm_ids: List[str]

class InventoryResponse(BaseModel):
    inventory: Dict[str, Dict[str, int]]

class ResponseMessage(BaseModel):
    timestamp: datetime
    requested_data: StandardRequestType
    resource_id: str
    data: StateResponse | AlarmResponse | InventoryResponse
    seq_no: int | None = None

    @model_validator(mode="after")
    def validate_data_matches_request(self):
        match self.requested_data:
            case StandardRequestType.STATE:
                if not isinstance(self.data, StateResponse):
                    raise ValueError("STATE request requires StateResponse")
                
            case StandardRequestType.ALARMS:
                if not isinstance(self.data, AlarmResponse):
                    raise ValueError("STATE request requires AlarmResponse")
            
            case StandardRequestType.INVENTORY_LEVELS:
                if not isinstance(self.data, InventoryResponse):
                    raise ValueError("STATE request requires InventoryResponse")
        
        return self




