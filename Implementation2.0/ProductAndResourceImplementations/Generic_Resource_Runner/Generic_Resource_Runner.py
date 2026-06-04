#This should be a class that is able to run and keep track of multiple resources. It should have functions to add a resource, based on shell id
# and a function for starting that resource and one for terminating the resource.
import sys
from pathlib import Path
import time
import asyncio
from datetime import datetime
import random
import requests
import json
import Generic_Resource_Models as GRM
from Generic_Resource_Submodel_Parser import ResourceParser, AASResourceLoader

script_dir = Path(__file__).parent

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from ClassesAndBuilderMethods.MQTT.ResourceMQTT import MQTTClientResource
from ClassesAndBuilderMethods.PackML.PackMLMachineClass import StationBehavior, PackMLState,PackMLStateMachine 
from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS

#====== JUST FOR TESTING=========
BROKER = "localhost"
AAS_PORT = "8081"
SERVER_BASE = f"http://{BROKER}:{AAS_PORT}"  # your server base URL
SUBMODEL_ENDPOINT = f"{SERVER_BASE}/submodels"
SHELL_ENDPOINT = f"{SERVER_BASE}/shells"
#====== JUST FOR TESTING=========

class GenericResourceExecutor:

    def __init__(self, SERVER_BASE, SUBMODEL_ENDPOINT, SHELL_ENDPOINT, resource_shell_id):
        self.server_base = SERVER_BASE
        self.submodel_endpoint = SUBMODEL_ENDPOINT
        self.shell_endpoint = SHELL_ENDPOINT
        self.resource_shell_id = resource_shell_id
        self.resource_loader = AASResourceLoader(self.server_base, self.submodel_endpoint, self.shell_endpoint)
        self.resource_parser = ResourceParser()
        self.loaded_raw_resource = self.resource_loader.load(self.resource_shell_id)
        self.parsed_resource = self.resource_parser.parse(self.loaded_raw_resource)
        self.shell_id_short = None
        self.main_loop = None
        self.skill_executor = None
        self.actors = {}

        self.inventory_manager = InventoryManager(self.resource_loader,self.resource_parser,self.resource_shell_id,self.submodel_endpoint)

        self.refresh_resource()
        self.wait_for_communication_configuration()

        
    def attach_event_loop(self, loop):
        self.main_loop = loop

    def refresh_resource(self):

        raw_shell = self.resource_loader.read_shell(self.resource_shell_id)
        self.shell_id_short = raw_shell.id_short

        self.loaded_raw_resource = self.resource_loader.load(self.resource_shell_id)

        self.parsed_resource = self.resource_parser.parse(self.loaded_raw_resource)

    def wait_for_communication_configuration(self):
        while True:
            try:
                self.refresh_resource()
                communication = self.parsed_resource.get("Communication")
                if communication is None:
                    raise ValueError("Communication submodel not found")

                prefix = communication.production_line_prefix
                broker = communication.broker_id
                port = communication.broker_port

                if (prefix is not None and broker is not None and port is not None):
                    break

                print(
                    f"[{self.resource_shell_id}] "
                    f"Waiting for MQTT configuration..."
                )

            except Exception as e:

                print(
                    f"[{self.resource_shell_id}] "
                    f"Failed loading communication settings: {e}"
                )

            time.sleep(10)

        self.initialize_mqtt()

    def initialize_mqtt(self):

        communication = self.parsed_resource["Communication"]

        self.mqtt_client = MQTTClientResource(
            communication.broker_id,
            communication.broker_port,
            self.shell_id_short,
            communication.production_line_prefix,
        )
        self.register_mqtt_handlers()

        self.mqtt_client.start_mqtt_connection()

        print(f"[{self.resource_shell_id}] Connected to MQTT broker")

        # 🔥 THIS IS THE KEY ADDITION
        self.initialize_runtime()

    def register_mqtt_handlers(self):

        suffixes = self.parsed_resource["Communication"].suffixes

        self.mqtt_client.register_subscriber(
            suffixes.command_suffix,
            MS.CommandMessage,
            self.handle_command,
        )

        self.mqtt_client.register_subscriber(
            suffixes.info_request_suffix,
            MS.RequestMessage,
            self.handle_request,
        )

    def handle_command(self, msg: MS.CommandMessage):
    
        try:
            print(
                f"Received command "
                f"{msg.skill} "
                f"for actor "
                f"{msg.actor_name}"
            )
    
            actor_entry = self.actors.get(msg.actor_name)
    
            if not actor_entry:
                print(f"Unknown actor: {msg.actor_name}")
                return
    
            machine = actor_entry["machine"]
            behavior = actor_entry["behavior"]
    
            context = self.skill_executor.build_skill_context(
                msg.skill,
                msg
            )
    
            behavior.apply_context(context)
    
            asyncio.run_coroutine_threadsafe(
                machine.state_command_callback(msg.skill_trigger),
                self.main_loop
            )
    
        except Exception as e:
            print(f"[MQTT HANDLE_COMMAND ERROR] {e}")
    
    def handle_request(self, msg: MS.RequestMessage):
        print(f"Received request for "f"{msg.requested_topic_update}")

        # State and inventory responses
        # come later


    def initialize_runtime(self):

        # 1. Skill executor (shared across actors)
        self.skill_executor = SkillExecutor(self.parsed_resource)

        skills = self.parsed_resource["Skills"].skills

        # 2. Extract unique actors
        actor_set = set()

        for skill in skills.values():
            for actor in skill.actors:
                actor_set.add(actor)

        print(f"Detected actors: {actor_set}")

        # 3. Create behavior + state machine per actor
        for actor_name in actor_set:

            behavior = GenericStationBehavior(
                resource_id_short=self.shell_id_short,
                actor_name=actor_name,
                mqtt_client=self.mqtt_client,
                suffixes=self.parsed_resource["Communication"].suffixes,
                resource_id=self.resource_shell_id,
                inventory_manager=self.inventory_manager
            )

            machine = PackMLStateMachine(behavior)

            self.actors[actor_name] = {
                "behavior": behavior,
                "machine": machine
            }

        print(f"[{self.resource_shell_id}] Runtime initialized with {len(self.actors)} actors")
    

class SkillExecutionContext:
    def __init__(self):
        self.skill_name = None
        self.skill = None

        self.capability = None
        self.process_transformation = None

        self.command = None

        # normalized validated parameters (flat or nested but clean)
        self.parameters = {}

        # precomputed execution metadata
        self.input_types = None
        self.output_types = None


class SkillExecutor:

    def __init__(self, parsed_resource):
        self.resource = parsed_resource
        self.skills = parsed_resource["Skills"].skills

    # ---------------------------
    # Skill resolution
    # ---------------------------
    def get_skill(self, skill_name: str):
        return self.skills.get(skill_name)

    def get_capability(self, skill: str):
        skill_obj = self.get_skill(skill)
        if not skill_obj:
            return None

        cap_id = skill_obj.capability.capability_type_id

        for value in self.resource.values():
            if hasattr(value, "capability_type") and value.capability_type == cap_id:
                return value

        return None

    # ---------------------------
    # Process transformation matching
    # (STRICT set equality, no subset logic)
    # ---------------------------
    def match_process_transformation(self, capability, command_pt):
        if not capability:
            return None

        cmd_in = command_pt.get("InputTypes") or []
        cmd_out = command_pt.get("OutputTypes") or []

        for pt in capability.process_transformations.values():

            cap_inputs = pt.input_types
            cap_outputs = pt.output_types

            if self._types_match(cap_inputs, cmd_in) and self._types_match(cap_outputs, cmd_out):
                return pt

        return None

    def _types_match(self, capability_types, command_types):
        """
        Each capability type must match at least one command type
        via prefix matching.
        """

        for cap_type in capability_types:
            matched = False

            for cmd_type in command_types:
                if cmd_type.startswith(cap_type):
                    matched = True
                    break

            if not matched:
                return False

        return True

    # ---------------------------
    # Parameter validation
    # supports:
    # - flat params
    # - nested collections
    # - range constraints
    # ---------------------------
    def validate_parameters(self, capability, parameters: dict):

        if not capability.parameters:
            return {}

        validated = {}

        for name, definition in capability.parameters.items():

            if name not in parameters:
                raise ValueError(f"Missing parameter: {name}")

            value = parameters[name]

            # -------------------
            # Collection parameter
            # -------------------
            if getattr(definition, "parameter_type", None) == "Collection":

                result = {}

                for sub_name, sub_def in definition.parameters.items():

                    if sub_name not in value:
                        raise ValueError(f"Missing sub-parameter: {sub_name}")

                    sub_value = value[sub_name]

                    # range validation if exists
                    if hasattr(sub_def, "min_value") and hasattr(sub_def, "max_value"):
                        if not (sub_def.min_value <= sub_value <= sub_def.max_value):
                            raise ValueError(
                                f"{sub_name} out of range: {sub_value}"
                            )

                    result[sub_name] = sub_value

                validated[name] = result

            # -------------------
            # Flat parameter
            # -------------------
            else:

                # range validation for flat
                if hasattr(definition, "min_value") and hasattr(definition, "max_value"):
                    if not (definition.min_value <= value <= definition.max_value):
                        raise ValueError(
                            f"{name} out of range: {value}"
                        )

                validated[name] = value

        return validated

    # ---------------------------
    # Build execution context
    # ---------------------------
    def build_skill_context(self, skill_name: str, command):

        context = SkillExecutionContext()
        context.skill_name = skill_name
        context.command = command

        skill = self.get_skill(skill_name)
        capability = self.get_capability(skill_name)

        if not skill or not capability:
            raise ValueError("Skill or capability not found")

        context.skill = skill
        context.capability = capability

        match = self.match_process_transformation(
            capability,
            command.process_transformation
        )

        if not match:
            raise ValueError("No matching process transformation")

        context.process_transformation = match

        context.parameters = self.validate_parameters(
            capability,
            command.parameters or {}
        )

        return context


class InventoryManager:

    STORE_CAPABILITY = "https://aausmartlab.org/Submodels/Capability/Store"
    RETRIEVE_CAPABILITY = "https://aausmartlab.org/Submodels/Capability/Retrieve"

    def __init__(self, resource_loader: AASResourceLoader, resource_parser: ResourceParser, resource_shell_id, submodel_endpoint):
        self.resource_loader = resource_loader
        self.resource_parser = resource_parser
        self.resource_shell_id = resource_shell_id
        self.submodel_endpoint = submodel_endpoint

        self.inventory_parser = None
        self.inventory_model = None
        encoded_id = self.resource_loader._base64encode(f"{resource_shell_id}/Inventory")
        self.inventory_url = f"{self.submodel_endpoint}/{encoded_id}"

    def load(self):
        parsed = self.resource_parser.parse(
            self.resource_loader.load(self.resource_shell_id)
        )

        

        self.inventory_parser = self.resource_parser.get_parser(GRM.SubmodelSemanticIDs.INVENTORY)
        self.inventory_model = parsed["Inventory"]
        #self.inventory_model = self.inventory_parser.parse(parsed["Inventory"])

        #print(f"[PARSED] {self.inventory_model}")

        return self.inventory_model

    def execute_inventory_effect(self, context):

        cap = context.capability.capability_type

        if cap == self.STORE_CAPABILITY:
            return self.store_component(context)

        if cap == self.RETRIEVE_CAPABILITY:
            return self.retrieve_component(context)

    def retrieve_component(self, context):

        component_id = context.command.process_transformation.get("OutputTypes") or []
        if component_id is not []:
            component_id = component_id[0]
        inventory_name, slot_id = self.find_component_slot(component_id)

        self.inventory_parser.update_slot(
            inventory_name=inventory_name,
            slot_id=slot_id,
            component_id=None
        )

        self.upload()

        return component_id

    def store_component(self, context):

        component_id = context.command.process_transformation.get("InputTypes") or []
        if component_id is not []:
            component_id = component_id[0]

        inventory_name, slot_id = self.find_free_slot(component_id)

        self.inventory_parser.update_slot(
            inventory_name=inventory_name,
            slot_id=slot_id,
            component_id=component_id
        )

        self.upload()

        return slot_id

    def find_component_slot(self, component_id):
        model = self.load()

        print(f"[MODEL] {model}")
        print(f"[COMPONENT ID] {component_id}")
        

        for inv_name, inv in model.inventories.items():
            for slot_id, slot in inv.storage.items():
                print(f"[SLOT COMPONENT ID] {slot.component_id}")
                if slot.component_id == component_id:
                    return inv_name, slot_id

        raise ValueError(f"Component not found: {component_id}")

    def find_free_slot(self, component_id):
        model = self.load()

        for inv_name, inv in model.inventories.items():

            supports = any(
                component_id.startswith(s)
                for s in inv.supported_components
            )

            if not supports:
                continue

            for slot_id, slot in inv.storage.items():
                if slot.component_id is None:
                    return inv_name, slot_id

        raise ValueError("No free slot found")

    def upload(self):

        headers = {"Content-Type": "application/json"}

        data = json.dumps(self.inventory_parser.raw_submodel.data).encode("utf-8")

        r = requests.put(self.inventory_url, headers=headers, data=data)

        if r.status_code not in (200, 201, 204):
            raise RuntimeError(r.text)





class GenericStationBehavior(StationBehavior):

    def __init__(self, resource_id_short: str, actor_name: str, mqtt_client, suffixes, resource_id: str, inventory_manager: InventoryManager):
        self.actor_name = actor_name
        self.resource_id_short = resource_id_short
        self.mqtt_client = mqtt_client
        self.suffixes = suffixes
        self.resource_id = resource_id

        self.inventory_manager = inventory_manager

        # execution context (set per job)
        self.context = None

        # runtime outputs (always reset per job)
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None

    # =========================================================
    # CONTEXT INJECTION (THIS is where SkillExecutor connects)
    # =========================================================
    def apply_context(self, context):
        """
        THIS is the ONLY entry point from SkillExecutor → behavior
        """
        self.context = context

        self.skill = context.skill_name
        self.capability = context.capability
        self.process_transformation = context.process_transformation
        self.parameters = context.parameters

    # =========================================================
    # PACKML STATES
    # =========================================================

    async def idle(self, machine):
        msg = MS.StateMessage(
            timestamp=datetime.now(),
            resource_id=self.resource_id,
            state=PackMLState.IDLE
        )
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", msg)
        #print(f"[{self.actor_name}] IDLE")

    async def starting(self, machine):
        msg = MS.StateMessage(
            timestamp=datetime.now(),
            resource_id=self.resource_id_short,
            state=PackMLState.STARTING
        )
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", msg)

        if not self.context:
            raise ValueError("No execution context applied")

        print(f"[{self.actor_name}] STARTING skill={self.skill}")
        print(f"ProcessTransformation={self.context.command.process_transformation}")
        print(f"Parameters={self.parameters}")

        await asyncio.sleep(1)

        await machine.transition_to(PackMLState.EXECUTE)

    async def execute(self, machine):

        #NOTE ==================== NEED SOMETHING TO HANDLE INVENTORIES

        msg = MS.StateMessage(
            timestamp=datetime.now(),
            resource_id=self.resource_id_short,
            state=PackMLState.EXECUTE
        )
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", msg)

        if not self.context:
            raise ValueError("No execution context applied")

        #print(f"[{self.actor_name}] EXECUTING {self.skill}")

        # ===========================
        # GENERIC EXECUTION LOGIC
        # ===========================

        self.inventory_manager.execute_inventory_effect(self.context)

        # Example: derive fake cycle time (replace later with real model)
        base_time = 3000 + len(self.parameters) * 500

        self.ideal_cycle_time = base_time
        self.actual_cycle_time = base_time + random.randint(100, 800)

        await asyncio.sleep(self.actual_cycle_time / 1000)

        self.result = MS.Result.COMPLETE
        self.quality = MS.Quality.GOOD

        await machine.transition_to(PackMLState.COMPLETING)

    async def completing(self, machine):
        msg = MS.StateMessage(
            timestamp=datetime.now(),
            resource_id=self.resource_id_short,
            state=PackMLState.COMPLETING
        )
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", msg)

        #print(f"[{self.actor_name}] COMPLETING")

        # =====================================================
        # BUILD JOB RESULT (YOUR EXACT REQUIRED STRUCTURE)
        # =====================================================

        job_result_message = MS.JobResultMessage(
            timestamp=datetime.now(),
            resource_id=self.resource_id,
            order_id=self.context.command.order_id,
            job_id=self.context.command.job_id,
            ideal_cycle_time_ms=self.ideal_cycle_time,
            actual_cycle_time_ms=self.actual_cycle_time,
            process_transformation=self.context.command.process_transformation,
            result=self.result,
            quality=self.quality,
            output_parameters=self._build_output_parameters()
        )

        self.mqtt_client.publish(
            f"{self.suffixes.job_result_suffix}/{self.actor_name}",
            job_result_message
        )

        await asyncio.sleep(1)
        await machine.transition_to(PackMLState.COMPLETE)

    async def resetting(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=self.resource_id_short, state=PackMLState.RESETTING)
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", state_message)
        print("Resetting Assembler")

        self.capability = None
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None
        self.skill = None
        self.capability = None
        self.process_transformation = None
        self.parameters = None

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.IDLE)

    async def stopping(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=self.resource_id_short, state=PackMLState.STOPPING)
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", state_message)
        print("Stopping")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)

    async def holding(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=self.resource_id_short, state=PackMLState.HOLDING)
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", state_message)
        print("Holding")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.HELD)

    async def unholding(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=self.resource_id_short, state=PackMLState.UNHOLDING)
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", state_message)
        print("Unholding Assembler")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def suspending(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=self.resource_id_short, state=PackMLState.SUSPENDING)
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", state_message)
        print("Suspending Assembler")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.SUSPENDED)

    async def unsuspending(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=self.resource_id_short, state=PackMLState.UNSUSPENDING)
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", state_message)
        print("Unsuspending Assembler")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def aborting(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=self.resource_id_short, state=PackMLState.ABORTING)
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", state_message)
        print("Aborting Assembler")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.ABORTED)

    async def clearing(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=self.resource_id_short, state=PackMLState.CLEARING)
        self.mqtt_client.publish(f"{self.suffixes.state_suffix}/{self.actor_name}", state_message)
        print("Clearing Assembler")

        self.capability = None
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None
        self.skill = None
        self.capability = None
        self.process_transformation = None
        self.parameters = None

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)
    
    # =========================================================
    # OUTPUT PARAMETER BUILDER (THIS IS NOT CORRECT YET)
    # =========================================================
    def _build_output_parameters(self):

        params = self.parameters

        elements = []

        for key, value in params.items():

            # flat parameter
            if not isinstance(value, dict):
                elements.append(
                    MS.PropertyElement(
                        id_short=key,
                        value=value,
                        semantic_id="https://aausmartlab.org/Semantics/mm"
                    )
                )

            # nested parameter (Collection)
            else:
                sub_elements = []

                for sub_key, sub_value in value.items():
                    sub_elements.append(
                        MS.PropertyElement(
                            id_short=sub_key,
                            value=sub_value,
                            semantic_id="https://aausmartlab.org/Semantics/mm"
                        )
                    )

                elements.append(
                    MS.CollectionElement(
                        id_short=key,
                        semantic_id="https://aausmartlab.org/Semantics/Parameters",
                        elements=sub_elements
                    )
                )

        return MS.CollectionElement(
            id_short="Parameters",
            semantic_id="https://aausmartlab.org/Semantics/Parameters",
            elements=elements
        )

CLIENT_ID = "Storage_12345678"
Actor = "UR5"

params = {}

test_command = MS.CommandMessage(
    timestamp=datetime.now(),
    resource_id=CLIENT_ID,
    skill="Retrieve",
    actor_name=Actor,
    skill_trigger=MS.CommandType.START,
    order_id="ORD-12345",
    job_id="Retrieve_Test_001",
    parameters=params,
    process_transformation={
        "InputTypes": [],
        "OutputTypes": [
            "https://aausmartlab.org/Shells/Component/TopCover/TopCoverABSBlack-99ea6008-1829-416b-a1d1-c9bab9700492"
        ]
    }
)

print(test_command.model_dump_json(indent=2))

params = {
    "TargetPosition": {
        "XPos": 20.0,
        "YPos": 10.0
    }
}

test_command = MS.CommandMessage(
    timestamp=datetime.now(),
    resource_id=CLIENT_ID,
    skill="Handoff",
    actor_name=Actor,
    skill_trigger=MS.CommandType.START,
    order_id="ORD-12345",
    job_id="Handoff_Test_001",
    parameters=params,
    process_transformation={
        "InputTypes": [],
        "OutputTypes": [
            "https://aausmartlab.org/Shells/Component/TopCover/SomeID"
        ]
    }
)

print(test_command.model_dump_json(indent=2))



resource_shell_id = "https://aausmartlab.org/Shells/Resources/Transport_12345678"

#resource_executor = GenericResourceExecutor(SERVER_BASE, SUBMODEL_ENDPOINT, SHELL_ENDPOINT, resource_shell_id)

#print(resource_executor.parsed_resource)

resource_executor = None

async def main():
    global resource_executor

    resource_executor = GenericResourceExecutor(SERVER_BASE,SUBMODEL_ENDPOINT,SHELL_ENDPOINT,resource_shell_id)

    loop = asyncio.get_running_loop()
    resource_executor.attach_event_loop(loop)

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())

#resource_executor = GenericResourceExecutor(SERVER_BASE,SUBMODEL_ENDPOINT,SHELL_ENDPOINT,resource_shell_id)

#inventory_parser = resource_executor.resource_parser.get_parser(GRM.SubmodelSemanticIDs.INVENTORY)

#inventory_parser = parser.get_parser(GRM.SubmodelSemanticIDs.INVENTORY)
#component_id = "https://aausmartlab.org/Shells/Component/TopCover/TopCoverABSBlack-NEW" #The one I want to add
#
#inventory_parser.update_slot(inventory_name="Inventory_1",slot_id="SlotEntry_10",component_id=component_id)
#headers = {"Content-Type": "application/json"}
#
#inventory_submodel_data = json.dumps(inventory_parser.raw_submodel.data).encode("utf-8")
#
#response = requests.put(f"{SUBMODEL_ENDPOINT}/aHR0cHM6Ly9hYXVzbWFydGxhYi5vcmcvU2hlbGxzL1Jlc291cmNlcy9TdG9yYWdlXzEyMzQ1Njc4L0ludmVudG9yeQ==", headers=headers, data=inventory_submodel_data)
#
#if response.status_code in (200, 201, 204):
#    print("updated")
#else:
#    raise RuntimeError(f"Upload failed on PUT: {response.status_code} - {response.text}")