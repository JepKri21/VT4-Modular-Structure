from PackML_Machine_Class import StationBehavior, PackMLState, PackMLStateMachine
import asyncio
import time
import random


# BROKER = "172.20.10.236"
BROKER = "localhost"
PORT = 1883
CLIENT_ID = "Drilling_1"
BASE_TOPIC = "AAU/Smartlab/PL1/Stations"

mqtt_information = [BROKER, PORT, CLIENT_ID,BASE_TOPIC]

class DrillingStationBehavior(StationBehavior):

    def __init__(self):
        # Station-specific variables live HERE
        self.skill = None
        self.component_reference = None
        self.drill_depth = None
        self.rpm = None
        self.base_time_ms = None
        self.depth_factor = None
        self.rpm_factor = None

    async def starting(self, machine):
        print("Drill warming up... and reading job parameters")
        machine.cycle_start_time = time.time()
        machine.job_id = machine.current_job["job_id"]
        machine.order_id = machine.current_job["order_id"]

        params = machine.current_job.get("parameters", {})

        self.skill = params.get("skill",0)
        self.drill_depth = params.get("drill_depth", 0)
        self.rpm = params.get("rpm", 0)
        self.component_reference = params.get("component_reference", "")

        #Use parameters to calculate ideal cycle time..
        self.base_time_ms = 2000
        self.depth_factor = self.drill_depth * 100    # 100ms per mm
        self.rpm_factor = 1200 / self.rpm * 500      # højere rpm → kortere tid

        machine.ideal_cycle_time_ms = int(self.base_time_ms + self.depth_factor - self.rpm_factor)

        print("All parameters are read, now transitioning to EXECUTE")
        await machine.transition_to(PackMLState.EXECUTE)

    async def execute(self, machine):
        print("Drilling in progress...")
        
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
        print("Resetting drill...")
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
        print("Stopping Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.STOPPED)
        
    async def holding(self, machine): 
        print("Holding Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.HELD)
    
    async def unholding(self, machine): 
        print("Unholding Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def suspending(self, machine):
        print("Suspending Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.SUSPENDED)

    async def unsuspending(self, machine):
        print("Unsuspending Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.EXECUTE)

    async def aborting(self, machine): 
        print("Aborting Drill")
        await asyncio.sleep(2)
        await machine.transition_to(PackMLState.ABORTED)

    async def clearing(self, machine): 
        print("Clearing Drill")

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
        await machine.transition_to(PackMLState.STOPPED)







async def main():
    behavior = DrillingStationBehavior()
    machine = PackMLStateMachine(mqtt_information, behavior)
    machine.active_alarms = [51,62]
    # Keep machine alive forever
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())