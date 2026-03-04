import enum
from typing import Optional
import time
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from MQTT_Server_Client.MQTT_Client import MQTT_Client_Resource

class PackMLState(enum.Enum):
    # Main states
    IDLE = "IDLE"
    STARTING = "STARTING"
    EXECUTE = "EXECUTE"
    COMPLETING = "COMPLETING"
    COMPLETE = "COMPLETE"
    RESETTING = "RESETTING"

    # Hold states
    HOLDING = "HOLDING"
    HELD = "HELD"
    UNHOLDING = "UNHOLDING"

    # Suspend states
    SUSPENDING = "SUSPENDING"
    SUSPENDED = "SUSPENDED"
    UNSUSPENDING = "UNSUSPENDING"

    # Stop and abort states
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ABORTING = "ABORTING"
    ABORTED = "ABORTED"
    CLEARING = "CLEARING"


class StationBehavior:
    async def idle(self, machine): pass
    async def starting(self, machine): pass
    async def execute(self, machine): pass
    async def completing(self, machine): pass
    async def stopping(self, machine): pass
    async def holding(self, machine): pass
    async def unholding(self, machine): pass
    async def suspending(self, machine): pass
    async def unsuspending(self, machine): pass
    async def aborting(self, machine): pass
    async def resetting(self, machine): pass
    async def clearing(self, machine): pass


class PackMLStateMachine:
    def __init__(self, mqtt_info, behavior: StationBehavior):
        self.behavior = behavior
        self.state = PackMLState.IDLE

        #PACKML INFO:
        self.current_task = None            #Tracking the state it is currently doing
        self.current_job = None             #Containing job data for whatever job is being sent
        self.job_id = None                  #Updated when a job has been given
        self.job_result = None              #Updated when a job has been given
        self.order_id = None                #Updated when a job has been given
        self.ideal_cycle_time_ms = None     #Updated when a job has been given
        self.cycle_time_ms = None           #Updated when a job has been given
        self.job_quality = None             #Updated when a job has been given


        #MQTT INFO:
        self.BROKER = mqtt_info[0]
        self.PORT = mqtt_info [1]
        self.CLIENT_ID = mqtt_info[2]
        self.BASE_TOPIC = mqtt_info[3]
        self.mqtt_client = MQTT_Client_Resource(self.BROKER,self.PORT, self.CLIENT_ID,self.BASE_TOPIC, self)
        self.mqtt_client.start_mqtt_connection()
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            # fallback hvis ingen running loop (kan ske ved sync init)
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

    async def state_command_callback(self, cmd):
        if cmd == "start":
            if self.state == PackMLState.IDLE:
                await self.transition_to(PackMLState.STARTING)
            else:
                print(f"Cannot transition to state: {PackMLState.STARTING} when in state: {self.state} state!")
        
        elif cmd == "stop":
            if self.state not in [PackMLState.STOPPED, PackMLState.STOPPING, PackMLState.ABORTED, PackMLState.ABORTING]:
                await self.transition_to(PackMLState.STOPPING)
            else:
                print(f"Cannot transition to state: {PackMLState.STOPPING} when in state: {self.state} state!")    
            
        elif cmd == "hold":
            if self.state == PackMLState.EXECUTE:
                await self.transition_to(PackMLState.HOLDING)
            else:
                print(f"Cannot transition to state: {PackMLState.HOLDING} when in state: {self.state} state!")
                
        elif cmd == "unhold":
            if self.state in [PackMLState.HELD, PackMLState.HOLDING]:
                await self.transition_to(PackMLState.UNHOLDING)
            else:
                print(f"Cannot transition to state: {PackMLState.UNHOLDING} when in state: {self.state} state!")
        
        elif cmd == "clear":
            if self.state == PackMLState.ABORTED:
                await self.transition_to(PackMLState.CLEARING)
            else:
                print(f"Cannot transition to state: {PackMLState.CLEARING} when in state: {self.state} state!")

        elif cmd == "reset":
            if self.state in [PackMLState.STOPPED, PackMLState.ABORTED, PackMLState.COMPLETE]:
                await self.transition_to(PackMLState.RESETTING)
            else:
                print(f"Cannot transition to state: {PackMLState.RESETTING} when in state: {self.state} state!")
        
        elif cmd == "suspend":
            if self.state == PackMLState.EXECUTE:
                await self.transition_to(PackMLState.SUSPENDING)
            else:
                print(f"Cannot transition to state: {PackMLState.SUSPENDING} when in state: {self.state} state!")
                
        elif cmd == "unsuspend":
            if self.state in [PackMLState.SUSPENDED, PackMLState.SUSPENDING]:
                await self.transition_to(PackMLState.UNSUSPENDING)
            else:
                print(f"Cannot transition to state: {PackMLState.UNSUSPENDING} when in state: {self.state} state!")
        
        elif cmd == "abort":
            if self.state not in [PackMLState.ABORTED, PackMLState.ABORTING]:
                await self.transition_to(PackMLState.ABORTING)
            else:
                print(f"Cannot transition to state: {PackMLState.ABORTING} when in state: {self.state} state!")

    async def execute_state(self):
        print("State: EXECUTE")
        await self.behavior.execute(self)

    async def idle_state(self):
        print("State: IDLE")
        await self.behavior.idle(self)

    async def starting_state(self):
        print("State: STARTING")
        await self.behavior.starting(self)

    async def stopping_state(self):
        print("State: STOPPING")
        await self.behavior.stopping(self)

    async def holding_state(self):
        print("State: HOLDING")
        await self.behavior.holding(self)

    async def unholding_state(self):
        print("State: UNHOLDING")
        await self.behavior.unholding(self)

    async def suspending_state(self):
        print("State: SUSPENDING")
        await self.behavior.suspending(self)

    async def unsuspending_state(self):
        print("State: UNSUSPENDING")
        await self.behavior.unsuspending(self)

    async def completing_state(self):
        print("State: COMPLETING")
        await self.behavior.completing(self)

    async def aborting_state(self):
        print("State: ABORTING")
        await self.behavior.aborting(self)

    async def resetting_state(self):
        print("State: RESETTING")
        await self.behavior.resetting(self)

    async def clearing_state(self):
        print("State: CLEARING")
        await self.behavior.clearing(self)

    async def transition_to(self, new_state):
        self.state = new_state

        # Cancel currently running state task
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()

        # Start new state as background task
        self.current_task = asyncio.create_task(self.run_state(new_state))

    async def run_state(self, state):
        try:
            if state == PackMLState.IDLE:
                self.mqtt_client.publish_state(state)
                await self.idle_state()
            elif state == PackMLState.STARTING:
                self.mqtt_client.publish_state(state)
                await self.starting_state()
            elif state == PackMLState.EXECUTE:
                self.mqtt_client.publish_state(state)
                await self.execute_state()
            elif state == PackMLState.STOPPING:
                self.mqtt_client.publish_state(state)
                await self.stopping_state()
            elif state == PackMLState.HOLDING:
                self.mqtt_client.publish_state(state)
                await self.holding_state()
            elif state == PackMLState.UNHOLDING:
                self.mqtt_client.publish_state(state)
                await self.unholding_state()
            elif state == PackMLState.SUSPENDING:
                self.mqtt_client.publish_state(state)
                await self.suspending_state()
            elif state == PackMLState.UNSUSPENDING:
                self.mqtt_client.publish_state(state)
                await self.unsuspending_state()
            elif state == PackMLState.COMPLETING:
                self.mqtt_client.publish_state(state)
                await self.completing_state()
            elif state == PackMLState.RESETTING:
                self.mqtt_client.publish_state(state)
                await self.resetting_state()
            elif state == PackMLState.ABORTING:
                self.mqtt_client.publish_state(state)
                await self.aborting_state()
            elif state == PackMLState.CLEARING:
                self.mqtt_client.publish_state(state)
                await self.clearing_state()
            elif state == PackMLState.STOPPED:
                self.mqtt_client.publish_state(state)
                print("State: STOPPED")
            elif state == PackMLState.ABORTED:
                self.mqtt_client.publish_state(state)
                print("State: ABORTED")
            elif state == PackMLState.COMPLETE:
                print("State: COMPLETE")
                await self.transition_to(PackMLState.RESETTING)

        except asyncio.CancelledError:
            print(f"{state} cancelled")
            raise


    async def wait_for_state(self, target_state: PackMLState):
        while True:
            if self.state == target_state and (
                self.current_task is None or self.current_task.done()
            ):
                return
            await asyncio.sleep(0.05)










#==========================================================================================================================
#==============================================Only for testing the class==================================================
#==========================================================================================================================

#async def produce_n_products(machine, n):
#    for i in range(n):
#        print(f"\n--- Producing product {i+1} ---")
#
#        # Start cycle
#        await machine.state_command_callback("start")
#
#        await machine.wait_for_state(PackMLState.IDLE)
#
#    print("\nProduction finished.")
#
#
#async def manual_control(machine):
#    while True:
#        cmd = await asyncio.to_thread(input, "Enter command: ")
#        await machine.state_command_callback(cmd)
#
#
#machine = PackMLStateMachine(mqtt_info=mqtt_information)
#
#
#
#async def main():
#    # production_task = asyncio.create_task(produce_n_products(machine, 5))
#    # manual_task = asyncio.create_task(manual_control(machine))
#
#    # await production_task
#
#    # # Optionally cancel manual input when done
#    # manual_task.cancel()
#    while True:
#        await asyncio.sleep(1)
#
#
#asyncio.run(main())