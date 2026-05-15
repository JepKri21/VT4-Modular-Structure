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

(We are not using this one:)
ProductionLine1/Transport-12345678/Data/CMD/Shuttle1/value
ProductionLine1/Transport-12345678/Data/CMD/Shuttle2/value
Resoruce subscribes to ProductionLine1/Transport-12345678/Data/CMD/+/value

OR MAYBE IT IS BETTER TO (We are unsing the one below):

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

        self.command_payload = None
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None
        

    async def idle(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.IDLE)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Drill Is Idle")

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


        elif self.skill == "Drilling":

            if self.parameters is None:
                raise ValueError("No parameters provided for Drilling skill")

            try:
                # Parameters the work order is allowed to set, per the
                # DrillingCapabilityOffered contract.
                self.hole_diameter = self.parameters.get("HoleDiameter")
                self.drill_depth = self.parameters.get("DrillDepth")
                target_position = self.parameters.get("TargetPosition") or {}
                self.hole_x = target_position.get("XPos")
                self.hole_y = target_position.get("YPos")
                self.component_reference = self.parameters.get("ComponentReference")

                # Internal resource settings — not in the capability, the
                # resource decides its own best feed/speed for the given bit.
                self.spindle_speed = 800.0   # RPM
                self.spindle_feed = 20.0     # mm/s

                print("Drilling parameters loaded:", self.parameters)

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

            
        elif self.skill == "Drilling":
            print(f"Executing drilling with these parameters: Hole Diameter: {self.hole_diameter}, Drill Depth: {self.drill_depth}, Spindle Speed: {self.spindle_speed}, Spindle Feed: {self.spindle_feed}, Hole X: {self.hole_x}, Hole Y: {self.hole_y}, Component Reference: {self.component_reference}")
            
            #Generating cycle times based on parameters
            self.ideal_cycle_time = int((self.drill_depth/self.spindle_feed)*1000)
            self.actual_cycle_time = self.ideal_cycle_time + random.randint(200,1500)
            await asyncio.sleep(self.actual_cycle_time/1000)

            #Generating result and quality randomly
            if random.randint(1,10) > 1:
                self.result = MS.Result.COMPLETE
                if random.randint(1,10) > 1:
                    self.quality = MS.Quality.GOOD
                else:
                    self.quality = MS.Quality.BAD
            else:
                self.result = MS.Result.INCOMPLETE
                self.quality = MS.Quality.NA
            

        else:
            print("How did you even get here?")
            await machine.transition_to(PackMLState.STOPPING)
        
        await machine.transition_to(PackMLState.COMPLETING)

    async def completing(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.COMPLETING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Finalizing Process and sending result")

        job_result_message = MS.JobResultMessage(
            timestamp=datetime.now(),
            resource_id=CLIENT_ID, 
            order_id=self.command_payload.order_id, 
            job_id=self.command_payload.job_id, 
            ideal_cycle_time_ms=self.ideal_cycle_time,
            actual_cycle_time_ms=self.actual_cycle_time,
            result=self.result,
            quality=self.quality
        )
        self.mqtt_client.publish(f"{job_result_suffix}/{self.actor_name}",job_result_message)
        print(f"JobResult Payload published {job_result_message}")

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.COMPLETE)

    async def resetting(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.RESETTING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Resetting Drill")

        self.command_payload = None
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.IDLE)

    async def stopping(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.STOPPING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Stopping Drill")

        #Stop command, should maybe just wait like 2 seconds
        
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)
        
    async def holding(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.HOLDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Holding Drill")

        # Why holding? Maybe not relevant at the moment

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.HELD)
    
    async def unholding(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.UNHOLDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Unholding Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def suspending(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.SUSPENDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Suspending Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.SUSPENDED)

    async def unsuspending(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.UNSUSPENDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Unsuspending Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def aborting(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.ABORTING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Aborting Drill")
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

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)


#=============
# Generating Actors from their behavior
#=============

kuka_manipulator_behavior = KUKAManipulatorBehavior(Actor,mqtt_client)
KUKAManipulator = PackMLStateMachine(kuka_manipulator_behavior)



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

    if msg.actor_name == Actor:
        KUKAManipulator.behavior.command_payload = msg
        if main_loop is None:
            print("Event loop not ready; dropping command")
            return
        asyncio.run_coroutine_threadsafe(
            KUKAManipulator.state_command_callback(msg.skill_trigger),
            main_loop,
        )


#ProductionLine1/Transport-12345678/Data/State/Shuttle1/value

def handle_request(msg: MS.RequestMessage):
    print(f"Topic to update: {msg.requested_topic_update}")
    elements = msg.requested_topic_update.split("/")

    if state_suffix in elements:
        #Here it should just print all the states for all the actors, we don't want to specify which actor we want the state from
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=KUKAManipulator.state)
        mqtt_client.publish(f"{state_suffix}/{KUKAManipulator.behavior.actor_name}", state_message)


    else:
        print("State suffix not found in topic")

#=============
#Registering those handlers to specific topics
#=============

mqtt_client.register_subscriber(command_suffix, MS.CommandMessage,handle_command)
mqtt_client.register_subscriber(info_request_suffix, MS.RequestMessage,handle_request)

params = {
    "BitDiameter": 5.0,
    "DrillDepth": 50.0,
    "SpindleSpeed": 800.0,
    "SpindleFeed": 20.0,
    "TargetPosition": {"XPos": 20.0, "YPos": 10.0},
    "ComponentReference": "BottomCover_ALU"
}

test_command = MS.CommandMessage(
    timestamp=datetime.now(),
    resource_id=CLIENT_ID,
    skill="Drilling",
    actor_name=Actor,
    skill_trigger=MS.CommandType.START,
    order_id=None,
    job_id=None,
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