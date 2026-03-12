from aas_reader import read_aas

def extract_station_skills(stations):
    """
    Finder alle Skills:
    Skills -> Agents -> agent_name -> skill_name -> Estimated_Duration, Supported_Components
    """
    station_skills = {}

    for station_id, submodels in stations.items():
        skills_list = []

        for sm_name, sm in submodels.items():
            if "Skills" not in sm_name:
                continue
            skills_sm = sm.get("Skills", {})
            agents = skills_sm.get("Agents", {})

            for agent_name, agent_skills in agents.items():
                print(f"[DEBUG] Station {station_id} - Agent: {agent_name}")

                for skill_name, skill_data in agent_skills.items():
                    # skill_data er dict med 'Estimated_Duration' og 'Supported_Components'
                    duration = None
                    comp_type = None

                    # Hent value hvis det er Property
                    est = skill_data.get("Estimated_Duration")
                    if isinstance(est, dict) and "value" in est:
                        duration = float(est["value"])
                    elif isinstance(est, str) or isinstance(est, (int,float)):
                        duration = est

                    comp = skill_data.get("Supported_Components", {}).get("Component_Type")
                    if isinstance(comp, dict) and "value" in comp:
                        comp_type = comp["value"]
                    elif isinstance(comp, str):
                        comp_type = comp

                    print(f"  Skill: {skill_name} | Duration: {duration} | Component: {comp_type}")

                    skills_list.append({
                        "agent": agent_name,
                        "operation": skill_name,
                        "component": comp_type,
                        "duration": duration
                    })

        station_skills[station_id] = skills_list
        print(f"[INFO] Extracted {len(skills_list)} skills from station {station_id}")

    return station_skills

def extract_product_processes(products):
    product_processes = {}

    for product_id, submodels in products.items():
        product_processes[product_id] = []

        for sm_name, sm in submodels.items():
            if "Bill_Of_Processes" not in sm_name:
                continue
            processes = sm.get("List_Of_Processes", {})
            print(f"[DEBUG] Product {product_id} - Found {len(processes)} processes")

            for process_name, data in processes.items():
                params = data.get("Parameters", {})
                component = params.get("Component_Type")
                selected_op = params.get("Selected_Operation")

                if component is None:
                    print(f"[Warning] Product {product_id}, process {process_name} mangler Component_Type")
                    continue

                print(f"  Process: {process_name} | Component: {component} | Selected Operation: {selected_op}")

                product_processes[product_id].append({
                    "operation": process_name,
                    "component": component,
                    "selected_operation": selected_op
                })

    return product_processes

def match_routing(product_processes, station_skills):
    routing = {}

    for product_id, processes in product_processes.items():
        routing[product_id] = []

        for process in processes:
            operation = process["operation"]
            component = process["component"]
            possible_stations = []

            for station_id, skills in station_skills.items():
                for skill in skills:
                    if skill["operation"] == operation and skill["component"] == component:
                        possible_stations.append({
                            "station": station_id,
                            "agent": skill["agent"],
                            "duration": skill["duration"]
                        })

            routing[product_id].append({
                "operation": operation,
                "stations": possible_stations
            })

    return routing

def create_process_plan():
    factory = read_aas()
    stations = factory["stations"]
    products = factory["products"]

    print("\n=== EXTRACTING STATION SKILLS ===")
    station_skills = extract_station_skills(stations)

    print("\n=== EXTRACTING PRODUCT PROCESSES ===")
    product_processes = extract_product_processes(products)

    print("\n=== MATCHING ROUTING ===")
    routing = match_routing(product_processes, station_skills)
    return routing

if __name__ == "__main__":
    routing = create_process_plan()
    print("\n=== ROUTING OUTPUT ===")
    for product, ops in routing.items():
        print(f"\nProduct: {product}")
        for op in ops:
            print(f"  Operation: {op['operation']}")
            if not op["stations"]:
                print("     [No matching stations]")
            for s in op["stations"]:
                print(f"     Station: {s['station']} | Agent: {s['agent']} | Duration: {s['duration']}")