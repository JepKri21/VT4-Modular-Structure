#!/usr/bin/env python3
"""
Quick Reference: Line Controller Process Planning

Usage Examples:
"""

from aas_reader import read_aas
from process_planner import ProcessPlanner


# ============================================================================
# EXAMPLE 1: Read all data from AAS server
# ============================================================================

def example_1_read_aas():
    """Read all shells and submodels from Basyx server"""
    aas_data = read_aas()
    
    # Access stations
    for station_id, station_data in aas_data["stations"].items():
        print(f"Station: {station_data['idShort']}")
        if "skills" in station_data:
            for agent, operations in station_data["skills"].items():
                for op_name, op_data in operations.items():
                    duration = op_data.get("Estimated_Duration", "?")
                    print(f"  {agent} → {op_name} ({duration}s)")
    
    # Access products
    for product_id, product_data in aas_data["products"].items():
        print(f"\nProduct: {product_data['idShort']}")
        if "processes" in product_data:
            for process in product_data["processes"]:
                print(f"  Requires: {process['Process_Type']}")


# ============================================================================
# EXAMPLE 2: Check what operations are available
# ============================================================================

def example_2_check_capabilities():
    """Check what each station can do"""
    aas_data = read_aas()
    planner = ProcessPlanner(aas_data)
    
    # Get all capabilities by operation type
    print("\nAvailable Operations:")
    for op_type in sorted(planner.capabilities.keys()):
        stations = planner.get_capabilities_for_operation(op_type)
        print(f"\n{op_type}:")
        for cap in stations:
            print(f"  - {cap.station_name}: {cap.estimated_duration}s")


# ============================================================================
# EXAMPLE 3: Generate process plan for a product
# ============================================================================

def example_3_generate_process_plan():
    """Generate process plan for a specific product"""
    aas_data = read_aas()
    planner = ProcessPlanner(aas_data)
    
    # Find a product
    product_id = None
    for pid, pdata in aas_data["products"].items():
        if pdata.get("idShort") == "Bottom_Cover":
            product_id = pid
            break
    
    if product_id:
        # Generate plan
        plan = planner.generate_process_plan(product_id)
        
        print(f"\n{plan.product_name}:")
        print(f"  Required processes: {len(plan.required_processes)}")
        for process in plan.required_processes:
            print(f"    - {process.process_type}")
        
        print(f"\n  Possible routes: {len(plan.possible_routes)}")
        for route_idx, route in enumerate(plan.possible_routes, 1):
            print(f"  Route {route_idx}:")
            for station_id, operation in route:
                station_name = planner.stations[station_id]["idShort"]
                print(f"    → {station_name}: {operation}")


# ============================================================================
# EXAMPLE 4: Find fastest route
# ============================================================================

def example_4_find_fastest_route():
    """Find the fastest manufacturing route for a product"""
    aas_data = read_aas()
    planner = ProcessPlanner(aas_data)
    
    # Get Bottom_Cover
    product_id = None
    for pid, pdata in aas_data["products"].items():
        if pdata.get("idShort") == "Bottom_Cover":
            product_id = pid
            break
    
    if product_id:
        plan = planner.generate_process_plan(product_id)
        
        # Find fastest route
        best_route = None
        best_duration = float('inf')
        
        for route in plan.possible_routes:
            route_duration = 0
            for station_id, operation in route:
                caps = planner.get_capabilities_for_operation(operation)
                cap = next((c for c in caps if c.station_id == station_id), None)
                if cap:
                    route_duration += cap.estimated_duration
            
            if route_duration < best_duration:
                best_duration = route_duration
                best_route = route
        
        if best_route:
            print(f"\nFastest route for {plan.product_name}: {best_duration}s")
            for station_id, operation in best_route:
                station_name = planner.stations[station_id]["idShort"]
                caps = planner.get_capabilities_for_operation(operation)
                cap = next((c for c in caps if c.station_id == station_id), None)
                print(f"  → {station_name}: {operation} ({cap.estimated_duration}s)")


# ============================================================================
# EXAMPLE 5: Prepare data for scheduler
# ============================================================================

def example_5_prepare_for_scheduler():
    """Prepare job data ready for a scheduler"""
    aas_data = read_aas()
    planner = ProcessPlanner(aas_data)
    
    # For each product, create job entries
    jobs = []
    
    for product_id, product_data in aas_data["products"].items():
        if not product_data.get("processes"):
            continue
        
        plan = planner.generate_process_plan(product_id)
        
        # Take first route (you could also store all routes)
        if plan.possible_routes:
            route = plan.possible_routes[0]
            
            job = {
                "product": plan.product_name,
                "product_id": product_id,
                "steps": []
            }
            
            for step_idx, (station_id, operation) in enumerate(route, 1):
                station_name = planner.stations[station_id]["idShort"]
                caps = planner.get_capabilities_for_operation(operation)
                cap = next((c for c in caps if c.station_id == station_id), None)
                
                job["steps"].append({
                    "sequence": step_idx,
                    "station_id": station_id,
                    "station_name": station_name,
                    "operation": operation,
                    "duration": cap.estimated_duration if cap else 0
                })
            
            jobs.append(job)
    
    # Print as scheduler-ready data
    print("\nScheduler-ready jobs:")
    import json
    print(json.dumps(jobs, indent=2))


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("QUICK REFERENCE EXAMPLES")
    print("="*70)
    
    print("\n" + "-"*70)
    print("EXAMPLE 1: Read AAS Data")
    print("-"*70)
    example_1_read_aas()
    
    print("\n" + "-"*70)
    print("EXAMPLE 2: Check Capabilities")
    print("-"*70)
    example_2_check_capabilities()
    
    print("\n" + "-"*70)
    print("EXAMPLE 3: Generate Process Plan")
    print("-"*70)
    example_3_generate_process_plan()
    
    print("\n" + "-"*70)
    print("EXAMPLE 4: Find Fastest Route")
    print("-"*70)
    example_4_find_fastest_route()
    
    print("\n" + "-"*70)
    print("EXAMPLE 5: Prepare for Scheduler")
    print("-"*70)
    example_5_prepare_for_scheduler()
    
    print("\n" + "="*70)
