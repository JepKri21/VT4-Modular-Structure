# Line Controller - Complete System

## Architecture Overview

### Three-Layer System

```
┌─────────────────────────────────────────────────────────┐
│ 1. PLANNING LAYER (line_controller.py)                  │
│ ✅ Complete - reads AAS, creates manufacturing plans   │
├─────────────────────────────────────────────────────────┤
│ • BillOfMaterialsResolver - resolves component hierarchy
│ • ManufacturingSequencePlanner - topological sort
│ • ConstraintAwareScheduler - assigns jobs to stations
│ • LineController - orchestrates planning
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 2. MQTT COMMUNICATION (line_controller_mqtt.py)         │
│ ✅ Complete - sends jobs via MQTT, monitors execution  │
├─────────────────────────────────────────────────────────┤
│ • LineControllerMQTT - MQTT client
│ • dispatch_job() - sends to station
│ • wait_for_completion() - monitors status
│ • Integrates with Resource_MQTT_Client protocol
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 3. INTEGRATED EXECUTION (integrated_line_controller.py)│
│ ✅ Complete - combines planning + MQTT execution       │
├─────────────────────────────────────────────────────────┤
│ • plan_product() - create manufacturing plan
│ • execute_plan() - dispatch jobs via MQTT
│ • Tracks real-time execution status
└─────────────────────────────────────────────────────────┘
                        ↓
              Real Manufacturing Stations
              (Drilling_Resource.py, etc.)
```

## How to Use

### Option 1: Planning Only (Current Workflow)

```python
from line_controller import LineController

controller = LineController()
plan = controller.manufacture_product(product_id)
# Returns complete manufacturing plan with all jobs and timing
```

### Option 2: Planning + MQTT Dispatch (New!)

```python
from integrated_line_controller import IntegratedLineController

controller = IntegratedLineController(mqtt_broker="localhost")
controller.connect_mqtt()

# Plan manufacturing
plan = controller.plan_product(telefon_id)

# Execute on real stations
success = controller.execute_plan(wait_for_completion=True)

controller.print_execution_summary()
controller.disconnect_mqtt()
```

## MQTT Protocol (Integrated with Existing System)

### LineController → Station (Job Assignment)

```
Topic: factory/{station_id}/CMD
Payload: {
    "seq_no": 1,
    "job_id": "job_0",
    "product": "Bottom_Cover",
    "operation": "Drilling",
    "command": "start",
    "estimated_duration_ms": 5000,
    "timestamp": "2026-03-11T14:30:00"
}
```

### Station → LineController (Acknowledgement)

```
Topic: factory/{station_id}/controller_ack
Payload: {
    "seq_no": 1,
    "error_code": "NO_ERROR",
    "timestamp": "2026-03-11T14:30:01"
}
```

### Station → LineController (Job Completion)

```
Topic: factory/{station_id}/job_status
Payload: {
    "seq_no": 2,
    "job_id": "job_0",
    "result": "success",
    "cycle_time_ms": 5100,
    "timestamp": "2026-03-11T14:30:06"
}
```

## Key Features

### ✅ Planning

- [x] Read AAS (shells, skills, processes, BoM)
- [x] Resolve hierarchical BoM (fuzzy ID matching)
- [x] Create manufacturing sequence (topological sort)
- [x] Schedule jobs respecting dependencies
- [x] Visualize routing paths (router.py)

### ✅ Execution

- [x] Connect to MQTT broker
- [x] Dispatch jobs with sequence numbers
- [x] Monitor acknowledgements
- [x] Track job completion
- [x] Measure actual cycle time vs planned
- [x] Report execution summary

### ⚠️ Not Yet Implemented (Next Phase)

- [ ] Dynamic rescheduling on station failure
- [ ] Redundant station routing
- [ ] Timing variance analysis
- [ ] Database logging (PSQL_Publisher integration)
- [ ] Live dashboard/visualization
- [ ] Multi-product batching
- [ ] Advanced scheduling (earliest start, lateness minimization)

## Files in Line_Controller/

```
Core Planning:
├── aas_reader.py                  ✅ Read AAS shells & submodels
├── process_planner.py             ✅ Match operations to stations
├── line_controller.py             ✅ Plan manufacturing
└── router.py                      ✅ Visualize routing paths

Execution:
├── line_controller_mqtt.py        ✅ MQTT job dispatch
└── integrated_line_controller.py  ✅ Combined planning + execution

Utilities:
├── example_usage.py               ✅ Usage examples
└── quick_reference.py             ✅ Quick reference patterns
```

## Testing

### Test Planning (No MQTT needed)

```bash
cd Line_Controller
python3 line_controller.py
python3 router.py
```

### Test Planning + MQTT Execution

```bash
# Make sure MQTT broker is running (e.g., mosquitto)
# Make sure at least one station is running (e.g., Drilling_Resource.py)

python3 integrated_line_controller.py
```

## Integration with Existing System

The system integrates seamlessly with:

- ✅ Resource_MQTT_Client.py - exact same MQTT protocol
- ✅ Drilling_Resource.py - already has PackML state machine
- ✅ PackML_Machine_Class.py - handles job execution
- ✅ PSQL_Publisher.py - can log execution data (future integration)

## Constraints & Requirements Handled

| Constraint          | Implementation                              | Status |
| ------------------- | ------------------------------------------- | ------ |
| **Dependency**      | Topological sort + job dependency checks    | ✅     |
| **Resource**        | Station can only do one job at a time       | ✅     |
| **Temporal**        | MQTT waits for station idle before dispatch | ✅     |
| **State**           | MQTT monitors job completion feedback       | ✅     |
| **Failure**         | Can detect job failure via MQTT             | ✅     |
| **Redundancy**      | Not yet implemented                         | ⚠️     |
| **Timing Variance** | Tracks actual vs planned cycle time         | ✅     |

## Next Steps (Recommended)

1. **Test with real stations** - Run integrated_line_controller.py with actual Drilling_Resource
2. **Add failure handling** - Detect station failures and trigger rescheduling
3. **Database logging** - Integrate with PSQL_Publisher to log all executions
4. **Dashboard** - Add real-time web dashboard for monitoring
5. **Multi-product scheduling** - Handle multiple orders concurrently
