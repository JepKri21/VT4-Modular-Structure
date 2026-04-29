#This should first create the shell and submodels from the yaml files and publish them to the server.

#It should also contain the PackML implementation, aka, this should be the main script for this resource


import asyncio
import time
import random
import sys
from pathlib import Path
import json
from datetime import datetime
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


builder = yaml_to_instance.load_instance_from_yaml(f"{script_dir}/DrillingCapabilityOffered.yaml")
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

Actor = "KUKAManipulator"

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

class KUKAManipulatorBehavior(StationBehavior):

    def __init__(self, actor_name: str, mqtt_client):
        # Station-specific variables live HERE
        self.mqtt_client = mqtt_client
        self.actor_name = actor_name
        self.skill = None
        self.component_reference = None
        self.drill_depth = None
        self.rpm = None
        self.base_time_ms = None
        self.depth_factor = None
        self.rpm_factor = None

        #Make a variable that adds the command message
        self.command_payload = None

    async def starting(self, machine):
        #EVERY STATE SHOULD HAVE A PUBLISHING OF THE NEW STATE AS THE BEGINNING
        state_message = MS.StateMessage(datetime.now(),CLIENT_ID, PackMLState.STARTING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Starting Drill Process")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def execute(self, machine):
        state_message = MS.StateMessage(datetime.now(),CLIENT_ID, PackMLState.EXECUTE)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Executing Drill Process")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.COMPLETING)

    async def completing(self, machine):
        state_message = MS.StateMessage(datetime.now(),CLIENT_ID, PackMLState.COMPLETING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Completing Drill Process")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.COMPLETE)

    async def resetting(self, machine):
        state_message = MS.StateMessage(datetime.now(),CLIENT_ID, PackMLState.RESETTING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Resetting Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.IDLE)

    async def stopping(self, machine):
        state_message = MS.StateMessage(datetime.now(),CLIENT_ID, PackMLState.STOPPING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Stopping Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)
        
    async def holding(self, machine): 
        state_message = MS.StateMessage(datetime.now(),CLIENT_ID, PackMLState.HOLDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Holding Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.HELD)
    
    async def unholding(self, machine): 
        state_message = MS.StateMessage(datetime.now(),CLIENT_ID, PackMLState.UNHOLDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Unholding Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def suspending(self, machine):
        state_message = MS.StateMessage(datetime.now(),CLIENT_ID, PackMLState.SUSPENDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Suspending Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.SUSPENDED)

    async def unsuspending(self, machine):
        state_message = MS.StateMessage(datetime.now(),CLIENT_ID, PackMLState.UNSUSPENDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Unsuspending Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def aborting(self, machine): 
        state_message = MS.StateMessage(datetime.now(),CLIENT_ID, PackMLState.ABORTING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Aborting Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.ABORTED)

    async def clearing(self, machine): 
        state_message = MS.StateMessage(datetime.now(),CLIENT_ID, PackMLState.CLEARING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Clearing Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)



kuka_manipulator_behavior = KUKAManipulatorBehavior(Actor,mqtt_client)
KUKAManipulator = PackMLStateMachine(kuka_manipulator_behavior)



def handle_command(msg: MS.CommandMessage):
    print(f"Received command: {msg.command_type}")
    print(f"Skill: {msg.skill}")
    print(f"Actor: {msg.actor_name}")
    print(f"Order ID: {msg.order_id}")
    print(f"Parameters: {msg.parameters}")

    if msg.actor_name == Actor:
        KUKAManipulator.behavior.command_payload = msg
        KUKAManipulator.state_command_callback(msg.skill_trigger)


#ProductionLine1/Transport-12345678/Data/State/Shuttle1/value

def handle_request(msg: MS.RequestMessage):
    print(f"Topic to update: {msg.requested_topic_update}")
    elements = msg.requested_topic_update.split("/")

    if state_suffix in elements:
        state_index = elements.index(state_suffix)

        # Make sure there is something after "state"
        if len(elements) > state_index + 1:
            actor_name = elements[state_index + 1]

            print(f"Requested actor: {actor_name}")

            if actor_name == "KUKAManipulator":
                state_message = MS.StateMessage(datetime.now(),CLIENT_ID, KUKAManipulator.state)
                mqtt_client.publish(f"{state_suffix}/{KUKAManipulator.behavior.actor_name}", state_message)

            else:
                print(f"Unknown actor: {actor_name}")
        else:
            print("No actor specified after state suffix")
    else:
        print("State suffix not found in topic")



mqtt_client.register_subscriber(command_suffix, MS.CommandMessage,handle_command)
mqtt_client.register_subscriber(info_request_suffix, MS.RequestMessage,handle_request)

test_command = MS.CommandMessage(
    timestamp=datetime.now(),
    resource_id=CLIENT_ID,
    skill="Drilling",
    actor_name=Actor,
    skill_trigger=MS.CommandType.START,
    order_id=None,
    job_id=None,
    parameters=None,
)

print("Test Command: ", test_command.model_dump_json(indent=2))

async def main():
    

    mqtt_client.start_mqtt_connection()
    
    #machine.active_alarms = [51,62]
    # Keep machine alive forever
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())