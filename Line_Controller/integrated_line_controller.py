"""
Integrated Line Controller with MQTT Execution
Combines manufacturing planning with real-time MQTT-based job dispatch
"""

from line_controller import LineController as PlanningController
from line_controller_mqtt import LineControllerMQTT, JobState
import time
from typing import Optional, Dict, Any


class IntegratedLineController:
    """
    Complete manufacturing line controller that:
    1. Plans manufacturing (topological sort, scheduling)
    2. Dispatches jobs via MQTT to real stations
    3. Monitors execution and tracks completion
    """
    
    def __init__(self, mqtt_broker: str = "localhost", mqtt_port: int = 1883, 
                 base_topic: str = "factory"):
        """
        Initialize integrated controller.
        
        Args:
            mqtt_broker: MQTT broker hostname
            mqtt_port: MQTT broker port
            base_topic: Base topic for MQTT communication
        """
        self.planner = PlanningController()
        self.executor = LineControllerMQTT(broker=mqtt_broker, port=mqtt_port, 
                                          base_topic=base_topic)
        self.manufacturing_plan = None
        self.product_id = None
    
    def connect_mqtt(self) -> bool:
        """Connect to MQTT broker"""
        return self.executor.connect()
    
    def disconnect_mqtt(self):
        """Disconnect from MQTT broker"""
        self.executor.disconnect()
    
    def plan_product(self, product_id: str) -> Dict[str, Any]:
        """
        Plan manufacturing for a product (planning phase).
        
        Args:
            product_id: Product to manufacture
            
        Returns:
            Manufacturing plan dict
        """
        self.product_id = product_id
        self.manufacturing_plan = self.planner.manufacture_product(product_id)
        return self.manufacturing_plan
    
    def execute_plan(self, wait_for_completion: bool = True) -> bool:
        """
        Execute the manufacturing plan via MQTT (execution phase).
        
        Args:
            wait_for_completion: Wait for all jobs to complete
            
        Returns:
            True if execution succeeded, False if any job failed
        """
        if not self.manufacturing_plan:
            print("No plan loaded. Call plan_product() first.")
            return False
        
        if not self.executor.connected:
            print("Not connected to MQTT. Call connect_mqtt() first.")
            return False
        
        # Extract schedule from plan
        schedule = self.manufacturing_plan.get('schedule', [])
        
        print(f"\n{'='*80}")
        print("EXECUTING MANUFACTURING PLAN")
        print(f"{'='*80}\n")
        
        print(f"Dispatching {len(schedule)} jobs...\n")
        
        # Dispatch all jobs
        for i, job in enumerate(schedule, 1):
            job_id = job.get('job_id')
            product = job.get('product')
            operation = job.get('operation')
            station = job.get('station')
            
            # Extract station name from shell ID
            station_name = station.split('/')[-1] if '/' in station else station
            
            # Duration: convert from seconds to milliseconds
            duration_s = job.get('duration', 0)
            duration_ms = int(duration_s * 1000)
            
            # Find actual station ID in AAS data
            station_id = None
            for sid, sdata in self.planner.aas_data['stations'].items():
                if sdata.get('idShort') == station_name or sid == station:
                    station_id = sid
                    break
            
            if not station_id:
                station_id = station_name  # Fallback to name if not found
            
            print(f"  {i}. {job_id}: {product} → {operation}")
            print(f"     Station: {station_name} ({duration_s:.1f}s)")
            
            success = self.executor.dispatch_job(
                job_id=job_id,
                product_name=product,
                operation=operation,
                station_id=station_id,
                duration_ms=duration_ms
            )
            
            if not success:
                print(f"     ✗ Failed to dispatch")
                return False
        
        print(f"\nAll jobs dispatched. Waiting for execution...\n")
        
        if wait_for_completion:
            # Wait for all jobs
            all_completed = self._wait_all_jobs(schedule)
            
            if all_completed:
                print("\n✓ All jobs completed successfully")
                return True
            else:
                print("\n✗ Some jobs failed or timed out")
                return False
        else:
            return True
    
    def _wait_all_jobs(self, schedule: list, timeout_s: float = 600) -> bool:
        """Wait for all jobs to complete"""
        job_ids = [j['job_id'] for j in schedule]
        start_time = time.time()
        last_status_time = start_time
        
        while time.time() - start_time < timeout_s:
            # Print status every 5 seconds
            if time.time() - last_status_time > 5:
                completed = sum(1 for jid in job_ids 
                              if self.executor.get_job_state(jid) == JobState.COMPLETED)
                print(f"Progress: {completed}/{len(job_ids)} jobs completed")
                last_status_time = time.time()
            
            # Check if all jobs done
            all_done = True
            any_failed = False
            
            for job_id in job_ids:
                state = self.executor.get_job_state(job_id)
                if state == JobState.FAILED:
                    any_failed = True
                    print(f"✗ Job {job_id} failed")
                elif state not in [JobState.COMPLETED, JobState.FAILED]:
                    all_done = False
            
            if any_failed:
                return False
            
            if all_done:
                return True
            
            time.sleep(0.5)
        
        print("Timeout waiting for job completion")
        return False
    
    def print_execution_summary(self):
        """Print summary of execution"""
        self.executor.print_job_summary()


if __name__ == "__main__":
    # Example: Plan and execute
    controller = IntegratedLineController()
    
    # Plan
    print("="*80)
    print("PLANNING PHASE")
    print("="*80)
    
    # Find Telefon product
    telefon_id = None
    for pid, pdata in controller.planner.aas_data['products'].items():
        if pdata['idShort'] == 'Telefon':
            telefon_id = pid
            break
    
    if telefon_id:
        plan = controller.plan_product(telefon_id)
        
        print(f"\nProduct: {plan['product']}")
        print(f"Components: {len(plan['components'])}")
        print(f"Jobs: {plan['total_jobs']}")
        print(f"Makespan: {plan['makespan']:.1f}s")
        
        # Connect and execute
        if controller.connect_mqtt():
            time.sleep(1)  # Give time to connect
            
            success = controller.execute_plan(wait_for_completion=False)
            
            # Print status
            time.sleep(2)
            controller.print_execution_summary()
            
            controller.disconnect_mqtt()
        else:
            print("Could not connect to MQTT broker")
