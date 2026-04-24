#This should first create the shell and submodels from the yaml files and publish them to the server.

#It should also contain the PackML implementation, aka, this should be the main script for this resource


import asyncio
import time
import random
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from ClassesAndBuilderMethods.PackML.PackML_Machine_Class import StationBehavior, PackMLState,PackMLStateMachine


from Shell_And_Submodels.Shell_Generator_Class import ShellGenerator




AAS_PORT = "8081"
SERVER_BASE = f"http://{BROKER}:{AAS_PORT}"  # your server base URL
SUBMODEL_ENDPOINT = f"{SERVER_BASE}/submodels"
SHELL_ENDPOINT = f"{SERVER_BASE}/shells"



class ACOPOS6DStationBehavior(StationBehavior):

    def __init__(self):
        # Station-specific variables live HERE
        self.skill = None
        self.component_reference = None
        self.speed = None
        self.acceleration = None
        self.base_time_ms = None
        self.hover_height = None

    async def starting(self, machine):
        print("Reading job parameters")
        machine.cycle_start_time = time.time()
        machine.job_id = machine.current_job["job_id"]
        machine.order_id = machine.current_job["order_id"]

        print("Getting parameters")
        params = machine.current_job.get("parameters", {})

        print("Reading parameters")
        self.skill = params.get("skill",0)
        self.speed = params.get("speed", 0)
        self.acceleration = params.get("acceleration", 0)
        self.hover_height = params.get("hover_height", 0)
        self.component_reference = params.get("component_reference", "")

        print("Calculating Ideal time")
        #Use parameters to calculate ideal cycle time..
        self.base_time_ms = 2000
        self.speed_factor = 1200 / self.speed * 100    
        self.acceleration_factor = 1200 / self.acceleration * 500      # højere rpm → kortere tid
        print("Adding Ideal Time")
        machine.ideal_cycle_time_ms = int(self.base_time_ms + self.speed_factor - self.acceleration_factor)

        print("All parameters are read, now transitioning to EXECUTE")
        await machine.transition_to(PackMLState.EXECUTE)

    async def execute(self, machine):
        print(f"Transporting component: {self.component_reference} in progress...")
        
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
        print("Resetting Shuttle...")
        self.skill = None
        self.component_reference = None
        self.drill_depth = None
        self.rpm = None

        machine.job_result = None
        machine.order_id = None
        machine.job_id = None
        machine.ideal_cycle_time_ms = None
        machine.cycle_time_ms = None
        machine.job_quality = None

        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.IDLE)

    async def stopping(self, machine):
        print("Stopping Shuttle")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)
        
    async def holding(self, machine): 
        print("Holding Shuttle")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.HELD)
    
    async def unholding(self, machine): 
        print("Unholding Shuttle")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def suspending(self, machine):
        print("Suspending Shuttle")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.SUSPENDED)

    async def unsuspending(self, machine):
        print("Unsuspending Shuttle")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def aborting(self, machine): 
        print("Aborting Shuttle")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.ABORTED)

    async def clearing(self, machine): 
        print("Clearing Shuttle")

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
    behavior = ACOPOS6DStationBehavior()
    machine = PackMLStateMachine(mqtt_information, behavior)
    ACOPOS6D_Resource_AAS.post_shell_and_submodels(SHELL_ENDPOINT=SHELL_ENDPOINT, SUBMODEL_ENDPOINT=SUBMODEL_ENDPOINT)
    
    #machine.active_alarms = [51,62]
    # Keep machine alive forever
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())