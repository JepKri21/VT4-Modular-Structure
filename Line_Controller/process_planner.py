from typing import Dict, List, Tuple, Any
from dataclasses import dataclass


@dataclass
class ProcessStep:
    """Represents a single process step in a product's manufacturing"""
    process_id: str
    process_type: str
    parameters: Dict[str, Any]
    execution_constraints: Dict[str, Any] = None


@dataclass
class StationCapability:
    """Represents what a station can do"""
    station_id: str
    station_name: str
    agent_name: str
    operation_name: str
    estimated_duration: float
    parameters: Dict[str, Any]


@dataclass
class ProcessPlan:
    """Represents a complete process plan for a product"""
    product_id: str
    product_name: str
    required_processes: List[ProcessStep]
    possible_routes: List[List[Tuple[str, str]]]  # List of possible sequences of (station_id, operation_name)


class ProcessPlanner:
    """
    Plans manufacturing processes by matching product requirements with station capabilities.
    
    Takes station skills and product bill of processes, and creates a mapping of which 
    stations can perform which operations for a given product.
    """
    
    def __init__(self, aas_data: Dict[str, Any]):
        """
        Initialize the process planner with AAS data.
        
        Args:
            aas_data: Output from aas_reader.read_aas() containing stations and products
        """
        self.stations = aas_data.get("stations", {})
        self.products = aas_data.get("products", {})
        
        # Build a capability index for quick lookup
        self.capabilities = self._build_capability_index()
    
    def _build_capability_index(self) -> Dict[str, List[StationCapability]]:
        """
        Build an index mapping operation types to stations that can perform them.
        
        Returns:
            {
                "operation_type": [
                    StationCapability(...),
                    StationCapability(...)
                ]
            }
        """
        capabilities = {}
        
        for station_id, station_data in self.stations.items():
            station_name = station_data.get("idShort", station_id)
            skills = station_data.get("skills", {})
            
            # Iterate through agents and their operations
            for agent_name, operations in skills.items():
                for operation_name, operation_data in operations.items():
                    # Use operation_name as the capability key (e.g., "Drilling", "Retrieve")
                    if operation_name not in capabilities:
                        capabilities[operation_name] = []
                    
                    capability = StationCapability(
                        station_id=station_id,
                        station_name=station_name,
                        agent_name=agent_name,
                        operation_name=operation_name,
                        estimated_duration=operation_data.get("Estimated_Duration", 0),
                        parameters=operation_data.get("Parameters", {})
                    )
                    capabilities[operation_name].append(capability)
        
        return capabilities
    
    def get_capabilities_for_operation(self, operation_type: str) -> List[StationCapability]:
        """
        Get all stations that can perform a specific operation type.
        
        Args:
            operation_type: The type of operation (e.g., "Drilling")
        
        Returns:
            List of StationCapability objects
        """
        return self.capabilities.get(operation_type, [])
    
    def generate_process_plan(self, product_id: str) -> ProcessPlan:
        """
        Generate a process plan for a specific product.
        
        This analyzes the product's Bill_Of_Processes and finds all stations that
        can perform each required operation.
        
        Args:
            product_id: The ID of the product to plan for
        
        Returns:
            ProcessPlan object containing required processes and possible routes
        
        Raises:
            ValueError: If product not found
        """
        if product_id not in self.products:
            raise ValueError(f"Product {product_id} not found")
        
        product_data = self.products[product_id]
        product_name = product_data.get("idShort", product_id)
        
        # Extract required processes from Bill_Of_Processes
        required_processes = []
        processes_raw = product_data.get("processes", [])
        
        for process in processes_raw:
            process_step = ProcessStep(
                process_id=process.get("Process_Id", ""),
                process_type=process.get("Process_Type", ""),
                parameters=process.get("Parameters", {}),
                execution_constraints=process.get("Execution_Constraints", {})
            )
            required_processes.append(process_step)
        
        # Find possible stations for each process
        possible_routes = self._find_possible_routes(required_processes)
        
        return ProcessPlan(
            product_id=product_id,
            product_name=product_name,
            required_processes=required_processes,
            possible_routes=possible_routes
        )
    
    def _find_possible_routes(self, required_processes: List[ProcessStep]) -> List[List[Tuple[str, str]]]:
        """
        Find all possible routes through stations for a given set of required processes.
        
        Args:
            required_processes: List of ProcessStep objects
        
        Returns:
            List of possible routes, where each route is a list of (station_id, operation_name) tuples
        """
        # For each process, get all stations that can do it
        options_per_step = []
        
        for step in required_processes:
            matching_capabilities = self.get_capabilities_for_operation(step.process_type)
            
            if not matching_capabilities:
                print(f"WARNING: No station found for operation '{step.process_type}'")
                return []  # Can't complete the process
            
            # Create (station_id, operation_name) tuples
            options = [(cap.station_id, cap.operation_name) for cap in matching_capabilities]
            options_per_step.append(options)
        
        # Generate all combinations (Cartesian product)
        if not options_per_step:
            return []
        
        from itertools import product
        possible_routes = [list(route) for route in product(*options_per_step)]
        
        return possible_routes
    
    def get_process_plan_summary(self, product_id: str) -> str:
        """
        Get a human-readable summary of a process plan.
        
        Args:
            product_id: The ID of the product
        
        Returns:
            Formatted string with process plan details
        """
        plan = self.generate_process_plan(product_id)
        
        summary = []
        summary.append(f"\n{'='*70}")
        summary.append(f"PROCESS PLAN: {plan.product_name}")
        summary.append(f"{'='*70}\n")
        
        summary.append("REQUIRED PROCESSES:")
        for i, process in enumerate(plan.required_processes, 1):
            summary.append(f"  {i}. {process.process_type} (ID: {process.process_id})")
        
        summary.append(f"\nPOSSIBLE ROUTES: {len(plan.possible_routes)} option(s)\n")
        
        for route_idx, route in enumerate(plan.possible_routes, 1):
            summary.append(f"Route {route_idx}:")
            for step_idx, (station_id, operation) in enumerate(route, 1):
                station_name = self.stations[station_id].get("idShort", station_id)
                
                # Find duration for this capability
                duration = "N/A"
                capabilities = self.get_capabilities_for_operation(operation)
                for cap in capabilities:
                    if cap.station_id == station_id:
                        duration = f"{cap.estimated_duration}s"
                        break
                
                summary.append(f"  Step {step_idx}: {station_name} → {operation} ({duration})")
            summary.append("")
        
        return "\n".join(summary)


if __name__ == "__main__":
    # Example usage
    from aas_reader import read_aas
    
    # Read AAS data
    aas_data = read_aas()
    
    # Create planner
    planner = ProcessPlanner(aas_data)
    
    # Print capability index
    print("\n" + "="*70)
    print("STATION CAPABILITIES")
    print("="*70)
    for op_type, capabilities in sorted(planner.capabilities.items()):
        print(f"\n{op_type}:")
        for cap in capabilities:
            print(f"  - {cap.station_name}: {cap.estimated_duration}s")
    
    # Generate process plans for each product
    print("\n" + "="*70)
    print("PROCESS PLANS FOR EACH PRODUCT")
    print("="*70)
    
    for product_id, product_data in aas_data["products"].items():
        if product_data.get("processes"):  # Only products with processes
            try:
                summary = planner.get_process_plan_summary(product_id)
                print(summary)
            except ValueError as e:
                print(f"Skipping {product_data.get('idShort')}: {e}")