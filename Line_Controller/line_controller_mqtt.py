"""
Line Controller MQTT Integration
Sends manufacturing jobs to real stations via MQTT and monitors execution
"""

import paho.mqtt.client as mqtt
import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import threading


class JobState(Enum):
    """State of a job during execution"""
    PLANNED = "planned"
    DISPATCHED = "dispatched"
    ACKNOWLEDGED = "acknowledged"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobAssignment:
    """A job ready to be sent to a station"""
    job_id: str
    product_name: str
    operation_type: str
    station_id: str
    station_topic_base: str
    duration_ms: int
    seq_no: int = 0
    state: JobState = JobState.PLANNED
    ack_received: bool = False
    actual_cycle_time_ms: Optional[int] = None


class LineControllerMQTT:
    """
    Controls manufacturing line via MQTT.
    
    Sends jobs to stations and monitors execution.
    """
    
    def __init__(self, broker: str = "localhost", port: int = 1883, base_topic: str = "factory"):
        self.broker = broker
        self.port = port
        self.base_topic = base_topic
        
        self.client = mqtt.Client(client_id="LineController", callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        
        self.jobs: Dict[str, JobAssignment] = {}
        self.seq_no = 1
        self.station_acks: Dict[int, Dict[str, Any]] = {}  # seq_no -> ack data
        self.job_completions: Dict[str, Dict[str, Any]] = {}  # job_id -> completion data
        
        self._lock = threading.Lock()
        self.connected = False
    
    def connect(self):
        """Connect to MQTT broker"""
        try:
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            print(f"[LineController] Connecting to MQTT broker at {self.broker}:{self.port}")
            return True
        except Exception as e:
            print(f"[LineController] Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from MQTT broker"""
        self.client.loop_stop()
        self.client.disconnect()
        self.connected = False
    
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            print("[LineController] Connected to MQTT broker")
            self.connected = True
            # Subscribe to all station acknowledgements and job status
            client.subscribe(f"{self.base_topic}/+/controller_ack")
            client.subscribe(f"{self.base_topic}/+/job_status")
        else:
            print(f"[LineController] Connection failed with code {rc}")
    
    def _on_message(self, client, userdata, msg):
        """MQTT message callback"""
        topic = msg.topic
        payload = json.loads(msg.payload.decode())
        
        try:
            if "controller_ack" in topic:
                self._handle_ack(payload)
            elif "job_status" in topic:
                self._handle_job_status(payload)
        except Exception as e:
            print(f"[LineController] Error processing message: {e}")
    
    def _handle_ack(self, payload: Dict[str, Any]):
        """Handle acknowledgement from station"""
        seq_no = payload.get("seq_no")
        error_code = payload.get("error_code")
        
        if error_code == "NO_ERROR":
            print(f"[LineController] ACK received: seq_no={seq_no}")
            with self._lock:
                self.station_acks[seq_no] = payload
                # Mark corresponding job as acknowledged
                for job in self.jobs.values():
                    if job.seq_no == seq_no:
                        job.ack_received = True
                        job.state = JobState.ACKNOWLEDGED
        else:
            print(f"[LineController] ACK error: seq_no={seq_no}, error={error_code}")
    
    def _handle_job_status(self, payload: Dict[str, Any]):
        """Handle job completion status from station"""
        job_id = payload.get("job_id")
        result = payload.get("result")
        cycle_time_ms = payload.get("cycle_time_ms")
        
        print(f"[LineController] Job status: {job_id}={result} ({cycle_time_ms}ms)")
        
        with self._lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                if result == "success":
                    job.state = JobState.COMPLETED
                    job.actual_cycle_time_ms = cycle_time_ms
                else:
                    job.state = JobState.FAILED
            
            self.job_completions[job_id] = payload
    
    def dispatch_job(self, job_id: str, product_name: str, operation: str, 
                     station_id: str, duration_ms: int) -> bool:
        """
        Dispatch a job to a station.
        
        Args:
            job_id: Unique job identifier
            product_name: Name of product being manufactured
            operation: Operation to perform (e.g., "Drilling")
            station_id: Target station identifier
            duration_ms: Expected duration in milliseconds
            
        Returns:
            True if dispatched successfully
        """
        if not self.connected:
            print(f"[LineController] Not connected to MQTT broker, cannot dispatch job")
            return False
        
        with self._lock:
            seq_no = self.seq_no
            self.seq_no += 1
            
            # Create job assignment
            job = JobAssignment(
                job_id=job_id,
                product_name=product_name,
                operation_type=operation,
                station_id=station_id,
                station_topic_base=f"{self.base_topic}/{station_id}",
                duration_ms=duration_ms,
                seq_no=seq_no
            )
            self.jobs[job_id] = job
        
        # Prepare command
        command_payload = {
            "seq_no": seq_no,
            "job_id": job_id,
            "product": product_name,
            "operation": operation,
            "command": "start",
            "estimated_duration_ms": duration_ms,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
        
        # Send to station
        topic = f"{self.base_topic}/{station_id}/CMD"
        try:
            self.client.publish(topic, json.dumps(command_payload))
            job.state = JobState.DISPATCHED
            print(f"[LineController] Dispatched {job_id} to {station_id}")
            return True
        except Exception as e:
            print(f"[LineController] Failed to dispatch job: {e}")
            return False
    
    def wait_for_job_completion(self, job_id: str, timeout_s: float = 600) -> bool:
        """
        Wait for a job to complete.
        
        Args:
            job_id: Job to wait for
            timeout_s: Maximum time to wait (seconds)
            
        Returns:
            True if job completed successfully, False on timeout or failure
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout_s:
            with self._lock:
                if job_id in self.jobs:
                    job = self.jobs[job_id]
                    if job.state == JobState.COMPLETED:
                        return True
                    elif job.state == JobState.FAILED:
                        return False
            
            time.sleep(0.1)
        
        print(f"[LineController] Timeout waiting for job {job_id}")
        return False
    
    def get_job_state(self, job_id: str) -> Optional[JobState]:
        """Get current state of a job"""
        with self._lock:
            job = self.jobs.get(job_id)
            return job.state if job else None
    
    def get_job_info(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed info about a job"""
        with self._lock:
            job = self.jobs.get(job_id)
            if job:
                return {
                    'job_id': job.job_id,
                    'product': job.product_name,
                    'operation': job.operation_type,
                    'station': job.station_id,
                    'state': job.state.value,
                    'planned_duration_ms': job.duration_ms,
                    'actual_duration_ms': job.actual_cycle_time_ms,
                    'ack_received': job.ack_received
                }
            return None
    
    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """Get info about all jobs"""
        with self._lock:
            return [
                {
                    'job_id': job.job_id,
                    'product': job.product_name,
                    'operation': job.operation_type,
                    'station': job.station_id,
                    'state': job.state.value,
                    'planned_ms': job.duration_ms,
                    'actual_ms': job.actual_cycle_time_ms
                }
                for job in self.jobs.values()
            ]
    
    def print_job_summary(self):
        """Print summary of all jobs"""
        with self._lock:
            jobs = list(self.jobs.values())
        
        print("\n" + "=" * 80)
        print("JOB EXECUTION SUMMARY")
        print("=" * 80)
        
        completed = sum(1 for j in jobs if j.state == JobState.COMPLETED)
        failed = sum(1 for j in jobs if j.state == JobState.FAILED)
        running = sum(1 for j in jobs if j.state == JobState.RUNNING)
        dispatched = sum(1 for j in jobs if j.state == JobState.DISPATCHED)
        
        print(f"\nTotal Jobs: {len(jobs)}")
        print(f"  Completed: {completed}")
        print(f"  Running: {running}")
        print(f"  Dispatched: {dispatched}")
        print(f"  Failed: {failed}")
        
        print(f"\nJob Details:")
        for job in sorted(jobs, key=lambda j: j.job_id):
            status_icon = {
                JobState.COMPLETED: "✓",
                JobState.RUNNING: "►",
                JobState.FAILED: "✗",
                JobState.DISPATCHED: "⊳",
                JobState.ACKNOWLEDGED: "→",
                JobState.PLANNED: " "
            }.get(job.state, "?")
            
            variance = ""
            if job.actual_cycle_time_ms:
                variance = f" ({job.actual_cycle_time_ms - job.duration_ms:+d}ms)"
            
            print(f"  {status_icon} {job.job_id}: {job.product_name} → {job.operation_type}")
            print(f"      Station: {job.station_id}")
            print(f"      Duration: {job.duration_ms}ms{variance}")


if __name__ == "__main__":
    # Example usage
    controller = LineControllerMQTT(broker="localhost", port=1883)
    
    if controller.connect():
        # Give it time to connect
        time.sleep(1)
        
        # Example: Dispatch some jobs
        jobs = [
            ("job_1", "Bottom_Cover", "Drilling", "Drill_Station", 5000),
            ("job_2", "Housing", "Assemble", "Assembler_1", 8000),
        ]
        
        for job_id, product, operation, station, duration in jobs:
            controller.dispatch_job(job_id, product, operation, station, duration)
            print(f"Dispatched {job_id}")
        
        # Wait a bit and check status
        time.sleep(2)
        controller.print_job_summary()
        
        controller.disconnect()
