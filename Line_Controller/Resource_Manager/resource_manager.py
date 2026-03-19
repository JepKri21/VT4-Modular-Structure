from collections import deque

class ResourceManager:
    def __init__(self, Resources):
        self.resource_nodes = Resources
        
    def check_skill_and_component(self, skill: str, component: str):

        matches = {}

        for resource_name, resource in self.resource_nodes.items():

            skills = resource.Skills
            if not skills:
                continue

            agents = skills.Agents
            if not agents:
                continue

            for agent_name, agent in agents.children.items():

                capabilities = agent.children.get("Capabilities")
                if not capabilities:
                    continue

                for cap_name, capability in capabilities.children.items():

                    if cap_name != skill:
                        continue

                    io_maps = capability.children.get("Input_Output_Mappings")
                    if not io_maps:
                        continue

                    for map_name, io_map in io_maps.children.items():

                        inputs = io_map.children.get("Inputs")
                        if not inputs:
                            continue

                        for input_name, input_node in inputs.children.items():

                            if component in (input_node.id_short, input_node.value):
                                matches[resource_name] = resource

        return matches
    
    def return_component_inventory(self):

        inventory = {}

        for resource_name, resource in self.resource_nodes.items():

            resource_inventory = {}

            try:
                item_capacity = resource["Item_Capacity"]
            except KeyError:
                continue

            storages = item_capacity.children.get("Internal_Part_Storages")
            if not storages:
                continue

            for storage_name, storage_node in storages.children.items():

                storage_data = {}

                # --- Agents ---
                agents = []
                agent_access = storage_node.children.get("Agent_Accessibility")

                if agent_access:
                    for _, agent_node in agent_access.children.items():
                        agents.append(agent_node.value)

                # --- Part Types ---
                part_types = storage_node.children.get("Part_Types")
                if not part_types:
                    continue

                for _, part_node in part_types.children.items():

                    part_type = None
                    quantity = 0
                    model_number = None

                    for element_name, element_node in part_node.children.items():

                        if element_name == "Part_Type_Id":
                            part_type = element_node.value

                        elif element_name == "Quantity":
                            quantity = int(element_node.value)

                        elif element_name == "Model_Number":
                            model_number = element_node.value

                    # ✅ Use model number as key
                    storage_data[model_number] = {
                        "Component_Type": part_type,
                        "Model_Number": model_number,
                        "Quantity": quantity,
                        "Agents": agents
                    }

                resource_inventory[storage_name] = storage_data

            inventory[resource_name] = resource_inventory

        return inventory
    

    def _get_resource_connections(self, resource):

        connections = []

        location = resource["Location"]
        rc = location.children.get("Resource_Connections")

        if not rc:
            return connections

        for conn_name, conn_node in rc.children.items():

            conn_data = {}

            for elem_name, elem_node in conn_node.children.items():

                if elem_name == "Own_Connection_Point_Id":
                    conn_data["own_cp"] = elem_node.value

                elif elem_name == "Connection_Resource_Id":
                    conn_data["target"] = elem_node.value

                elif elem_name == "Other_Resource_Connection_Point_Id":
                    conn_data["target_cp"] = elem_node.value

            conn_data["connection_name"] = conn_name

            connections.append(conn_data)

        return connections
    

    def _get_matching_skill(self, resource, skill_type, component, connection_point):

        skills = resource["Skills"]
        agents_node = skills.children.get("Agents")

        if not agents_node:
            return None

        valid_agents = []

        for agent_name, agent in agents_node.children.items():

            capabilities = agent.children.get("Capabilities")
            if not capabilities:
                continue

            for cap_name, capability in capabilities.children.items():

                if cap_name != skill_type:
                    continue

                # Check connection point support
                cp_node = capability.children.get("Supported_Connection_Points")
                if cp_node:
                    supported = [
                        c.children["Connection_Point_Id"].value
                        for c in cp_node.children.values()
                    ]
                    if connection_point not in supported:
                        continue

                # Check IO mappings
                io_maps = capability.children.get("Input_Output_Mappings")
                if not io_maps:
                    continue

                for _, io_map in io_maps.children.items():

                    inputs = io_map.children.get("Inputs")
                    outputs = io_map.children.get("Outputs")

                    input_vals = []
                    output_vals = []

                    if inputs:
                        input_vals = [i.value for i in inputs.children.values()]

                    if outputs:
                        output_vals = [o.value for o in outputs.children.values()]

                    if skill_type == "Retrieve":
                        if not input_vals and component in output_vals:
                            valid_agents.append(agent_name)

                    elif skill_type == "Transport":
                        if component in input_vals and component in output_vals:
                            valid_agents.append(agent_name)

        return valid_agents if valid_agents else None


    def find_resource_connection_points(self, start_resource: str, destination_resource: str, component: str):

        queue = deque()

        queue.append((start_resource, []))

        while queue:

            current, path = queue.popleft()


            resource_obj = self.resource_nodes[current]
            connections = self._get_resource_connections(resource_obj)

            for conn in connections:

                next_res = conn["target"]
                conn_name = conn["connection_name"]
                own_cp = conn["own_cp"]

                print(f"Trying connection {conn_name} -> {next_res} (cp={own_cp})")
                # =========================
                # FIRST STEP → RETRIEVE
                # =========================
                if current == start_resource:

                    agents_current = self._get_matching_skill(
                        resource_obj,
                        "Retrieve",
                        component,
                        own_cp
                    )

                    if not agents_current:
                        continue

                    step = {
                        current: {
                            "Skill": "Retrieve",
                            "Agents": agents_current,
                            "Resource_Connection_Points": [conn_name]
                        }
                    }

                # =========================
                # DESTINATION STEP
                # =========================
                elif next_res == destination_resource:

                    agents_current = self._get_matching_skill(
                        resource_obj,
                        "Transport",
                        component,
                        own_cp
                    )

                    if not agents_current:
                        continue
                    
                    step = {
                        current: {
                            "Skill": "Transport",
                            "Agents": agents_current,
                            "Resource_Connection_Points": [conn_name]
                        }
                    }

                    # build the new path including this last step
                    new_path = path + [step]
                    print(f"✅ Found valid path to destination: {new_path}")
                    return new_path

                # =========================
                # NORMAL TRANSPORT STEP
                # =========================
                else:

                    agents_current = self._get_matching_skill(
                        resource_obj,
                        "Transport",
                        component,
                        own_cp
                    )
                

                    if not agents_current:
                        continue

                    step = {
                        current: {
                            "Skill": "Transport",
                            "Agents": agents_current,
                            "Resource_Connection_Points": [conn_name]
                        }
                    }

                # =========================
                # BUILD PATH
                # =========================
                new_path = path + [step]

                #print(f"New path: {new_path}")

                queue.append((next_res, new_path))

        return []
    
    def build_full_order_execution(self, order_dict, component_inventory):
        # Use the output from order_reader.py to get BoP, but add the Retrieve and Transport commands from find_resource_connection_points (Might have to adjust so that it fits into what we need.)
        
        # build_order_dict: Giver en BoP for hele produktet
        # find_resource_connection_points: Giver steps fra start_resource -> target_resource.
        
        # Vi Skal med build_full_order_execution have en fuld step by step liste som line_controller.py kan holde styr på, så når hvert step er udført kan det enten krydses af på en checkliste, eller poppes fra listen. For hvert step bliver find_resource_connection_points nok kaldt, da den fortæller hvordan du kommer fra dit nuværende resource til din næste resource (måske er der noget med constraints i sub-assembly, hvordan finder den ud af at drilling skal laves inden den kommer til sub-assembly ved PCB_Assembler?).

        # Hvordan sikrer vi os at den rigtige sub-assembly bliver samlet i korrekt rækkefølge? Skulle man komme til at se  på sub-assembly for https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB-Fuse/edff53e0-8150-430a-90b0-1553d888591b
        pass
        
        





# {'ORD-001': [
#         {'https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB/f0ab9bcf-e7e7-4418-9fb0-cdf25d290d22': [
#             {'Assemble_1': [
#                 {'Process_Constraints': ['Drilling_1']}, 
#                 {'Required_Components': ['PCB_1', 'Bottom_Cover_1']}, 
#                 {'Parameters': [{'Selected_Operation': 'Assemble'}]}]}, 
#             {'Drilling_1': [{'Process_Constraints': []}, 
#                 {'Required_Components': ['Bottom_Cover_1']}, 
#                 {'Parameters': [{'Selected_Operation': 'Drilling'}, {'Drill_Size': '3'}, {'Drill_Depth': '20'}]}]}]}, 
#         {'https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB-Fuse/edff53e0-8150-430a-90b0-1553d888591b': [
#             {'Assemble_1': [{'Process_Constraints': []}, 
#                 {'Required_Components': ['Bottom_Cover-PCB_1', 'Fuse_1']}, 
#                 {'Parameters': [{'Selected_Operation': 'Assemble'}]}]}]}, 
#         {'https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max/e739eb46-b993-4bed-a46d-6ac6793db1cb': [
#             {'Assemble_1': [{'Process_Constraints': []}, 
#                 {'Required_Components': ['Bottom_Cover-PCB-Fuse_1', 'Top_Cover_1']}, 
#                 {'Parameters': [{'Selected_Operation': 'Assemble'}]}]}]}]}
                              

#This function (or functions) should be able to read the order and establish a sequence.
# FIRST: It should read the process constraints to see if it needs to process something first
# IF there is a constraint, then it should look at that process
# IF there is NO constraint, then it should look at the required components
# SECOND: It should look at the parameters and find a resource with that skill and parameters available.
# WHEN it finds that resourse it should look at the required components and 
#   FIRST see if that part is being produced as part of the order and if not, then SECOND, check if that resource has any of those parts in storage 
# IF it DOES have those parts in storage, then you can just add this skill to the beginning of the execution list
# IF it DOES NOT have those parts, it should find a resource with those components and then run find_resource_connection_points to establish a route
# that route should then be added to the execution list before the skill is


order_example ={'ORD-001': [
    {'https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB/f0ab9bcf-e7e7-4418-9fb0-cdf25d290d22': [
        {'Assemble_1': [
            {'Process_Constraints': ['Drilling_1']}, 
            {'Required_Components': [{'PCB_1' : "https://aausmartlab.com/Assets/Product/Component/AAU/PCB"}, {'Bottom_Cover_1' : "https://aausmartlab.com/Assets/Product/Component/AAU/Bottom_Cover"}]}, 
            {'Parameters': [{'Selected_Operation': 'Assemble'}, {"inputs" : ["PCB_1", "Bottom_Cover_1"]}, {"outputs" : ["https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB"]}]}]}, 
        {'Drilling_1': [
            {'Process_Constraints': []}, 
            {'Required_Components': [{'Bottom_Cover_1': "https://aausmartlab.com/Assets/Product/Component/AAU/Bottom_Cover"}]}, 
            {'Parameters': [{'Selected_Operation': 'Drilling'}, {"inputs" : ["Bottom_Cover_1"]}, {"outputs" : ["Bottom_Cover_1"]} ,{'Drill_Size': '3'}, {'Drill_Depth': '20'}]}]}]}, 
    {'https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB-Fuse/edff53e0-8150-430a-90b0-1553d888591b': [
        {'Assemble_1': [
            {'Process_Constraints': []}, 
            {'Required_Components': [{'Bottom_Cover-PCB_1' : "https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB"}, {'Fuse_1' : "https://aausmartlab.com/Assets/Product/Component/AAU/Fuse"}]}, 
            {'Parameters': [{'Selected_Operation': 'Assemble'}, {"inputs" : ["Bottom_Cover-PCB_1", "Fuse_1"]}, {"outputs" : ["https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB-Fuse"]} ]}]}]}, 
    {'https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max/e739eb46-b993-4bed-a46d-6ac6793db1cb': [
        {'Assemble_1': [
            {'Process_Constraints': []}, 
            {'Required_Components': [{'Bottom_Cover-PCB-Fuse_1' : "https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB-Fuse"}, {'Top_Cover_1' : "https://aausmartlab.com/Assets/Product/Component/AAU/Top_Cover"}]}, 
            {'Parameters': [{'Selected_Operation': 'Assemble'}, {"inputs" : ["Bottom_Cover-PCB-Fuse_1", "Top_Cover_1"]}, {"outputs" : ["https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max"]}]}]}]}]} 


final_product = "https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max/e739eb46-b993-4bed-a46d-6ac6793db1cb"

execution_list = []

#This should contain a class that we can construct with all the resources we have.
#This it should have a function that:
# allows us to insert a component and returns a list of resources that have the specific component in their internal storage
# allows us to check for at specific input and output match
# Maybe we should also have a function that just returns ALL storage for every resource which the line-controller can keep track of itself, maybe checking-in with the stations every 10 minutes to see if they agree
# Insert component into function that returns a resource and an amount
# allows us to insert two different resources and return a list, showing if and how they are connected through connection points
# Lastly, it should be able to generate a command that can later be sent over MQTT



def _find_process(order, product_url, process_name):

    order_id, items = list(order.items())[0]

    for item in items:
        if product_url in item:

            for proc in item[product_url]:
                if process_name in proc:
                    return proc[process_name]

    return None

def _find_process_producing(order, component_url):

    order_id, items = list(order.items())[0]

    for item in items:
        for product_url, processes in item.items():

            for proc in processes:
                for proc_name, proc_data in proc.items():

                    for section in proc_data:
                        if "Parameters" in section:

                            for p in section["Parameters"]:
                                if "outputs" in p:
                                    if component_url in p["outputs"]:
                                        return product_url, proc_name, proc_data

    return None, None, None

def _get_section(process_data, section_name):

    for section in process_data:
        if section_name in section:
            return section[section_name]

    return []


def resolve_process(order, product_url, process_name, execution_list):

    process_data = _find_process(order, product_url, process_name)

    if not process_data:
        return

    constraints = _get_section(process_data, "Process_Constraints")
    required = _get_section(process_data, "Required_Components")
    parameters = _get_section(process_data, "Parameters")

    # STEP 1: resolve constraints
    for constraint in constraints:
        resolve_process(order, product_url, constraint, execution_list)

    # STEP 2: resolve required components
    for comp_dict in required:
        for comp_alias, comp_url in comp_dict.items():

            prod_url, proc_name, proc_data = _find_process_producing(order, comp_url)

            if proc_name:
                resolve_process(order, prod_url, proc_name, execution_list)
            else:
                execution_list.append({
                    "action": "fetch_from_storage",
                    "component": comp_url
                })

    # STEP 3: add this process
    execution_list.append({
        "action": "execute",
        "product": product_url,
        "process": process_name,
        "parameters": parameters
    })


resolve_process(
    order_example,
    final_product,
    "Assemble_1",
    execution_list
)

print(execution_list)


"""
[
{'action': 'fetch_from_storage', 'component': 'https://aausmartlab.com/Assets/Product/Component/AAU/Bottom_Cover'}, 
{'action': 'execute', 'product': 'https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB/f0ab9bcf-e7e7-4418-9fb0-cdf25d290d22', 'process': 'Drilling_1', 
    'parameters': [{'Selected_Operation': 'Drilling'}, {'inputs': ['Bottom_Cover_1']}, {'outputs': ['Bottom_Cover_1']}, {'Drill_Size': '3'}, {'Drill_Depth': '20'}]}, 
{'action': 'fetch_from_storage', 'component': 'https://aausmartlab.com/Assets/Product/Component/AAU/PCB'}, 
{'action': 'fetch_from_storage', 'component': 'https://aausmartlab.com/Assets/Product/Component/AAU/Bottom_Cover'}, 
{'action': 'execute', 'product': 'https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB/f0ab9bcf-e7e7-4418-9fb0-cdf25d290d22', 'process': 'Assemble_1', 
    'parameters': [{'Selected_Operation': 'Assemble'}, {'inputs': ['PCB_1', 'Bottom_Cover_1']}, {'outputs': ['https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB']}]}, 
{'action': 'fetch_from_storage', 'component': 'https://aausmartlab.com/Assets/Product/Component/AAU/Fuse'}, 
{'action': 'execute', 'product': 'https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB-Fuse/edff53e0-8150-430a-90b0-1553d888591b', 'process': 'Assemble_1', 
    'parameters': [{'Selected_Operation': 'Assemble'}, {'inputs': ['Bottom_Cover-PCB_1', 'Fuse_1']}, {'outputs': ['https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB-Fuse']}]}, 
    {'action': 'fetch_from_storage', 'component': 'https://aausmartlab.com/Assets/Product/Component/AAU/Top_Cover'}, 
    {'action': 'execute', 'product': 'https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max/e739eb46-b993-4bed-a46d-6ac6793db1cb', 'process': 'Assemble_1', 
        'parameters': [{'Selected_Operation': 'Assemble'}, {'inputs': ['Bottom_Cover-PCB-Fuse_1', 'Top_Cover_1']}, {'outputs': ['https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max']}]}]
"""