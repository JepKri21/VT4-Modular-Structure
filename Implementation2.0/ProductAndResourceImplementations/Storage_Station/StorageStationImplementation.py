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



builder = yaml_to_instance.load_instance_from_yaml(f"{script_dir}/RetrieveCapabilityOffered.yaml")
json_str = json.dumps(builder.get(),cls=basyx.aas.adapter.json.AASToJsonEncoder,indent=2,ensure_ascii=False,)
result = yaml_to_instance.upload_submodel(json_str, SERVER_BASE)
print(result)  # "created" or "updated"

builder = yaml_to_instance.load_instance_from_yaml(f"{script_dir}/HandoffCapabilityOffered.yaml")
json_str = json.dumps(builder.get(),cls=basyx.aas.adapter.json.AASToJsonEncoder,indent=2,ensure_ascii=False,)
result = yaml_to_instance.upload_submodel(json_str, SERVER_BASE)
print(result)  # "created" or "updated"

builder = yaml_to_instance.load_instance_from_yaml(f"{script_dir}/StoreCapabilityOffered.yaml")
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

resource_inventories = {
    "Inventory1": 
    {
        "InventorySize": 10,
        "SupportedComponents": 
        [
           "https://aausmartlab.org/Shells/Component/Bottom_Cover", 
           "https://aausmartlab.org/Shells/Component/Top_Cover"
        ],
        "Storage" : 
        {
            "position1": "https://aausmartlab.org/Shells/Component/Bottom_Cover/Bottom_Cover-BC001",
            "position2": "https://aausmartlab.org/Shells/Component/Bottom_Cover/Bottom_Cover-BC002",
            "position3": "https://aausmartlab.org/Shells/Component/Bottom_Cover/Bottom_Cover-BC003",
            "position4": "https://aausmartlab.org/Shells/Component/Bottom_Cover/Bottom_Cover-BC004",
            "position5": "https://aausmartlab.org/Shells/Component/Top_Cover/Top_Cover-TC001",
            "position6": "https://aausmartlab.org/Shells/Component/Top_Cover/Top_Cover-TC002",
            "position7": "",
            "position8": "",
            "position9": "",
            "position10": ""
        }
    },
    "Inventory2": 
    {
        "InventorySize" : 5,
        "SupportedComponents": 
        [
            "https://aausmartlab.org/Shells/Assembly/Bottom_Cover_Drilled"
        ],   
        "Storage": 
        {
            "position1" : "https://aausmartlab.org/Shells/Assembly/Bottom_Cover_Drilled/Bottom_Cover_Drilled-BCD001",
            "position2" : "",
            "position3" : "",
            "position4" : "",
            "position5" : "",
        }
    }
}


def summarize_inventories(inventories):
    result = {}
    all_items = []

    for inv_name, inv_data in inventories.items():
        storage = inv_data.get("Storage", {})
        counts = {}

        for item in storage.values():
            if not item:
                continue
            
            # Collect full item list
            all_items.append(item)
            
            # Remove unique ID (last part of URL)
            base = item.rsplit("/", 1)[0]
            
            # Count per type
            counts[base] = counts.get(base, 0) + 1

        # Convert counts to list of dicts
        result[inv_name] = [
            {
                "ComponentReference": ref,
                "Amount": amt
            }
            for ref, amt in counts.items()
        ]

    return result, all_items


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


Actor = "UR5"

mqtt_client = MQTTClientResource(BROKER, MQTT_PORT, CLIENT_ID, BASE_TOPIC)




"""
Since there will occasionally be more than 1 actor on a station, it is important to know the different states of each actor individually.
Each actor may also have slightly different implementations of PackML

We think the smartest way would be to setup topics like this:

#========
#STATE
#========

ProductionLine1/Transport-12345678/Data/State/Shuttle1/value
ProductionLine1/Transport-12345678/Data/State/Shuttle2/value
Contoller subscribes to ProductionLine1/Transport-12345678/Data/State/+/value

#========
#COMMAND
#========

ProductionLine1/Transport-12345678/Data/CMD/Shuttle1/value
ProductionLine1/Transport-12345678/Data/CMD/Shuttle2/value
Resoruce subscribes to ProductionLine1/Transport-12345678/Data/CMD/+/value

OR MAYBE IT IS BETTER TO:

ProductionLine1/Transport-12345678/Data/CMD/value           #CMD message specifies the actor
Resoruce subscribes to ProductionLine1/Transport-12345678/Data/CMD/value

#========
#JOBRESULT
#========

ProductionLine1/Transport-12345678/Data/JobResult/Shuttle1/value
ProductionLine1/Transport-12345678/Data/JobResult/Shuttle2/value
Controller subscribes to ProductionLine1/Transport-12345678/Data/JobResult/+/value

#========
#ALARMS
#========

ProductionLine1/Transport-12345678/Data/Alarms/value        #Alarm payload specifies which actor has the alarm and if the resource itself maybe has an alarm
Controller subscribes to ProductionLine1/Transport-12345678/Data/Alarms/value

#========
#ACKNOWLEDGEMENTS
#========

ProductionLine1/Transport-12345678/Data/ResourceAck/value        #Acknowledgement is handled on the resource itself when commands or similar messages are published (not actor specific)
Controller subscribes to ProductionLine1/Transport-12345678/Data/Resource_ack/value

ProductionLine1/Transport-12345678/Data/ControllerAck/value        
Resource subscribes to ProductionLine1/Transport-12345678/Data/Controller_ack/value

#========
#INVENTORY
#========

ProductionLine1/Transport-12345678/Data/InventoryLevel/value       #The payload specifies the number of products in each inventory (Not actor specific)
Controller subscribes to ProductionLine1/Transport-12345678/Data/InventoryLevel/value

#========
#REQUEST
#========

ProductionLine1/Transport-12345678/Data/InfoRequest/value
Resource subscribes to ProductionLine1/Transport-12345678/Data/InfoRequest/value
#The controller does not need to subscribe to an additional response message, just all the topics from the submodel

"""


"""
Since there can be multiple actors 
"""

class UR5ManipulatorBehavior(StationBehavior):

    def __init__(self, actor_name: str, mqtt_client):
        # Station-specific variables live HERE
        self.mqtt_client = mqtt_client
        self.actor_name = actor_name

        self.command_payload = None
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None
        self.retrieved_item_component = None
        

    async def idle(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.IDLE)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Resource Is Idle")

    async def starting(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.STARTING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        self.skill = self.command_payload.skill
        self.parameters = self.command_payload.parameters
        print(f"Reading job {self.command_payload.job_id} for order {self.command_payload.order_id}")


        if self.skill == "Handoff":
            try:
                #Loading handoff specific parameters
                self.component_reference = self.parameters.get("ComponentReference")
                self.target_position = self.parameters.get("TargetPosition")
                self.XPos = self.target_position.get("XPos")
                self.YPos = self.target_position.get("YPos")
                print("Handoff parameters loaded:", self.parameters)
            except Exception as e:
                print(f"Failed to load the parameters with exception {e}")


        elif self.skill == "Retrieve":

            if self.parameters is None:
                raise ValueError("No parameters provided for Retrieve skill")

            try:
                # unpack for readability
                self.component_reference = self.parameters.get("ComponentReference")

                print("Retrieve parameters loaded:", self.parameters)

            except Exception as e:
                print(f"Failed to load the parameters with exception {e}")
        
        elif self.skill == "Store":

            if self.parameters is None:
                raise ValueError("No parameters provided for Drilling skill")

            try:
                # unpack for readability
                self.component_reference = self.parameters.get("ComponentReference")

                print("Store parameters loaded:", self.parameters)

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
            print(f"Handing off product: {self.component_reference}")
            print(f"At position ({self.XPos},{self.YPos})")
            self.ideal_cycle_time = 4000+int(self.XPos)+int(self.YPos)
            self.actual_cycle_time = self.ideal_cycle_time + random.randint(200,800)
            await asyncio.sleep(self.actual_cycle_time/1000)

            self.result = MS.Result.COMPLETE
            self.quality = MS.Quality.GOOD

            
        elif self.skill == "Retrieve":
            print(f"Executing Retrieve with product {self.component_reference}")

            retriveable_locations = find_positions(inventories=resource_inventories,query=self.component_reference)

            if retriveable_locations:
                retrieved_item = retriveable_locations[0]  # We just take the first one
                inventory_name = retrieved_item["inventory"]
                position = retrieved_item["position"]
                self.retrieved_item_component = retrieved_item["item"]
                resource_inventories[inventory_name]["Storage"][position] = ""
                #Generating cycle times based on parameters
                self.ideal_cycle_time = 4000
                self.actual_cycle_time = self.ideal_cycle_time + random.randint(200,800)
                await asyncio.sleep(self.actual_cycle_time/1000)
                #Generating result and quality randomly
                self.result = MS.Result.COMPLETE
                self.quality = MS.Quality.GOOD
            
            
        
        elif self.skill == "Store":
            print(f"Executing Store with product {self.component_reference}")
            
            #This should automatically find available positions and then place it into one
            #It also returns the specific inventory and position, but we don't need that right now

            stored_item_position = place_item(resource_inventories, self.component_reference)
            
            if stored_item_position is not None:
                #Generating cycle times based on parameters
                self.ideal_cycle_time = 4000
                self.actual_cycle_time = self.ideal_cycle_time + random.randint(200,800)
                await asyncio.sleep(self.actual_cycle_time/1000)
                #Generating result and quality
                self.result = MS.Result.COMPLETE
                self.quality = MS.Quality.GOOD
            else:
                self.result = MS.Result.INCOMPLETE
                self.quality = MS.Quality.BAD
                self.ideal_cycle_time = 0
                self.actual_cycle_time = 0
            

        else:
            print("How did you even get here?")
            await machine.transition_to(PackMLState.STOPPING)
        
        await machine.transition_to(PackMLState.COMPLETING)

    async def completing(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.COMPLETING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Finalizing Process and sending result")

        if self.skill == "Retrive":
            job_result_message = MS.JobResultMessage(
                timestamp=datetime.now(),
                resource_id=CLIENT_ID, 
                order_id=self.command_payload.order_id, 
                job_id=self.command_payload.job_id, 
                ideal_cycle_time_ms=self.ideal_cycle_time,
                actual_cycle_time_ms=self.actual_cycle_time,
                result=self.result,
                quality=self.quality,
                output_parameters={"ComponentReference": self.retrieved_item_component}
            )

        elif self.skill == "Store" or self.skill == "Handoff":
            job_result_message = MS.JobResultMessage(
                timestamp=datetime.now(),
                resource_id=CLIENT_ID, 
                order_id=self.command_payload.order_id, 
                job_id=self.command_payload.job_id, 
                ideal_cycle_time_ms=self.ideal_cycle_time,
                actual_cycle_time_ms=self.actual_cycle_time,
                result=self.result,
                quality=self.quality,
                output_parameters={"ComponentReference": self.component_reference}
            )
        

        self.mqtt_client.publish(f"{job_result_suffix}/{self.actor_name}",job_result_message)

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.COMPLETE)

    async def resetting(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.RESETTING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Resetting Storage")

        self.command_payload = None
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None
        self.retrieved_item_component = None

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.IDLE)

    async def stopping(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.STOPPING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Stopping Storage")

        #Stop command, should maybe just wait like 2 seconds
        
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)
        
    async def holding(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.HOLDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Holding Storage")

        # Why holding? Maybe not relevant at the moment

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.HELD)
    
    async def unholding(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.UNHOLDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Unholding Storage")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def suspending(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.SUSPENDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Suspending Storage")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.SUSPENDED)

    async def unsuspending(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.UNSUSPENDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Unsuspending Storage")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def aborting(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.ABORTING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Aborting Storage")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.ABORTED)

    async def clearing(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.CLEARING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Clearing Drill")

        self.command_payload = None
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None
        self.retrieved_item_component = None

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)


#=============
# Generating Actors from their behavior
#=============

ur5_manipulator_behavior = UR5ManipulatorBehavior(Actor,mqtt_client)
UR5Manipulator = PackMLStateMachine(ur5_manipulator_behavior)

StateMachines = [UR5Manipulator]

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
        inventory_data, all_items = summarize_inventories(resource_inventories)
        inventory_message = MS.InventoryLevelMessage(timestamp=datetime.now(), resource_id=CLIENT_ID,inventory=inventory_data,AllItems=all_items)
        mqtt_client.publish(f"{inventory_suffix}", inventory_message)
        

    else:
        print("Unable to find the requested topic, we are not yet sending an error message back")




#=============
#Registering those handlers to specific topics
#=============

mqtt_client.register_subscriber(command_suffix, MS.CommandMessage,handle_command)
mqtt_client.register_subscriber(info_request_suffix, MS.RequestMessage,handle_request)

params = {
    "ComponentReference": "BottomCover_PLA"
}

test_command = MS.CommandMessage(
    timestamp=datetime.now(),
    resource_id=CLIENT_ID,
    skill="Retrieve",
    actor_name=Actor,
    skill_trigger=MS.CommandType.START,
    order_id="ORD-1",
    job_id="RET13V3",
    parameters=params
)


print("Test Command: ", test_command.model_dump_json(indent=2))

test_request = MS.RequestMessage(timestamp=datetime.now(),requested_topic_update="AAUSmartLab/ProductionLine1/Storage_12345678/InventoryLevel",resource_id=CLIENT_ID)


print("Test Request: ", test_request.model_dump_json(indent=2))

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