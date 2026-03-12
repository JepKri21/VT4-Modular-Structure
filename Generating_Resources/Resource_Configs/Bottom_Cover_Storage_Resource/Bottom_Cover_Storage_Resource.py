
import asyncio
import time
import random
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from PackML.PackML_Machine_Class import StationBehavior, PackMLState, PackMLStateMachine
from Shell_And_Submodels.Shell_Generator_Class import ShellGenerator

BASE_DIR = Path(__file__).resolve().parent
yaml_config = BASE_DIR / "Bottom_Cover_Storage_Resource_Config.yaml"

Bottom_Cover_Storage_Resource_AAS = ShellGenerator(yaml_config)

communication_submodel = Bottom_Cover_Storage_Resource_AAS.builder.get_submodel("Communication")

communication_properties = communication_submodel['submodelElements'][0]['value'][0]['value']


#It is very possible that things like port, broker address, and things like AAS server port and endpoints should not be in the communication submodel,
#  as it will change depending where the machine is located and there is not very static or transferable, say if a new company obtains it.
#I think we just need to assume that the line controller will have access to the same networks as the stations and that you just have to match them.
# It would really only be necessary if a production line is on multiple MQTT brokers that the line controller needs to connect to.

for property in communication_properties:
    if property['idShort'] == 'Broker_Address':
        BROKER = property['value']
    if property['idShort'] == 'Port':
        MQTT_PORT = int(property['value'])
    if property['idShort'] == 'Base_Topic':
        BASE_TOPIC = property['value']

CLIENT_ID = Bottom_Cover_Storage_Resource_AAS.shell_idShort


mqtt_information = [BROKER, MQTT_PORT, CLIENT_ID,BASE_TOPIC]


AAS_PORT = "8081"
SERVER_BASE = f"http://{BROKER}:{AAS_PORT}"  # your server base URL
SUBMODEL_ENDPOINT = f"{SERVER_BASE}/submodels"
SHELL_ENDPOINT = f"{SERVER_BASE}/shells"



class Bottom_Cover_Storage_StationBehavior(StationBehavior):

    def __init__(self):
        # Station-specific variables live HERE
        self.skill = None
        self.component_reference = None
        self.speed = None
        self.acceleration = None
        self.base_time_ms = None
        self.speed_factor = None
        self.acceleration_factor = None

    async def starting(self, machine):
        print("Bottom_Cover_Storage: reading job parameters")
        machine.cycle_start_time = time.time()
        machine.job_id = machine.current_job["job_id"]
        machine.order_id = machine.current_job["order_id"]

        params = machine.current_job.get("parameters", {})

        self.skill = params.get("skill",0)
        self.speed = params.get("speed", 0)
        self.acceleration = params.get("acceleration", 0)
        self.component_reference = params.get("component_reference", "")

        #Use parameters to calculate ideal cycle time..
        self.base_time_ms = 2000
        self.speed_factor = self.speed * 100    # 100ms per mm
        self.acceleration_factor = 1200 / self.acceleration * 500      # højere rpm → kortere tid

        machine.ideal_cycle_time_ms = int(self.base_time_ms + self.speed_factor - self.acceleration_factor)

        print("All parameters are read, now transitioning to EXECUTE")
        await machine.transition_to(PackMLState.EXECUTE)

    async def execute(self, machine):
        print(f"Retrieving of component: {self.component_reference} in progress...")
        
        await asyncio.sleep((machine.ideal_cycle_time_ms + random.randint(0, 300)) / 1000)

        machine.job_result = "COMPLETE"
        machine.job_quality = "OK"

        await machine.transition_to(PackMLState.COMPLETING)

    async def completing(self, machine):
        machine.cycle_time_ms = int(
            (time.time() - machine.cycle_start_time) * 1000
        )

        machine.mqtt_client.publish_job_status(
            machine.job_result,
            machine.order_id,
            machine.job_id,
            machine.ideal_cycle_time_ms,
            machine.cycle_time_ms,
            machine.job_quality,
        )

        await machine.transition_to(PackMLState.COMPLETE)

    async def resetting(self, machine):
        print("Resetting Bottom_Cover_Storage...🤖")
        self.skill = None
        self.component_reference = None
        self.speed = None
        self.acceleration = None

        machine.job_result = None
        machine.order_id = None
        machine.job_id = None
        machine.ideal_cycle_time_ms = None
        machine.cycle_time_ms = None
        machine.job_quality = None

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.IDLE)

    async def stopping(self, machine):
        print("Stopping Bottom_Cover_Storage")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)
        
    async def holding(self, machine): 
        print("Holding Bottom_Cover_Storage")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.HELD)
    
    async def unholding(self, machine): 
        print("Unholding Bottom_Cover_Storage")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def suspending(self, machine):
        print("Suspending Bottom_Cover_Storage")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.SUSPENDED)

    async def unsuspending(self, machine):
        print("Unsuspending Bottom_Cover_Storage")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def aborting(self, machine): 
        print("Aborting Bottom_Cover_Storage")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.ABORTED)

    async def clearing(self, machine): 
        print("Clearing Bottom_Cover_Storage")

        self.skill = None
        self.component_reference = None
        self.speed = None
        self.acceleration = None

        machine.job_result = None
        machine.order_id = None
        machine.job_id = None
        machine.ideal_cycle_time_ms = None
        machine.cycle_time_ms = None
        machine.job_quality = None

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)



async def main():
    behavior = Bottom_Cover_Storage_StationBehavior()
    machine = PackMLStateMachine(mqtt_information, behavior)
    Bottom_Cover_Storage_Resource_AAS.post_shell_and_submodels(SHELL_ENDPOINT=SHELL_ENDPOINT, SUBMODEL_ENDPOINT=SUBMODEL_ENDPOINT)
    
    #machine.active_alarms = [51,62]
    # Keep machine alive forever
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())