# Line Controller - Process Planning System

Dette system læser Asset Administration Shell (AAS) data fra Basyx serveren og genererer process plans for produkter baseret på station capabilities.

## Komponenter

### 1. `aas_reader.py`

Læser alle shells og submodels fra Basyx serveren og ekstraherer:

- **Skills** fra Resource shells (stations)
- **Bill_Of_Processes** fra Product shells

**Struktur af returneret data:**

```python
{
    "stations": {
        "station_id": {
            "id": "...",
            "idShort": "Station Name",
            "skills": {
                "agent_name": {
                    "operation_name": {
                        "Estimated_Duration": 5.0,
                        "Parameters": {...}
                    }
                }
            }
        }
    },
    "products": {
        "product_id": {
            "id": "...",
            "idShort": "Product Name",
            "processes": [
                {
                    "Process_Id": "Drilling_1",
                    "Process_Type": "Drilling",
                    "Parameters": {...}
                }
            ]
        }
    }
}
```

**Brug:**

```python
from aas_reader import read_aas

aas_data = read_aas()
stations = aas_data["stations"]
products = aas_data["products"]
```

### 2. `process_planner.py`

Genererer process plans ved at matche produkt-behov med station-capabilities.

**Vigtige klasser:**

#### `ProcessPlanner`

```python
planner = ProcessPlanner(aas_data)

# Find hvilke stationer der kan lave Drilling
drilling_stations = planner.get_capabilities_for_operation("Drilling")

# Generer process plan for et produkt
plan = planner.generate_process_plan(product_id)
# Returns ProcessPlan med:
#   - required_processes: Liste af operationer produktet kræver
#   - possible_routes: Alle mulige kombinationer af stationer

# Få human-readable summary
summary = planner.get_process_plan_summary(product_id)
```

#### `ProcessPlan`

```python
@dataclass
class ProcessPlan:
    product_id: str
    product_name: str
    required_processes: List[ProcessStep]  # Hvad skal laves
    possible_routes: List[List[Tuple[str, str]]]  # Hvor kan det laves
```

#### `StationCapability`

```python
@dataclass
class StationCapability:
    station_id: str
    station_name: str
    agent_name: str
    operation_name: str
    estimated_duration: float
    parameters: Dict[str, Any]
```

## Eksempel: Process Plan for Bottom_Cover

Bottom_Cover kræver Drilling operation:

- Kun Drill_Station kan lave Drilling
- Estimeret varighed: 5 sekunder
- 1 mulig route

## Status på stationer

### Stationer med Skills:

- ✅ **Drill_Station**: Drilling (5s)
- ✅ **Bottom_Cover_Storage**: Retrieve (8s)
- ✅ **ACOPOS6D**: Transport (3s)

### Stationer UDEN Skills:

- ❌ **PCB_And_Cover_Assembler**: Mangler Skills submodel
- ❌ **PCB_And_Fuse_Assembler**: Mangler Skills submodel
- ❌ **Telefon_Assembler**: Mangler Skills submodel

For at få flere product-routes, skal disse stations have Skills submodels uploadet med "Assemble" operation.

## Næste trin

Med process plans kan du nu bygge:

### 1. **scheduler.py**

Assign jobs til stationer med tidsbaserede constraints

- Input: ProcessPlan for et produkt
- Output: Schedule med start/slut-tider for hver operation

### 2. **router.py**

Route produkter mellem stationer

- Input: ProcessPlan route
- Output: Transport- og håndteringsinstruktioner

### 3. **order_manager.py**

Administrer produkt-ordrer

- Input: Ordre med produkter
- Output: Track status gennem alle stationer

## Udvidelse af systemet

For at tilføje nye stationer:

1. Upload shell med submodels til Basyx
2. Opret Skills submodel med Agents → Operations struktur
3. Definer Estimated_Duration for hver operation
4. Run `aas_reader.py` igen - systemet finder automatisk nye capabilities

For at tilføje nye produkter:

1. Upload shell med Bill_Of_Processes submodel
2. Definer List_Of_Processes med required operationer
3. Run `process_planner.py` - systemet matcher automatisk med stations

## Testing

```bash
# Test aas_reader
python3 aas_reader.py

# Test process_planner
python3 process_planner.py

# Se full example
python3 example_usage.py
```
