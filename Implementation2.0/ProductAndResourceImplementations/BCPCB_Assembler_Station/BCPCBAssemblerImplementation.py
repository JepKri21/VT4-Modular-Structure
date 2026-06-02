#This should first create the shell and submodels from the yaml files and publish them to the server.

#It should also contain the PackML implementation, aka, this should be the main script for this resource


import asyncio
import time
import random
import sys
from pathlib import Path
import json
from datetime import datetime
from math import ceil
import basyx.aas.adapter.json

script_dir = Path(__file__).parent

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from ClassesAndBuilderMethods.MQTT.ResourceMQTT import MQTTClientResource
from ClassesAndBuilderMethods.PackML.PackMLMachineClass import StationBehavior, PackMLState,PackMLStateMachine 
from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS
from ClassesAndBuilderMethods.BaSyx_AAS_Generator import yaml_to_instance, yaml_to_shell

BROKER = "localhost"
MQTT_PORT = 1883
BASE_TOPIC = "AAUSmartLab/ProductionLine1" 

AAS_PORT = "8081"
SERVER_BASE = f"http://{BROKER}:{AAS_PORT}"  # your server base URL
SUBMODEL_ENDPOINT = f"{SERVER_BASE}/submodels"
SHELL_ENDPOINT = f"{SERVER_BASE}/shells"

#=============== UPLOADING SHELL ======================
shell = yaml_to_shell.load_shell_from_yaml(f"{script_dir}/Shell.yaml")
json_str = json.dumps(shell,cls=basyx.aas.adapter.json.AASToJsonEncoder,indent=2,ensure_ascii=False)
result = yaml_to_shell.upload_shell(json_str, SERVER_BASE)
print(result)  # "created" or "updated"

json_shell = json.loads(json_str)
CLIENT_ID = json_shell["idShort"]

#=============== UPLOADING SUBMODELS ======================

builder = yaml_to_instance.load_instance_from_yaml(f"{script_dir}/Communication.yaml")
json_str = json.dumps(builder.get(),cls=basyx.aas.adapter.json.AASToJsonEncoder,indent=2,ensure_ascii=False,)
result = yaml_to_instance.upload_submodel(json_str, SERVER_BASE)
print(result)  # "created" or "updated"

json_submodel = json.loads(json_str)
mqtt_key = MS.find_by_idshort(json_submodel["submodelElements"],"MQTT")
suffixes = MS.find_by_idshort(mqtt_key["value"], "Suffixes")

# Step 3: Find specific suffixes
command_suffix = MS.find_by_idshort(suffixes["value"],"CommandSuffix")["value"]
state_suffix = MS.find_by_idshort(suffixes["value"],"StateSuffix")["value"]
job_result_suffix = MS.find_by_idshort(suffixes["value"],"JobResultSuffix")["value"]
info_request_suffix = MS.find_by_idshort(suffixes["value"],"InfoRequestSuffix")["value"]
resource_ack_suffix = MS.find_by_idshort(suffixes["value"],"ResourceAcknowledgementSuffix")["value"]
controller_ack_suffix = MS.find_by_idshort(suffixes["value"],"ControllerAcknowledgementSuffix")["value"]
inventory_suffix = MS.find_by_idshort(suffixes["value"],"InventoryLevelSuffix")["value"]


builder = yaml_to_instance.load_instance_from_yaml(f"{script_dir}/AssemblyCapabilityOffered.yaml")
json_str = json.dumps(builder.get(),cls=basyx.aas.adapter.json.AASToJsonEncoder,indent=2,ensure_ascii=False,)
result = yaml_to_instance.upload_submodel(json_str, SERVER_BASE)
print(result)  # "created" or "updated"

builder = yaml_to_instance.load_instance_from_yaml(f"{script_dir}/HandoffCapabilityOffered.yaml")
json_str = json.dumps(builder.get(),cls=basyx.aas.adapter.json.AASToJsonEncoder,indent=2,ensure_ascii=False,)
result = yaml_to_instance.upload_submodel(json_str, SERVER_BASE)
print(result)  # "created" or "updated"

builder = yaml_to_instance.load_instance_from_yaml(f"{script_dir}/Skills.yaml")
json_str = json.dumps(builder.get(),cls=basyx.aas.adapter.json.AASToJsonEncoder,indent=2,ensure_ascii=False,)
result = yaml_to_instance.upload_submodel(json_str, SERVER_BASE)
print(result)  # "created" or "updated"

builder = yaml_to_instance.load_instance_from_yaml(f"{script_dir}/ResourceZones.yaml")
json_str = json.dumps(builder.get(),cls=basyx.aas.adapter.json.AASToJsonEncoder,indent=2,ensure_ascii=False,)
result = yaml_to_instance.upload_submodel(json_str, SERVER_BASE)
print(result)  # "created" or "updated"

builder = yaml_to_instance.load_instance_from_yaml(f"{script_dir}/Inventory.yaml")
json_str = json.dumps(builder.get(),cls=basyx.aas.adapter.json.AASToJsonEncoder,indent=2,ensure_ascii=False,)
result = yaml_to_instance.upload_submodel(json_str, SERVER_BASE)
print(result)  # "created" or "updated"

Actor = "KUKAManipulator"

mqtt_client = MQTTClientResource(BROKER, MQTT_PORT, CLIENT_ID, BASE_TOPIC)


resource_inventories = {
    "Inventory_1": 
    {
        "InventorySize": 10,
        "SupportedComponents": 
        [
           "https://aausmartlab.org/Shells/Component/PCB"
        ],
        "AccessibleActors" : [Actor],
        "Storage" : 
        {
            "position1": "",
            "position2": "",
            "position3": "",
            "position4": "",
            "position5": "",
            "position6": "https://aausmartlab.org/Shells/Component/PCB/PCBFuseBoxA-6c0758ad-986a-447d-a2b7-72a0a9eb1f2c",
            "position7": "https://aausmartlab.org/Shells/Component/PCB/PCBFuseBoxA-d362b1f2-89f6-4173-88b6-fcb837560e20",
            "position8": "",
            "position9": "",
            "position10": ""
        }
    }
}

def build_inventory(resource_inventories):

    inventory_models = {}

    for inventory_name, inventory_data in (
        resource_inventories.items()
    ):

        # =====================================
        # Convert storage slots
        # =====================================
        storage_models = {}

        for position, component_id in (
            inventory_data["Storage"].items()
        ):

            if component_id == "":
                component_id = None

            storage_models[position] = (
                MS.InventorySlot(
                    component_id=component_id
                )
            )

        # =====================================
        # Build InventoryData model
        # =====================================
        inventory_models[inventory_name] = (
            MS.InventoryData(
                inventory_size=inventory_data[
                    "InventorySize"
                ],

                supported_components=inventory_data[
                    "SupportedComponents"
                ],

                accessible_actors=inventory_data[
                    "AccessibleActors"
                ],

                storage=storage_models
            )
        )

    # =========================================
    # Build final InventoryLevelMessage
    # =========================================
    return inventory_models


def find_positions(inventories, query):
    results = []

    for inv_name, inv_data in inventories.items():
        storage = inv_data.get("Storage", {})

        for position, item in storage.items():
            if not item:
                continue

            # Case 1: exact match (specific ID)
            if item == query:
                results.append({
                    "inventory": inv_name,
                    "position": position,
                    "item": item
                })

            # Case 2: type match (base URL)
            elif item.startswith(query + "/"):
                results.append({
                    "inventory": inv_name,
                    "position": position,
                    "item": item
                })

    return results


def find_available_slots(inventories, query):
    results = {}

    # --- Extract base reference ---
    parts = query.rstrip("/").split("/")

    if "-" in parts[-1]:
        # Has ID → remove last part
        base_ref = "/".join(parts[:-1])
    else:
        # Already a base reference
        base_ref = query.rstrip("/")

    # --- Search inventories ---
    for inv_name, inv_data in inventories.items():
        supported = inv_data.get("SupportedComponents", [])

        # ✅ Compare full reference, not just name
        if base_ref not in supported:
            continue

        storage = inv_data.get("Storage", {})

        free_positions = [
            pos for pos, val in storage.items() if not val
        ]

        if free_positions:
            results[inv_name] = free_positions

    return results


def place_item(inventories, item_url):
    slots = find_available_slots(inventories, item_url)

    for inv_name, positions in slots.items():
        pos = positions[0]  # take first free slot
        inventories[inv_name]["Storage"][pos] = item_url

        return {
            "inventory": inv_name,
            "position": pos
        }

    return None  # no space available



class KUKAManipulatorBehavior(StationBehavior):

    def __init__(self, actor_name: str, mqtt_client):
        # Station-specific variables live HERE
        self.mqtt_client = mqtt_client
        self.actor_name = actor_name

        self.command_payload = None
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None
        self.retrived_item_component = None
        

    async def idle(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.IDLE)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Assembler Is Idle")

    async def starting(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.STARTING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        self.skill = self.command_payload.skill
        self.parameters = self.command_payload.parameters
        self.process_transformation = self.command_payload.process_transformation
        print(f"Reading job {self.command_payload.job_id} for order {self.command_payload.order_id}")


        if self.skill == "Handoff":
            if self.parameters is None:
                raise ValueError("No parameters provided for Handoff skill")
            try:
                #Loading handoff specific parameters
                self.target_position = self.parameters.get("TargetPosition")
                self.XPos = self.target_position.get("XPos")
                self.YPos = self.target_position.get("YPos")
                print("Handoff parameters loaded:", self.parameters)
            except Exception as e:
                print(f"Failed to load the parameters with exception {e}")


        elif self.skill == "BCPCBAssembly":

            if self.parameters is None:
                raise ValueError("No parameters provided for Assemble skill")
            try:
                # Loading Assemble Parameters
                self.target_position = self.parameters.get("TargetPosition") or {}
                self.XPos = self.target_position.get("XPos")
                self.YPos = self.target_position.get("YPos")
                print("Assemble parameters loaded:", self.parameters)
            except Exception as e:
                print(f"Failed to load the parameters with exception {e}")


        else:
            print("Skill not available for this Actor")
            #If we are told to do a skill we cannot, we stop the action
            #We will then need to reset automatically, but only when stopped like this
            await machine.transition_to(PackMLState.STOPPING)

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def execute(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.EXECUTE)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)

        if self.skill == "Handoff":
            if self.process_transformation["InputTypes"] is not None:
                print(f"Receiving {self.process_transformation["InputTypes"]} as handoff.")
            elif self.process_transformation["OutputTypes"] is not None:
                print(f"Providing {self.process_transformation["OutputTypes"]} as handoff.")

            print(f"At position ({self.XPos},{self.YPos})")
            self.ideal_cycle_time = 4000+int(self.XPos)+int(self.YPos)
            self.actual_cycle_time = self.ideal_cycle_time + random.randint(200,800)
            await asyncio.sleep(self.actual_cycle_time/1000)

            self.result = MS.Result.COMPLETE
            self.quality = MS.Quality.GOOD

            
        elif self.skill == "BCPCBAssembly":
            transformation_allowed = False
            print(f"Executing Assemble to perform this Process Transformation: {self.process_transformation}")
            print(f"With these parameters: XPos: {self.XPos}, YPos: {self.YPos}")
            
            pcb_input = next(
                (x for x in self.process_transformation["InputTypes"]
                 if x.startswith("https://aausmartlab.org/Shells/Component/PCB")),
                None
            )

            bottom_cover_input = next(
                (x for x in self.process_transformation["InputTypes"]
                 if x.startswith("https://aausmartlab.org/Shells/Component/BottomCover")),
                None
            )

            bottom_cover_pcb_output = next(
                (x for x in self.process_transformation["OutputTypes"]
                 if x.startswith("https://aausmartlab.org/Shells/Assembly/BottomCoverPCB")),
                None
            )

            if pcb_input and bottom_cover_input and bottom_cover_pcb_output and len(self.process_transformation["InputTypes"]) == 2 and len(self.process_transformation["OutputTypes"]) == 1:
                print(f"The requested process transformation is supported")
                transformation_allowed = True
            else:
                print(f"The requested {self.process_transformation} process transformation is not supported")
                self.result = MS.Result.INCOMPLETE
                self.quality = MS.Quality.NA

            if transformation_allowed:
                retriveable_locations = find_positions(inventories=resource_inventories,query=pcb_input)

                if not retriveable_locations:
                    print(f"Requested PCB is not in storage")
                    self.result = MS.Result.INCOMPLETE
                    self.quality = MS.Quality.NA
                    self.process_transformation["OutputTypes"] = None
                else:
                    retrieved_item = retriveable_locations[0]  # We just take the first one
                    inventory_name = retrieved_item["inventory"]
                    position = retrieved_item["position"]
                    self.retrieved_item_component = retrieved_item["item"]

                    # Generating cycle times (ms) based on parameters
                    self.ideal_cycle_time = 8000
                    self.actual_cycle_time = self.ideal_cycle_time + random.randint(200,1500)
                    await asyncio.sleep(self.actual_cycle_time/1000)

                    # Generating result and quality randomly. Only clear the
                    # inventory slot when the assembly actually succeeded —
                    # otherwise the part stays available for a retry / the
                    # next order.
                    if random.randint(1,100) > 1:
                        self.result = MS.Result.COMPLETE
                        if random.randint(1,100) > 1:
                            self.quality = MS.Quality.GOOD
                        else:
                            self.quality = MS.Quality.BAD
                        resource_inventories[inventory_name]["Storage"][position] = ""
                    else:
                        self.result = MS.Result.INCOMPLETE
                        self.quality = MS.Quality.NA
                        self.process_transformation["OutputTypes"] = None

        else:
            print("This is not a skill of the actor, How did you even get here?")
            await machine.transition_to(PackMLState.STOPPING)
        
        await machine.transition_to(PackMLState.COMPLETING)

    async def completing(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.COMPLETING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Finalizing Process and sending result")

        if self.skill == "BCPCBAssembly":
            XPos_element = MS.PropertyElement(id_short="XPos", value=self.XPos, semantic_id="https://aausmartlab.org/Semantics/mm")
            YPos_element = MS.PropertyElement(id_short="YPos", value=self.YPos, semantic_id="https://aausmartlab.org/Semantics/mm")
            target_position_element = MS.CollectionElement(id_short="TargetPosition", semantic_id="https://aausmartlab.org/Semantics/TargetPositon", elements=[XPos_element,YPos_element])
            used_parameters = MS.CollectionElement(id_short="Parameters", semantic_id="https://aausmartlab.org/Semantics/Parameters", elements=[target_position_element])

            job_result_message = MS.JobResultMessage(
                timestamp=datetime.now(),
                resource_id=CLIENT_ID, 
                order_id=self.command_payload.order_id, 
                job_id=self.command_payload.job_id, 
                ideal_cycle_time_ms=self.ideal_cycle_time,
                actual_cycle_time_ms=self.actual_cycle_time,
                process_transformation=self.process_transformation,
                result=self.result,
                quality=self.quality,
                output_parameters=used_parameters
            )

        elif self.skill == "Handoff":
            XPos_element = MS.PropertyElement(id_short="XPos", value=self.XPos, semantic_id="https://aausmartlab.org/Semantics/mm")
            YPos_element = MS.PropertyElement(id_short="YPos", value=self.YPos, semantic_id="https://aausmartlab.org/Semantics/mm")
            target_position_element = MS.CollectionElement(id_short="TargetPosition", semantic_id="https://aausmartlab.org/Semantics/TargetPositon", elements=[XPos_element,YPos_element])
            used_parameters = MS.CollectionElement(id_short="Parameters", semantic_id="https://aausmartlab.org/Semantics/Parameters", elements=[target_position_element])

            job_result_message = MS.JobResultMessage(
                timestamp=datetime.now(),
                resource_id=CLIENT_ID, 
                order_id=self.command_payload.order_id, 
                job_id=self.command_payload.job_id, 
                ideal_cycle_time_ms=self.ideal_cycle_time,
                actual_cycle_time_ms=self.actual_cycle_time,
                process_transformation=self.process_transformation,
                result=self.result,
                quality=self.quality,
                output_parameters=used_parameters
            )
        

        self.mqtt_client.publish(f"{job_result_suffix}/{self.actor_name}",job_result_message)
        inventory_build = build_inventory(resource_inventories)
        inventory_message = MS.InventoryLevelMessage(timestamp=datetime.now(), resource_id=CLIENT_ID,inventory=inventory_build)
        self.mqtt_client.publish(f"{inventory_suffix}", inventory_message)

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.COMPLETE)

    async def resetting(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.RESETTING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Resetting Assembler")

        self.command_payload = None
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None
        self.process_transformation = None
        self.XPos = None
        self.YPos = None
        self.target_position = None

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.IDLE)

    async def stopping(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.STOPPING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Stopping Assembler")

        #Stop command, should maybe just wait like 2 seconds
        
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)
        
    async def holding(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.HOLDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Holding Assembler")

        # Why holding? Maybe not relevant at the moment

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.HELD)
    
    async def unholding(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.UNHOLDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Unholding Assembler")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def suspending(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.SUSPENDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Suspending Assembler")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.SUSPENDED)

    async def unsuspending(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.UNSUSPENDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Unsuspending Assembler")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def aborting(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.ABORTING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Aborting Assembler")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.ABORTED)

    async def clearing(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.CLEARING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Clearing Assembler")

        self.command_payload = None
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)


#=============
# Generating Actors from their behavior
#=============

KR_Agilus_behavior = KUKAManipulatorBehavior(Actor,mqtt_client)
KR_Agilus = PackMLStateMachine(KR_Agilus_behavior)

StateMachines = [KR_Agilus]

main_loop: asyncio.AbstractEventLoop | None = None

#=============
#Creating handlers for subscribers 
#=============

def handle_command(msg: MS.CommandMessage):
    print(f"Received trigger: {msg.skill_trigger}")
    print(f"Skill: {msg.skill}")
    print(f"Actor: {msg.actor_name}")
    print(f"Order ID: {msg.order_id}")
    print(f"Parameters: {msg.parameters}")

    for StateMachine in StateMachines:
        if msg.actor_name == StateMachine.behavior.actor_name:
            StateMachine.behavior.command_payload = msg
            if main_loop is None:
                print("Event loop not ready; dropping command")
                return
            asyncio.run_coroutine_threadsafe(
                StateMachine.state_command_callback(msg.skill_trigger),
                main_loop,
            )



def handle_request(msg: MS.RequestMessage):
    print(f"Topic to update: {msg.requested_topic_update}")
    elements = msg.requested_topic_update.split("/")

    #Checking if the request is for the state
    if state_suffix in elements:

        for StateMachine in StateMachines:
            state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=StateMachine.state)
            mqtt_client.publish(f"{state_suffix}/{StateMachine.behavior.actor_name}", state_message)
            

    #Checking if the request is for the inventory level
    elif inventory_suffix in elements:
        #We could also send a list of all unique ids in the storage, allowing the controller to at least see and choose a specific one
        inventory_build = build_inventory(resource_inventories)
        inventory_message = MS.InventoryLevelMessage(timestamp=datetime.now(), resource_id=CLIENT_ID,inventory=inventory_build)
        mqtt_client.publish(f"{inventory_suffix}", inventory_message)
        

    else:
        print("Unable to find the requested topic, we are not yet sending an error message back")




#=============
#Registering those handlers to specific topics
#=============

mqtt_client.register_subscriber(command_suffix, MS.CommandMessage,handle_command)
mqtt_client.register_subscriber(info_request_suffix, MS.RequestMessage,handle_request)

params = {"TargetPosition": {"XPos": 80.0, "YPos": 40.0}}

test_command = MS.CommandMessage(
    timestamp=datetime.now(),
    resource_id=CLIENT_ID,
    skill="Assemble",
    actor_name=Actor,
    skill_trigger=MS.CommandType.START,
    process_transformation={"InputTypes": ["https://aausmartlab.org/Shells/Component/BottomCover/BottomCoverPLABlue-264a4570-0bfb-4171-bdf8-5ed087afd73e", "https://aausmartlab.org/Shells/Component/PCB/PCB_213fasd-0bfb-4171-bdf8-5ed087afd73e"],
                            "OutputTypes": ["https://aausmartlab.org/Shells/Assembly/BottomCoverPCB/BottomCoverPCB-as734bld-0bfb-4171-bdf8-5ed087afd73e"]},
    order_id="ORD-1",
    job_id="1xx23",
    parameters=params
)


print("Test Command: ", test_command.model_dump_json(indent=2))

#=============
#Main loop where the full machine runs
#=============

async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()

    mqtt_client.start_mqtt_connection()
    
    #machine.active_alarms = [51,62]
    # Keep machine alive forever
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())