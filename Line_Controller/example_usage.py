"""
Example usage of the process planner system for generating process plans,
scheduling, and routing.
"""

from aas_reader import read_aas
from process_planner import ProcessPlanner
from typing import List, Tuple


def demonstrate_process_planning():
    """
    Demonstrates how to use the process planner to:
    1. Get process plans for products
    2. Compare capabilities
    3. Find which stations can do which operations
    """
    
    # Step 1: Read all AAS data from Basyx server
    print("\n" + "="*70)
    print("STEP 1: Read AAS Data")
    print("="*70)
    aas_data = read_aas()
    print(f"✓ Loaded {len(aas_data['stations'])} stations")
    print(f"✓ Loaded {len(aas_data['products'])} products")
    
    # Step 2: Create process planner
    print("\n" + "="*70)
    print("STEP 2: Create Process Planner")
    print("="*70)
    planner = ProcessPlanner(aas_data)
    print(f"✓ Built capability index with {len(planner.capabilities)} operation types")
    
    # Step 3: Query capabilities
    print("\n" + "="*70)
    print("STEP 3: Query What Each Station Can Do")
    print("="*70)
    
    for station_id, station_data in aas_data["stations"].items():
        station_name = station_data.get("idShort")
        skills = station_data.get("skills", {})
        
        if skills:
            print(f"\n{station_name}:")
            for agent, operations in skills.items():
                print(f"  Agent: {agent}")
                for op_name, op_data in operations.items():
                    duration = op_data.get("Estimated_Duration", "N/A")
                    print(f"    ✓ {op_name}: {duration}s")
        else:
            print(f"\n{station_name}: (No skills defined)")
    
    # Step 4: Generate process plan for a specific product
    print("\n" + "="*70)
    print("STEP 4: Generate Process Plan for Bottom_Cover")
    print("="*70)
    
    # Find a product with processes
    target_product = None
    for product_id, product_data in aas_data["products"].items():
        if product_data.get("idShort") == "Bottom_Cover":
            target_product = product_id
            break
    
    if target_product:
        plan = planner.generate_process_plan(target_product)
        
        print(f"\nProduct: {plan.product_name}")
        print(f"Required processes: {len(plan.required_processes)}")
        
        for process in plan.required_processes:
            print(f"  - {process.process_type} (ID: {process.process_id})")
        
        print(f"\nPossible routes: {len(plan.possible_routes)}")
        
        for route_idx, route in enumerate(plan.possible_routes, 1):
            print(f"\n  Route {route_idx}:")
            total_duration = 0
            
            for step_idx, (station_id, operation) in enumerate(route, 1):
                station_name = planner.stations[station_id].get("idShort")
                
                # Find duration
                capabilities = planner.get_capabilities_for_operation(operation)
                for cap in capabilities:
                    if cap.station_id == station_id:
                        total_duration += cap.estimated_duration
                        print(f"    Step {step_idx}: {station_name} → {operation} ({cap.estimated_duration}s)")
                        break
            
            print(f"    Total duration: {total_duration}s")


def demonstrate_scheduling_ready_data():
    """
    Shows how to prepare data for a scheduler.
    The scheduler would use this information to assign jobs to stations.
    """
    print("\n" + "="*70)
    print("DATA READY FOR SCHEDULING")
    print("="*70)
    
    aas_data = read_aas()
    planner = ProcessPlanner(aas_data)
    
    # For each product with processes, generate a scheduling problem
    scheduling_problems = []
    
    for product_id, product_data in aas_data["products"].items():
        if product_data.get("processes"):
            plan = planner.generate_process_plan(product_id)
            
            # Each route is a potential job sequence
            for route_idx, route in enumerate(plan.possible_routes):
                job_id = f"{plan.product_name}_route_{route_idx + 1}"
                job_steps = []
                
                for step_idx, (station_id, operation) in enumerate(route):
                    station_name = planner.stations[station_id].get("idShort")
                    
                    # Get duration and parameters
                    capabilities = planner.get_capabilities_for_operation(operation)
                    cap = next((c for c in capabilities if c.station_id == station_id), None)
                    
                    if cap:
                        job_steps.append({
                            "sequence": step_idx + 1,
                            "station_id": station_id,
                            "station_name": station_name,
                            "operation": operation,
                            "duration": cap.estimated_duration,
                            "parameters": cap.parameters
                        })
                
                scheduling_problems.append({
                    "job_id": job_id,
                    "product": plan.product_name,
                    "steps": job_steps,
                    "total_duration": sum(s["duration"] for s in job_steps)
                })
    
    # Print scheduling data
    print(f"\nGenerated {len(scheduling_problems)} scheduling problems:\n")
    
    for problem in scheduling_problems:
        print(f"Job: {problem['job_id']}")
        print(f"  Product: {problem['product']}")
        print(f"  Total duration: {problem['total_duration']}s")
        print(f"  Steps:")
        for step in problem["steps"]:
            print(f"    {step['sequence']}. {step['station_name']} → {step['operation']} ({step['duration']}s)")
        print()


def demonstrate_routing_decision():
    """
    Shows how to make routing decisions based on:
    1. Available routes
    2. Station capabilities
    3. Performance constraints
    """
    print("\n" + "="*70)
    print("ROUTING DECISION LOGIC")
    print("="*70)
    
    aas_data = read_aas()
    planner = ProcessPlanner(aas_data)
    
    # Find Bottom_Cover
    bottom_cover = None
    for product_id, product_data in aas_data["products"].items():
        if product_data.get("idShort") == "Bottom_Cover":
            bottom_cover = product_id
            break
    
    if bottom_cover:
        plan = planner.generate_process_plan(bottom_cover)
        
        print(f"\nProduct: {plan.product_name}")
        print(f"Number of possible routes: {len(plan.possible_routes)}")
        
        if plan.possible_routes:
            print("\nRouting decision criteria:")
            print("1. Performance (shortest duration)")
            print("2. Station availability")
            print("3. Resource constraints")
            
            # Example: Find fastest route
            best_route = None
            best_duration = float('inf')
            
            for route_idx, route in enumerate(plan.possible_routes):
                route_duration = 0
                
                for station_id, operation in route:
                    capabilities = planner.get_capabilities_for_operation(operation)
                    cap = next((c for c in capabilities if c.station_id == station_id), None)
                    if cap:
                        route_duration += cap.estimated_duration
                
                if route_duration < best_duration:
                    best_duration = route_duration
                    best_route = (route_idx, route)
            
            if best_route:
                route_idx, route = best_route
                print(f"\n✓ Fastest route (Route {route_idx + 1}): {best_duration}s total")
                for step_idx, (station_id, operation) in enumerate(route, 1):
                    station_name = planner.stations[station_id].get("idShort")
                    print(f"  {step_idx}. {station_name} → {operation}")


if __name__ == "__main__":
    demonstrate_process_planning()
    demonstrate_scheduling_ready_data()
    demonstrate_routing_decision()
    
    print("\n" + "="*70)
    print("Now you can use this data for:")
    print("  1. scheduler.py - Assign jobs to stations with time constraints")
    print("  2. router.py - Route products between stations")
    print("  3. order_manager.py - Manage product orders and track progress")
    print("="*70 + "\n")
