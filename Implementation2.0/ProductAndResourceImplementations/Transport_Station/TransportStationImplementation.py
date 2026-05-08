import asyncio
import time
import random
import sys
from pathlib import Path
import json
from datetime import datetime
from math import ceil, dist, sqrt
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


builder = yaml_to_instance.load_instance_from_yaml(f"{script_dir}/TransportCapabilityOffered.yaml")
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

Actor1 = "Shuttle1"
Actor2 = "Shuttle2"
Actors = [Actor1, Actor2]

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

class Shuttle1Behaviour(StationBehavior):

    def __init__(self, actor_name: str, mqtt_client):
        # Station-specific variables live HERE
        self.mqtt_client = mqtt_client
        self.actor_name = actor_name

        self.command_payload = None
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None
        self.current_position = [0,0]
        

    async def idle(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.IDLE)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print(f"{self.actor_name} Is Idle")

    async def starting(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.STARTING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        self.skill = self.command_payload.skill
        self.parameters = self.command_payload.parameters
        print(f"Reading job {self.command_payload.job_id} for order {self.command_payload.order_id}")


        if self.skill == "Transport":

            if self.parameters is None:
                raise ValueError("No parameters provided for Transport skill")

            try:
                # unpack for readability
                self.speed_constraint = self.parameters.get("SpeedConstraint")
                self.acceleration_constraint = self.parameters.get("AccelerationConstraint")
                self.target_position = self.parameters.get("TargetPosition")
                self.x_pos = self.target_position.get("XPos")
                self.y_pos = self.target_position.get("YPos")
                self.component_reference = self.parameters.get("ComponentReference")

                print("Transport parameters loaded:", self.parameters)

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

        if self.skill == "Transport":
            print(f"Executing Transport with parameters:  Speed Constraint: {self.speed_constraint}, Acceleration Constraint: {self.acceleration_constraint}, Target Position: { self.target_position}, Component Reference: {self.component_reference}")
            
            #Generating cycle times based on parameters

            target_position = [self.x_pos, self.y_pos]
            distance = dist(self.current_position, target_position)/1000

            t_acc = self.speed_constraint/self.acceleration_constraint
            d_acc = 0.5*self.acceleration_constraint*t_acc**2

            if d_acc >= distance:
                self.ideal_cycle_time = int(sqrt(2*distance/self.acceleration_constraint)*1000)
            else:
                d_const = distance - d_acc
                t_const = d_const/self.speed_constraint
                self.ideal_cycle_time = int((t_acc+t_const)*1000)
        
            self.actual_cycle_time = self.ideal_cycle_time + int(self.ideal_cycle_time*(random.randint(5,20)/100))
            await asyncio.sleep(self.actual_cycle_time/1000)

            #Generating result and quality (Just good every time for now)
            self.result = MS.Result.COMPLETE
            self.quality = MS.Quality.GOOD
            
            self.current_position = target_position

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

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.COMPLETE)

    async def resetting(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.RESETTING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print(f"Resetting Transport with Shuttle: {self.actor_name}")

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
        print("Stopping Transport")

        #Stop command, should maybe just wait like 2 seconds
        
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)
        
    async def holding(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.HOLDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Holding Transport")

        # Why holding? Maybe not relevant at the moment

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.HELD)
    
    async def unholding(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.UNHOLDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Unholding Transport")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def suspending(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.SUSPENDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Suspending Transport")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.SUSPENDED)

    async def unsuspending(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.UNSUSPENDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Unsuspending Transport")
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
        print("Clearing Transport")

        self.command_payload = None
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)


class Shuttle2Behaviour(StationBehavior):

    def __init__(self, actor_name: str, mqtt_client):
        # Station-specific variables live HERE
        self.mqtt_client = mqtt_client
        self.actor_name = actor_name

        self.command_payload = None
        self.result = None
        self.quality = None
        self.ideal_cycle_time = None
        self.actual_cycle_time = None
        self.current_position = [0,0]
        

    async def idle(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.IDLE)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print(f"{self.actor_name} Is Idle")

    async def starting(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.STARTING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        self.skill = self.command_payload.skill
        self.parameters = self.command_payload.parameters
        print(f"Reading job {self.command_payload.job_id} for order {self.command_payload.order_id}")


        if self.skill == "Transport":

            if self.parameters is None:
                raise ValueError("No parameters provided for Transport skill")

            try:
                # unpack for readability
                self.speed_constraint = self.parameters.get("SpeedConstraint")
                self.acceleration_constraint = self.parameters.get("AccelerationConstraint")
                self.target_position = self.parameters.get("TargetPosition")
                self.x_pos = self.target_position.get("XPos")
                self.y_pos = self.target_position.get("YPos")
                self.component_reference = self.parameters.get("ComponentReference")

                print("Transport parameters loaded:", self.parameters)

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

        if self.skill == "Transport":
            print(f"Current Position Is: ({self.current_position[0]},{self.current_position[1]})")
            print(f"Executing Transport with parameters:  Speed Constraint: {self.speed_constraint}, Acceleration Constraint: {self.acceleration_constraint}, Target Position: { self.target_position}, Component Reference: {self.component_reference}")
            
            #Generating cycle times based on parameters
            target_position = [self.x_pos, self.y_pos]
            distance = dist(self.current_position, target_position)/1000
            

            t_acc = self.speed_constraint/self.acceleration_constraint
            d_acc = 0.5*self.acceleration_constraint*t_acc**2

            if d_acc >= distance:
                self.ideal_cycle_time = int(sqrt(2*distance/self.acceleration_constraint)*1000)
            else:
                d_const = distance - d_acc
                t_const = d_const/self.speed_constraint
                self.ideal_cycle_time = int((t_acc+t_const)*1000)
        
            self.actual_cycle_time = self.ideal_cycle_time + int(self.ideal_cycle_time*(random.randint(5,20)/100))
            await asyncio.sleep(self.actual_cycle_time/1000)

            #Generating result and quality (Just good every time for now)
            self.result = MS.Result.COMPLETE
            self.quality = MS.Quality.GOOD
            
            self.current_position = target_position

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

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.COMPLETE)

    async def resetting(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.RESETTING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print(f"Resetting Transport with Shuttle: {self.actor_name}")

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
        print("Stopping Transport")

        #Stop command, should maybe just wait like 2 seconds
        
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)
        
    async def holding(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.HOLDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Holding Transport")

        # Why holding? Maybe not relevant at the moment

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.HELD)
    
    async def unholding(self, machine): 
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.UNHOLDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Unholding Transport")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def suspending(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.SUSPENDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Suspending Transport")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.SUSPENDED)

    async def unsuspending(self, machine):
        state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=PackMLState.UNSUSPENDING)
        self.mqtt_client.publish(f"{state_suffix}/{self.actor_name}", state_message)
        print("Unsuspending Transport")
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
        print("Clearing Transport")

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

shuttle1_behaviour = Shuttle1Behaviour(Actor1,mqtt_client)
Shuttle1 = PackMLStateMachine(shuttle1_behaviour)

shuttle2_behaviour = Shuttle2Behaviour(Actor2,mqtt_client)
Shuttle2 = PackMLStateMachine(shuttle2_behaviour)

StateMachines = [Shuttle1, Shuttle2]

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

    if state_suffix in elements:
        for StateMachine in StateMachines:
            state_message = MS.StateMessage(timestamp=datetime.now(), resource_id=CLIENT_ID, state=StateMachine.state)
            mqtt_client.publish(f"{state_suffix}/{StateMachine.behavior.actor_name}", state_message)
            
    else:
        print("State suffix not found in topic")

#=============
#Registering those handlers to specific topics
#=============

mqtt_client.register_subscriber(command_suffix, MS.CommandMessage,handle_command)
mqtt_client.register_subscriber(info_request_suffix, MS.RequestMessage,handle_request)

params = {
    "SpeedConstraint": 0.2,
    "AccelerationConstraint": 0.5,
    "TargetPosition": {"XPos": 120.5, "YPos": 290.5},
    "ComponentReference": "BottomCover_ALU"
}

test_command = MS.CommandMessage(
    timestamp=datetime.now(),
    resource_id=CLIENT_ID,
    skill="Transport",
    actor_name=Shuttle1.behavior.actor_name,
    skill_trigger=MS.CommandType.START,
    order_id="ORD-1",
    job_id="TRANS1",
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