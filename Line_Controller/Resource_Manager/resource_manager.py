import sys
from pathlib import Path
from collections import deque


sys.path.append(str(Path(__file__).resolve().parent.parent))
from AAS_Reader.aas_reader import AASShellReader

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




    def est_resource_connection_points(self, start_resource: str, destination_resource: str, component: str):

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

                if own_cp == "ACOPOS6D_Connection_Point_7":
                    print("TRYING TO RUN A MATCH FOR TRANSPORT WHEN IT FINDS ACOPOS6D_Connection_Point_7")
                    print(f"VALID AGENTS FOR ACOPOS6D_Connection_Point_7 : {self._get_matching_skill(resource_obj,'Transport',component,own_cp)}")


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

                print(f"New path: {new_path}")

                queue.append((next_res, new_path))

        return []

    #def est_resource_connection_points(self, start_resource, destination_resource, component):
        # Return the connection points between two resources as a dictionary?, to be used for routing components through the production line.

        #We have Bottom_Cover at Bottom_Cover_Storage
        # Need component Bottom_Cover at Drill_Station
        # How do we get from where Bottom_Cover is located to Drill_Station?

        #If every station has a Retrieve function, then we can enforce that when trying to move a product from one station to another, through connection points, then it has to start with a Retrieve, and then only follow that with Transport skills

        # 1 Look for connection between resources:

        # 2 Check resources for correct skills:
            # - First resource in the chain must have a retrive skill with the component supported as output (important that it has no input required)
            # - All other resources must have the transport skill, supporting the component as input & output.
        
        # 3 Generate route from stored component to the desired resource, with a list of available agents to perform transportation from A -> B at each step

        #print("Hello")




                              
                                    
    


#This should contain a class that we can construct with all the resources we have.
#This it should have a function that:
# allows us to insert a requried skill and component and recieve a list of resoruces that have that skill and is compatible with that component
# allows us to insert a component and returns a list of resources that have the specific component in their internal storage
# allows us to check for at specific input and output match
# Maybe we should also have a function that just returns ALL storage for every resource which the line-controller can keep track of itself, maybe checking-in with the stations every 10 minutes to see if they agree
# Insert component into function that returns a resource and an amount
# allows us to insert two different resources and return a list, showing if and how they are connected through connection points
# Lastly, it should be able to generate a command that can later be sent over MQTT
