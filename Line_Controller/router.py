"""
Router for manufacturing system
Generates routing paths for products through manufacturing stations
"""

from typing import Dict, List, Any
from dataclasses import dataclass


@dataclass
class RoutingStep:
    """A single step in a product's routing path"""
    step_number: int
    product_name: str
    operation_type: str
    source_station: str
    destination_station: str
    estimated_arrival: float
    estimated_start: float
    estimated_completion: float
    transport_time: float = 0.0


@dataclass
class ProductRoute:
    """Complete routing path for a product"""
    product_name: str
    total_steps: int
    steps: List[RoutingStep]
    total_route_time: float
    

class Router:
    """Routes products through manufacturing stations"""
    
    def __init__(self, aas_data: Dict[str, Any], schedule: List[Dict[str, Any]]):
        """
        Args:
            aas_data: AAS data with stations and products
            schedule: List of job dicts from manufacturing result (format: product_name, operation, station, start, end)
        """
        self.aas_data = aas_data
        self.schedule = schedule
        self.stations = aas_data.get('stations', {})
        self.products = aas_data.get('products', {})
    
    def generate_route(self, product_name: str) -> ProductRoute:
        """
        Generate routing path for a product through manufacturing.
        
        Args:
            product_name: The product name to route (e.g., 'Telefon', 'Bottom_Cover')
            
        Returns:
            ProductRoute with all steps
        """
        # Get all jobs for this product from schedule
        product_jobs = [j for j in self.schedule if j.get('product') == product_name]
        product_jobs = sorted(product_jobs, key=lambda j: j.get('start', 0))
        
        if not product_jobs:
            return ProductRoute(
                product_name=product_name,
                total_steps=0,
                steps=[],
                total_route_time=0.0
            )
        
        steps = []
        current_location = None  # Start location unknown
        
        for i, job in enumerate(product_jobs):
            station_id = job.get('station')
            station_name = self.stations.get(station_id, {}).get('idShort', station_id)
            operation = job.get('operation', 'Unknown')
            start_time = job.get('start', 0)
            end_time = job.get('end', 0)
            
            # Calculate transport time from previous station
            transport_time = 0.0
            source_station = current_location if current_location else "Start"
            
            # Create routing step
            step = RoutingStep(
                step_number=i + 1,
                product_name=product_name,
                operation_type=operation,
                source_station=source_station,
                destination_station=station_name,
                estimated_arrival=start_time - transport_time,
                estimated_start=start_time,
                estimated_completion=end_time,
                transport_time=transport_time
            )
            steps.append(step)
            current_location = station_id
        
        # Calculate total route time
        if steps:
            total_time = steps[-1].estimated_completion - (steps[0].estimated_arrival if steps[0].source_station != "Start" else steps[0].estimated_start)
        else:
            total_time = 0.0
        
        return ProductRoute(
            product_name=product_name,
            total_steps=len(steps),
            steps=steps,
            total_route_time=total_time
        )
    
    def generate_all_routes(self, manufacturing_result: Dict[str, Any]) -> List[ProductRoute]:
        """
        Generate routes for all unique products in the manufacturing result.
        
        Args:
            manufacturing_result: The result dict from LineController.manufacture_product()
            
        Returns:
            List of ProductRoute objects for all products with jobs
        """
        routes = []
        unique_products = set()
        
        # Get all unique products with jobs from schedule
        schedule = manufacturing_result.get('schedule', [])
        for job in schedule:
            unique_products.add(job.get('product'))
        
        # Generate route for each product
        for product_name in sorted(unique_products):
            route = self.generate_route(product_name)
            if route.total_steps > 0:  # Only include if there are operations
                routes.append(route)
        
        return routes
    
    def print_routes(self, routes: List[ProductRoute]):
        """Print routing paths in human-readable format"""
        print("\n" + "=" * 80)
        print("PRODUCT ROUTING PATHS")
        print("=" * 80)
        
        for route in routes:
            print(f"\n{route.product_name}")
            print(f"  Total Steps: {route.total_steps}")
            print(f"  Total Route Time: {route.total_route_time:.1f}s")
            print(f"  Routing Path:")
            
            for step in route.steps:
                station_abbrev = step.destination_station.split('/')[-1] if '/' in step.destination_station else step.destination_station
                
                if step.source_station == "Start":
                    print(f"    Step {step.step_number}: {step.source_station} → {step.destination_station}")
                    print(f"                  Operation: {step.operation_type} ({step.estimated_completion - step.estimated_start:.1f}s)")
                    print(f"                  Schedule: {step.estimated_start:.1f}s - {step.estimated_completion:.1f}s")
                else:
                    source_abbrev = step.source_station.split('/')[-1] if '/' in step.source_station else step.source_station
                    print(f"    Step {step.step_number}: {source_abbrev} → {station_abbrev}")
                    print(f"                  Operation: {step.operation_type} ({step.estimated_completion - step.estimated_start:.1f}s)")
                    print(f"                  Schedule: {step.estimated_start:.1f}s - {step.estimated_completion:.1f}s")
                    if step.transport_time > 0:
                        print(f"                  Transport: {step.transport_time:.1f}s")


if __name__ == "__main__":
    from aas_reader import read_aas
    from line_controller import LineController
    
    # Test router
    controller = LineController()
    aas_data = controller.aas_data
    
    telefon_id = None
    for pid, pdata in aas_data['products'].items():
        if pdata['idShort'] == 'Telefon':
            telefon_id = pid
            break
    
    if telefon_id:
        result = controller.manufacture_product(telefon_id)
        schedule = result.get('schedule', [])
        
        if schedule:
            router = Router(aas_data, schedule)
            routes = router.generate_all_routes(result)
            router.print_routes(routes)
