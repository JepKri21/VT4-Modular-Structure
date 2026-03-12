"""
Line Controller - Complete Manufacturing Execution System

Handles:
1. BoM dependency resolution (hierarchical product structure)
2. Manufacturing sequence planning (respects dependencies)
3. Constraint-aware scheduling (assigns jobs to stations respecting time/dependencies)
4. Product routing (tracks product through manufacturing line)
"""

from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import json
from aas_reader import read_aas
from process_planner import ProcessPlanner


class JobStatus(Enum):
    """Status of a manufacturing job"""
    WAITING = "waiting"  # Waiting for dependencies
    READY = "ready"  # All dependencies satisfied
    RUNNING = "running"  # Currently executing
    COMPLETED = "completed"  # Done
    FAILED = "failed"  # Error occurred


@dataclass
class ManufacturingJob:
    """Represents a single manufacturing job"""
    job_id: str
    product_id: str
    product_name: str
    operation_type: str
    assigned_station: Optional[str] = None
    duration: float = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    status: JobStatus = JobStatus.WAITING
    dependencies: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    def is_ready(self, completed_jobs: Set[str]) -> bool:
        """Check if all dependencies are satisfied"""
        return all(dep in completed_jobs for dep in self.dependencies)


@dataclass
class ManufacturingPlan:
    """Complete manufacturing plan for a product"""
    product_id: str
    product_name: str
    all_components: List[str]  # All sub-products needed (BOM flattened)
    jobs: List[ManufacturingJob]
    dependency_graph: Dict[str, List[str]]  # Maps component to its dependencies


class BillOfMaterialsResolver:
    """Resolves hierarchical Bill of Materials to flatten component structure"""
    
    def __init__(self, aas_data: Dict[str, Any]):
        self.aas_data = aas_data
        self.products = aas_data.get("products", {})
        self._bom_cache = {}  # Cache resolved BOMs
        self._product_name_to_id = {}  # Map product names to IDs for fuzzy matching
        
        # Build name-to-ID mapping for fuzzy matching
        for product_id, product_data in self.products.items():
            id_short = product_data.get("idShort", "")
            if id_short:
                self._product_name_to_id[id_short] = product_id
    
    def _find_product_by_id(self, component_id: str) -> str:
        """
        Find a product ID, with fallback to fuzzy matching by name.
        If exact ID not found, try extracting the product name from the ID
        and matching against known product names.
        """
        # Try exact match first
        if component_id in self.products:
            return component_id
        
        # Try fuzzy match: extract product name from URL
        # URL format: .../Product_Type/AAU/Product_Name/001
        parts = component_id.split("/")
        if len(parts) >= 3:
            product_name = parts[-2]  # The part before /001 or version
            if product_name in self._product_name_to_id:
                return self._product_name_to_id[product_name]
        
        return None
    
    def get_components_for_product(self, product_id: str) -> List[str]:
        """
        Get all component IDs required for a product (flattened).
        
        Args:
            product_id: The product to analyze
        
        Returns:
            List of all component product IDs needed (recursively)
        """
        if product_id in self._bom_cache:
            return self._bom_cache[product_id]
        
        components = []
        product = self.products.get(product_id, {})
        
        # Get direct components from Bill_Of_Materials
        direct_components = product.get("components", [])
        
        # Recursively expand each component
        for component_id in direct_components:
            # Resolve the actual product ID (with fuzzy matching if needed)
            actual_id = self._find_product_by_id(component_id)
            if actual_id:
                components.append(actual_id)
                # Recursively get sub-components
                sub_components = self.get_components_for_product(actual_id)
                components.extend(sub_components)
        
        self._bom_cache[product_id] = components
        return components
    
    def get_dependency_graph(self, product_id: str) -> Dict[str, List[str]]:
        """
        Get the dependency graph for a product.
        Maps each component to its direct dependencies.
        
        Example:
            {
                "Telefon": ["PCB_With_Fuse", "Top_Cover"],
                "PCB_With_Fuse": ["Fuse", "Housing_With_PCB"],
                "Housing_With_PCB": ["PCB", "Bottom_Cover"],
                "Bottom_Cover": [],
                ...
            }
        """
        graph = {}
        
        def build_graph(product_id: str):
            if product_id in graph:
                return  # Already processed
            
            product = self.products.get(product_id, {})
            direct_components = product.get("components", [])
            graph[product_id] = direct_components
            
            # Recursively build graph for all sub-components
            for component_id in direct_components:
                build_graph(component_id)
        
        build_graph(product_id)
        return graph


class ManufacturingSequencePlanner:
    """Plans manufacturing sequence respecting BoM dependencies"""
    
    def __init__(self, aas_data: Dict[str, Any], planner: ProcessPlanner):
        self.aas_data = aas_data
        self.process_planner = planner
        self.bom_resolver = BillOfMaterialsResolver(aas_data)
    
    def plan_manufacturing(self, product_id: str) -> ManufacturingPlan:
        """
        Create a manufacturing plan for a product.
        
        This plan accounts for:
        1. All sub-components needed (BoM dependencies)
        2. What operations each component needs
        3. Which stations can do each operation
        4. Optimal manufacturing sequence
        
        Args:
            product_id: The top-level product to manufacture
        
        Returns:
            ManufacturingPlan with all jobs and dependencies
        """
        product = self.aas_data["products"].get(product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")
        
        product_name = product.get("idShort", product_id)
        
        # Get all components needed (flattened BoM)
        all_components = self._get_all_components_recursive(product_id)
        
        # Build dependency graph
        dep_graph = self._build_dependency_graph(product_id)
        
        # Create manufacturing jobs
        jobs = []
        job_counter = 0
        job_ids_by_product = {}  # Maps product_id to list of its job_ids
        
        # Process each component in dependency order
        for component_id in self._topological_sort(dep_graph):
            component = self.aas_data["products"].get(component_id)
            if not component:
                continue
            
            component_name = component.get("idShort", component_id)
            processes = component.get("processes", [])
            
            # Create a job for each process
            for process in processes:
                job_id = f"job_{job_counter}"
                job_counter += 1
                
                process_type = process.get("Process_Type", "")
                
                # Find dependencies: jobs from components this product depends on
                component_deps = dep_graph.get(component_id, [])
                dependency_job_ids = []
                for dep_component in component_deps:
                    if dep_component in job_ids_by_product:
                        dependency_job_ids.extend(job_ids_by_product[dep_component])
                
                # Get capabilities for this operation
                capabilities = self.process_planner.get_capabilities_for_operation(process_type)
                
                if capabilities:
                    # Use first capable station (can be optimized later)
                    cap = capabilities[0]
                    
                    job = ManufacturingJob(
                        job_id=job_id,
                        product_id=component_id,
                        product_name=component_name,
                        operation_type=process_type,
                        assigned_station=cap.station_id,
                        duration=cap.estimated_duration,
                        dependencies=dependency_job_ids,
                        parameters=cap.parameters
                    )
                    jobs.append(job)
                    
                    if component_id not in job_ids_by_product:
                        job_ids_by_product[component_id] = []
                    job_ids_by_product[component_id].append(job_id)
        
        # Create final assembly job (top-level product)
        if product.get("processes"):
            for process in product["processes"]:
                job_id = f"job_{job_counter}"
                job_counter += 1
                
                process_type = process.get("Process_Type", "")
                capabilities = self.process_planner.get_capabilities_for_operation(process_type)
                
                if capabilities:
                    cap = capabilities[0]
                    
                    # This job depends on all component jobs
                    component_job_deps = []
                    for comp_jobs in job_ids_by_product.values():
                        component_job_deps.extend(comp_jobs)
                    
                    job = ManufacturingJob(
                        job_id=job_id,
                        product_id=product_id,
                        product_name=product_name,
                        operation_type=process_type,
                        assigned_station=cap.station_id,
                        duration=cap.estimated_duration,
                        dependencies=component_job_deps,
                        parameters=cap.parameters
                    )
                    jobs.append(job)
        
        return ManufacturingPlan(
            product_id=product_id,
            product_name=product_name,
            all_components=all_components,
            jobs=jobs,
            dependency_graph=dep_graph
        )
    
    def _get_all_components_recursive(self, product_id: str, visited: Set[str] = None) -> List[str]:
        """Get all components recursively (flattened BoM) from actual Bill_Of_Materials"""
        if visited is None:
            visited = set()
        
        if product_id in visited:
            return []
        
        visited.add(product_id)
        components = [product_id]
        
        # Use BOM resolver to get actual component structure from submodels
        direct_components = self.bom_resolver.get_components_for_product(product_id)
        
        for component_id in direct_components:
            # Recursively get sub-components
            components.extend(self._get_all_components_recursive(component_id, visited))
        
        return components
    
    def _build_dependency_graph(self, product_id: str) -> Dict[str, List[str]]:
        """Build dependency graph using actual Bill_Of_Materials from submodels"""
        graph = {}
        
        def build_graph(prod_id: str):
            if prod_id in graph:
                return
            # Use BOM resolver to get direct dependencies
            direct_component_refs = self.bom_resolver.products.get(prod_id, {}).get("components", [])
            # Resolve each component reference to actual product ID
            direct_deps = []
            for comp_ref in direct_component_refs:
                actual_id = self.bom_resolver._find_product_by_id(comp_ref)
                if actual_id:
                    direct_deps.append(actual_id)
            
            graph[prod_id] = direct_deps
            for dep in direct_deps:
                build_graph(dep)
        
        build_graph(product_id)
        return graph
    
    def _topological_sort(self, graph: Dict[str, List[str]]) -> List[str]:
        """
        Topological sort of dependency graph.
        Returns products in order where dependencies come before dependents.
        """
        visited = set()
        stack = []
        
        def visit(node: str):
            if node in visited:
                return
            visited.add(node)
            for dep in graph.get(node, []):
                visit(dep)
            stack.append(node)
        
        for node in graph:
            visit(node)
        
        return stack


class ConstraintAwareScheduler:
    """Schedules jobs respecting dependencies and station constraints"""
    
    def schedule(self, plan: ManufacturingPlan, start_time: float = 0) -> Dict[str, ManufacturingJob]:
        """
        Schedule all jobs respecting:
        1. Dependency constraints (dependencies must complete first)
        2. Station availability (one job per station at a time)
        3. Time continuity (no negative durations)
        
        Args:
            plan: The manufacturing plan
            start_time: Global start time
        
        Returns:
            Updated jobs with scheduled times
        """
        jobs = {job.job_id: job for job in plan.jobs}
        completed = set()
        current_time = start_time
        
        # Simple greedy scheduler: process jobs as soon as dependencies are met
        max_iterations = len(jobs) * 2
        iteration = 0
        
        while len(completed) < len(jobs) and iteration < max_iterations:
            iteration += 1
            scheduled_this_iteration = False
            
            for job in plan.jobs:
                if job.job_id in completed:
                    continue
                
                # Check if dependencies are satisfied
                if not job.is_ready(completed):
                    continue
                
                # Find when this job can start
                job_start_time = current_time
                
                # Check if station has other jobs
                for other_job in plan.jobs:
                    if other_job.job_id == job.job_id or other_job.job_id not in completed:
                        continue
                    if other_job.assigned_station == job.assigned_station:
                        job_start_time = max(job_start_time, other_job.end_time or 0)
                
                # Schedule the job
                job.status = JobStatus.RUNNING
                job.start_time = job_start_time
                job.end_time = job_start_time + job.duration
                completed.add(job.job_id)
                scheduled_this_iteration = True
                
                # Update current time
                current_time = max(current_time, job.end_time)
            
            if not scheduled_this_iteration:
                break
        
        return jobs


class LineController:
    """Main controller orchestrating the entire manufacturing line"""
    
    def __init__(self):
        self.aas_data = read_aas()
        self.process_planner = ProcessPlanner(self.aas_data)
        self.sequence_planner = ManufacturingSequencePlanner(
            self.aas_data, self.process_planner
        )
        self.scheduler = ConstraintAwareScheduler()
    
    def manufacture_product(self, product_id: str) -> Dict[str, Any]:
        """
        Complete manufacturing orchestration for a product.
        
        Returns:
            Dictionary with plan and schedule information
        """
        # Step 1: Create manufacturing plan
        plan = self.sequence_planner.plan_manufacturing(product_id)
        
        # Step 2: Schedule jobs
        scheduled_jobs = self.scheduler.schedule(plan)
        
        # Compile results
        result = {
            "product": plan.product_name,
            "components": plan.all_components,
            "total_jobs": len(plan.jobs),
            "makespan": max((j.end_time for j in scheduled_jobs.values()), default=0),
            "jobs": scheduled_jobs,
            "schedule": self._format_schedule(scheduled_jobs),
            "by_station": self._group_by_station(scheduled_jobs)
        }
        
        return result
    
    def _format_schedule(self, jobs: Dict[str, ManufacturingJob]) -> List[Dict[str, Any]]:
        """Format scheduled jobs chronologically"""
        job_list = sorted(
            jobs.values(),
            key=lambda j: j.start_time or float('inf')
        )
        
        return [
            {
                "job_id": j.job_id,
                "product": j.product_name,
                "operation": j.operation_type,
                "station": j.assigned_station,
                "start": j.start_time,
                "end": j.end_time,
                "duration": j.duration,
                "status": j.status.value
            }
            for j in job_list
        ]
    
    def _group_by_station(self, jobs: Dict[str, ManufacturingJob]) -> Dict[str, List[Dict[str, Any]]]:
        """Group scheduled jobs by station"""
        by_station = {}
        
        for job in jobs.values():
            station = job.assigned_station
            if station not in by_station:
                by_station[station] = []
            
            by_station[station].append({
                "job_id": job.job_id,
                "product": job.product_name,
                "operation": job.operation_type,
                "start": job.start_time,
                "end": job.end_time,
                "duration": job.duration
            })
        
        # Sort by start time
        for station in by_station:
            by_station[station].sort(key=lambda j: j["start"] or float('inf'))
        
        return by_station


if __name__ == "__main__":
    controller = LineController()
    
    # Manufacture the complete Telefon
    product_id = "https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max/001"
    
    print("\n" + "="*70)
    print("MANUFACTURING ORCHESTRATION")
    print("="*70)
    
    result = controller.manufacture_product(product_id)
    
    print(f"\nProduct: {result['product']}")
    print(f"Components required: {len(result['components'])}")
    print(f"Total jobs: {result['total_jobs']}")
    print(f"Total makespan: {result['makespan']:.1f} seconds")
    
    print(f"\n{'='*70}")
    print("MANUFACTURING SCHEDULE")
    print(f"{'='*70}\n")
    
    for job in result["schedule"]:
        print(f"{job['job_id']}: {job['product']} → {job['operation']}")
        print(f"   Station: {job['station']}")
        print(f"   Time: {job['start']:.1f}s - {job['end']:.1f}s ({job['duration']:.1f}s)")
    
    print(f"\n{'='*70}")
    print("BY STATION")
    print(f"{'='*70}\n")
    
    for station, jobs in sorted(result["by_station"].items()):
        station_name = controller.aas_data["stations"].get(station, {}).get("idShort", station)
        print(f"\n{station_name}:")
        for job in jobs:
            print(f"  {job['job_id']}: {job['product']} → {job['operation']} ({job['start']:.1f}s-{job['end']:.1f}s)")


if __name__ == "__main__":
    print("Manufacturing Orchestration System Loaded")
    print("Use LineController, ManufacturingSequencePlanner, ConstraintAwareScheduler for orchestration")
    print("\nExample usage:")
    print("  aas_client = AAS_Server_Client('http://localhost:8081')")
    print("  aas_data = aas_client.read_aas()")
    print("  controller = LineController(aas_data)")
    print("  plan = controller.manufacture_product('Telefon')")