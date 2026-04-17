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
    
    def build_ordered_task_list(self, starting_processes, order_dict):
        """
        Build an ordered list of all tasks from the starting processes, 
        considering process constraints and dependencies.
        
        Args:
            starting_processes: List of starting processes from find_lowest_starting_processes()
            order_dict: The complete order dictionary
            
        Returns:
            List of ordered tasks with product, process name, and process data
        """
        ordered_tasks = []
        processed = set()
        
        # Start with the lowest starting processes
        queue = deque(starting_processes)
        
        while queue:
            current_task = queue.popleft()
            product_url = current_task["product"]
            process_name = current_task["process"]
            task_key = (product_url, process_name)
            
            if task_key in processed:
                continue
            
            # Find the process data
            process_data = self._get_process_data(order_dict, product_url, process_name)
            if not process_data:
                continue
            
            # Add this task to the ordered list
            ordered_tasks.append({
                "product": product_url,
                "process": process_name,
                "process_data": process_data,
                "required_external_components": current_task.get("required_external_components", [])
            })
            processed.add(task_key)
            
            # Find dependent tasks (tasks that depend on the output of this task)
            dependents = self._find_dependent_tasks(order_dict, product_url, process_name, processed)
            queue.extend(dependents)
        
        return ordered_tasks
    
    def _get_process_data(self, order_dict, product_url, process_name):
        """Extract process data from order dictionary."""
        for _, subassemblies in order_dict.items():
            for sub in subassemblies:
                if product_url in sub:
                    for process in sub[product_url]:
                        if process_name in process:
                            return process[process_name]
        return None
    
    def _find_dependent_tasks(self, order_dict, product_url, process_name, processed):
        """Find tasks that depend on the output of the given process."""
        dependents = []
        
        # Get the outputs from the current process
        current_process_data = self._get_process_data(order_dict, product_url, process_name)
        if not current_process_data:
            return dependents
        
        outputs = []
        parameters = self._get_section(current_process_data, "Parameters")
        for param in parameters:
            if "outputs" in param:
                outputs = param["outputs"]
                break
        
        # Also consider the product URL itself as a produced component
        produced_outputs = set(outputs)
        produced_outputs.add(self._extract_type(product_url))
        
        for prod_url, process_name_candidate, process_data in self._iter_order_processes(order_dict):
            task_key = (prod_url, process_name_candidate)
            if task_key in processed:
                continue
            
            constraints = self._get_section(process_data, "Process_Constraints")
            required_components = self._get_section(process_data, "Required_Components")
            
            # Check if this process depends on the current one
            depends_on_current = False
            
            # Check process constraints (explicit dependency)
            if process_name in constraints:
                depends_on_current = True
            
            # Check if required components match produced outputs
            if not depends_on_current and required_components:
                for comp_dict in required_components:
                    for comp_ref, comp_type in comp_dict.items():
                        # Check if the component reference matches any output
                        if comp_ref in produced_outputs:
                            depends_on_current = True
                            break
                        # Check if the component type (full URL) matches
                        if comp_type in produced_outputs:
                            depends_on_current = True
                            break
                        # Also check if the component base name matches
                        comp_base_name = comp_type.split("/")[-1] if "/" in comp_type else comp_type
                        if comp_base_name in produced_outputs:
                            depends_on_current = True
                            break
                        # Check the base type (without UUID)
                        comp_base_type = self._extract_type(comp_type)
                        if comp_base_type in produced_outputs:
                            depends_on_current = True
                            break
                    if depends_on_current:
                        break
            
            if depends_on_current:
                dependents.append({
                    "product": prod_url,
                    "process": process_name_candidate,
                    "required_external_components": []
                })
        
        return dependents


    def _extract_type(self, url):
        return "/".join(url.split("/")[:-1])

    def _collect_produced_types(self, order):
        produced = set()
        for _, subassemblies in order.items():
            for sub in subassemblies:
                for full_url in sub.keys():
                    produced.add(self._extract_type(full_url))
        return produced

    def _get_section(self, process_data, section_name):
        for section in process_data:
            if section_name in section:
                return section[section_name]
        return []

    def _iter_order_processes(self, order):
        for _, subassemblies in order.items():
            for sub in subassemblies:
                for product_url, process_list in sub.items():
                    for process in process_list:
                        for process_name, process_data in process.items():
                            yield product_url, process_name, process_data

    def find_lowest_starting_processes(self, order):
        produced_types = self._collect_produced_types(order)
        starting_processes = []

        for product_url, process_name, process_data in self._iter_order_processes(order):
            constraints = self._get_section(process_data, "Process_Constraints")
            required_components = self._get_section(process_data, "Required_Components")

            # Lowest executable points have no process constraints.
            if constraints:
                continue

            required_types = []
            for comp in required_components:
                for _, comp_type in comp.items():
                    required_types.append(comp_type)

            # Keep only processes that do not require internally produced parts.
            has_internal_dependency = any(
                comp_type in produced_types for comp_type in required_types
            )
            if has_internal_dependency:
                continue

            starting_processes.append(
                {
                    "product": product_url,
                    "process": process_name,
                    "required_external_components": required_types,
                }
            )

        return starting_processes
    
    def find_resource_for_task(self, task, ordered_tasks):
        """
        Find a resource that can perform the given task with matching parameters.
        
        Args:
            task: Task dictionary from build_ordered_task_list()
            ordered_tasks: Full list of ordered tasks (to track produced components)
            
        Returns:
            Resource name if found, None otherwise
        """
        process_data = task["process_data"]
        parameters = self._get_section(process_data, "Parameters")
        required_components = self._get_section(process_data, "Required_Components")
        
        # Extract skill type
        skill_type = None
        for param in parameters:
            if "Selected_Operation" in param:
                skill_type = param["Selected_Operation"]
                break
        
        if not skill_type:
            return None
        
        # Find resources with matching skill
        matching_resources = self._find_resources_with_skill(skill_type)
        
        if not matching_resources:
            return None
        
        for resource_name, resource in matching_resources.items():
            # Check if resource parameters match task parameters
            if self._resource_matches_parameters(resource, skill_type, parameters, required_components):
                return resource_name
        
        return None
    
    def _find_resources_with_skill(self, skill_type):
        """Find all resources that have a specific skill capability."""
        matching_resources = {}
        
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
                    if cap_name == skill_type:
                        matching_resources[resource_name] = resource
                        break
        
        return matching_resources
    
    def _resource_matches_parameters(self, resource, skill_type, task_parameters, required_components=None):
        """
        Check if a resource's capabilities match the task parameters, including inputs/outputs.
        
        Args:
            resource: The resource object to check
            skill_type: The skill type (e.g., 'Assemble', 'Drilling')
            task_parameters: List of parameters from the task
            required_components: List of required component dictionaries with component types
            
        Returns:
            True if resource can handle all operational parameters AND has matching I/O capability
        """
        try:
            skills = resource["Skills"]
        except (KeyError, AttributeError, TypeError):
            return False
        
        if not skills:
            return False
        
        agents = skills.Agents
        if not agents:
            return False
        
        # Extract operational parameters from task (exclude inputs/outputs)
        task_op_params = {}
        task_inputs = []
        task_outputs = []
        task_input_types = []
        task_output_types = []
        
        # Extract input and output names from task
        for param in task_parameters:
            for key, value in param.items():
                if key == "inputs":
                    task_inputs = value if isinstance(value, list) else [value]
                elif key == "outputs":
                    task_outputs = value if isinstance(value, list) else [value]
                elif key != "Selected_Operation":
                    task_op_params[key] = value
        
        # Try to resolve input/output component types from Required_Components in parent context
        # For now, we'll store this info, but match based on count and presence
        
        # Check agent capabilities
        for agent_name, agent in agents.children.items():
            capabilities = agent.children.get("Capabilities")
            if not capabilities:
                continue
            
            for cap_name, capability in capabilities.children.items():
                if cap_name != skill_type:
                    continue
                
                # ===== CHECK OPERATIONAL PARAMETERS =====
                parameters_node = capability.children.get("Parameters")
                op_params_match = True
                
                if parameters_node:
                    resource_params = {}
                    for param_name, param_node in parameters_node.children.items():
                        resource_params[param_name] = param_node.value
                    
                    # Check if resource can handle all required operational parameters
                    for key, value in task_op_params.items():
                        if key not in resource_params:
                            op_params_match = False
                            break
                else:
                    # No parameters defined in capability - only accept if task has no parameters either
                    if task_op_params:
                        op_params_match = False
                
                if not op_params_match:
                    continue
                
                # ===== CHECK INPUT/OUTPUT MAPPINGS =====
                # Verify that the resource's IO mappings can handle the task's inputs and outputs
                io_maps = capability.children.get("Input_Output_Mappings")
                
                if io_maps:
                    # Check if ANY IO mapping can handle this specific task
                    for map_name, io_map in io_maps.children.items():
                        map_inputs_node = io_map.children.get("Inputs")
                        map_outputs_node = io_map.children.get("Outputs")
                        
                        # Extract input and output values from this mapping
                        map_inputs = []
                        map_outputs = []
                        
                        if map_inputs_node:
                            for input_name, input_node in map_inputs_node.children.items():
                                map_inputs.append(input_node.value)
                        
                        if map_outputs_node:
                            for output_name, output_node in map_outputs_node.children.items():
                                map_outputs.append(output_node.value)
                        
                        # For now: if task requires inputs, resource must have inputs (and vice versa)
                        # If task produces outputs, resource must produce outputs (and vice versa)
                        task_requires_inputs = len(task_inputs) > 0
                        task_produces_outputs = len(task_outputs) > 0
                        resource_has_inputs = len(map_inputs) > 0
                        resource_has_outputs = len(map_outputs) > 0
                        
                        # First check: task and resource must both have inputs or both not have inputs
                        if task_requires_inputs != resource_has_inputs or task_produces_outputs != resource_has_outputs:
                            continue
                        
                        # Second check: if required_components provided, verify input component types match
                        if required_components and resource_has_inputs:
                            # Extract component types from required_components
                            req_input_types = set()
                            for comp_dict in required_components:
                                for comp_name, comp_type in comp_dict.items():
                                    # comp_type might be a URL or a base type
                                    req_input_types.add(comp_type)
                            
                            # Check if resource inputs contain the required component types
                            resource_inputs_set = set(map_inputs)
                            # For now, verify that there's significant overlap
                            # (at least one required input type matches a resource input type)
                            has_overlap = bool(req_input_types & resource_inputs_set)
                            if not has_overlap:
                                # No overlap - this resource can't handle these components
                                continue
                        
                        # If we made it here, this mapping works for the task
                        return True
                else:
                    # No IO mappings defined - only accept if task has no inputs/outputs (e.g., Retrieve-only operations)
                    if not task_inputs and not task_outputs:
                        return True
        
        return False
    
    def check_component_availability(self, resource_name, required_components, component_inventory, produced_so_far=None):
        """
        Check if a resource has all required components in inventory.
        If not, find source resources for missing components.
        
        Args:
            resource_name: The target resource that needs components
            required_components: List of required component URLs/types
            component_inventory: From return_component_inventory()
            produced_so_far: Set of components already produced in this order
            
        Returns:
            Dictionary with:
            - has_all_components: bool
            - missing_components: list of {'component': type, 'source_resource': name}
            - transport_routes: list of transport paths for missing components
        """
        if produced_so_far is None:
            produced_so_far = set()
        
        result = {
            "has_all_components": True,
            "missing_components": [],
            "transport_routes": []
        }
        
        for comp_dict in required_components:
            for comp_ref, comp_type in comp_dict.items():
                # Check if component is being produced in this order
                comp_base_type = self._extract_type(comp_type)
                if comp_base_type in produced_so_far:
                    continue
                
                # Check if resource has this component in storage
                if not self._resource_has_component(resource_name, comp_type, component_inventory):
                    result["has_all_components"] = False
                    
                    # Find source resource with this component
                    source_resource = self._find_resource_with_component(comp_type, component_inventory)
                    
                    if source_resource and source_resource != resource_name:
                        result["missing_components"].append({
                            "component": comp_type,
                            "source_resource": source_resource,
                            "component_ref": comp_ref
                        })
                        
                        # Get transport route
                        transport_path = self.find_resource_connection_points(
                            source_resource,
                            resource_name,
                            comp_type
                        )
                        
                        if transport_path:
                            result["transport_routes"].append({
                                "component": comp_type,
                                "source": source_resource,
                                "destination": resource_name,
                                "path": transport_path
                            })
        
        return result
    
    def build_complete_execution_plan(self, ordered_tasks, component_inventory):
        """
        Build a complete execution plan with all necessary retrieve and transport operations.
        
        Args:
            ordered_tasks: From build_ordered_task_list()
            component_inventory: From return_component_inventory()
            
        Returns:
            List of execution steps with resources, skills, and transport operations
        """
        execution_plan = []
        produced_components = set()  # Base types that are produced
        component_locations = {}  # Maps component to its current location (resource name)
        task_to_resource = {}
        
        # First pass: find resources for all tasks
        for task in ordered_tasks:
            resource = self.find_resource_for_task(task, ordered_tasks)
            if not resource:
                print(f"⚠️ No resource found for task: {task['process']}")
                continue
            
            task_key = (task["product"], task["process"])
            task_to_resource[task_key] = resource
            
            # Track produced components and their locations
            parameters = self._get_section(task["process_data"], "Parameters")
            for param in parameters:
                if "outputs" in param:
                    for output in param["outputs"]:
                        produced_components.add(output)
                        produced_components.add(self._extract_type(output))
        
        # Second pass: build complete execution plan with transport steps
        for task in ordered_tasks:
            task_key = (task["product"], task["process"])
            resource_name = task_to_resource.get(task_key)
            
            if not resource_name:
                continue
            
            required_components = self._get_section(task["process_data"], "Required_Components")
            
            # Check component availability considering intermediate production
            availability = self.check_component_availability_with_tracking(
                resource_name,
                required_components,
                component_inventory,
                produced_so_far=produced_components,
                component_locations=component_locations
            )
            
            # Add transport steps for missing components
            print(f"\n  🚛 Transport routes for {resource_name}: {len(availability['transport_routes'])} routes")
            for transport in availability["transport_routes"]:
                if transport["path"]:  # Only add if path is not empty
                    print(f"    Adding transport: {transport['source']} -> {transport['destination']}")
                    # Flatten the transport path - each step should be added individually
                    for step in transport["path"]:
                        execution_plan.append(step)
                else:
                    print(f"    ⚠️ WARNING: No transport route found from {transport['source']} to {transport['destination']} for {transport['component']}")
            
            # Add the main skill execution step
            parameters = self._get_section(task["process_data"], "Parameters")
            execution_plan.append({
                resource_name: {
                    "Skill": self._get_skill_from_parameters(parameters),
                    "Process": task["process"],
                    "Product": task["product"],
                    "Parameters": parameters,
                    "Required_Components": required_components
                }
            })
            
            # Update component locations after this task completes
            # Track both the full URL and base type for each output
            for param in parameters:
                if "outputs" in param:
                    for output in param["outputs"]:
                        # Store where this component now is (at this resource after processing)
                        component_locations[output] = resource_name
                        component_locations[self._extract_type(output)] = resource_name
                        print(f"  📍 Tracked output '{output}' at {resource_name}")
                        print(f"     Also tracked base type '{self._extract_type(output)}' at {resource_name}")
            
            # Also track the input references mapped to their types
            # This helps connect Bottom_Cover_1 (input reference) to its actual location
            for param in parameters:
                if "inputs" in param:
                    for input_ref in param["inputs"]:
                        # Try to find what component type this reference maps to
                        for comp_dict in required_components:
                            for comp_ref_name, comp_type in comp_dict.items():
                                if comp_ref_name == input_ref:
                                    # Map the reference name to the resource location
                                    component_locations[input_ref] = resource_name
                                    print(f"  📍 Tracked input reference '{input_ref}' at {resource_name}")
                                    break
        
        # After first pass builds all tasks and transports,
        # now add cleanup retrieves for resources that produced items
        # But skip if a transport retrieve from that resource is already in the plan
        resources_with_transport_retrieves = set()
        for step in execution_plan:
            if isinstance(step, dict):
                for resource_name, details in step.items():
                    if details.get('Skill') == 'Retrieve' and 'Retrieved_Components' in details:
                        # This is a transport retrieve (has specific components)
                        resources_with_transport_retrieves.add(resource_name)
        
        # Now go back through and add cleanup retrieves only where there are no transport retrieves
        for task in ordered_tasks:
            task_key = (task["product"], task["process"])
            resource_name = task_to_resource.get(task_key)
            
            if not resource_name:
                continue
            
            # Skip if this resource already has a transport retrieve
            if resource_name in resources_with_transport_retrieves:
                continue
            
            parameters = self._get_section(task["process_data"], "Parameters")
            retrieve_step = self._add_retrieve_step_after_process(resource_name, parameters)
            if retrieve_step:
                execution_plan.append(retrieve_step)
                print(f"  📦 Added cleanup retrieve after process at {resource_name}")
        
        return execution_plan
    
    def check_component_availability_with_tracking(self, resource_name, required_components, component_inventory, produced_so_far=None, component_locations=None):
        """
        Check if a resource has all required components, considering intermediate production.
        
        Args:
            resource_name: The target resource that needs components
            required_components: List of required component URLs/types
            component_inventory: From return_component_inventory()
            produced_so_far: Set of components already produced in this order
            component_locations: Dict mapping component to its current resource location
            
        Returns:
            Dictionary with availability info and transport routes
        """
        if produced_so_far is None:
            produced_so_far = set()
        if component_locations is None:
            component_locations = {}
        
        result = {
            "has_all_components": True,
            "missing_components": [],
            "transport_routes": []
        }
        
        for comp_dict in required_components:
            for comp_ref, comp_type in comp_dict.items():
                # Get the base type without UUID
                comp_base_type = self._extract_type(comp_type)
                
                # Check if this component type is produced in this order
                # Check multiple forms: full URL, base type, and if it's in component_locations
                is_produced = (comp_base_type in produced_so_far or 
                              comp_type in produced_so_far or 
                              comp_ref in component_locations or
                              comp_type in component_locations or
                              comp_base_type in component_locations)
                
                print(f"  Checking component '{comp_ref}' (type: {comp_type}, base: {comp_base_type})")
                print(f"    Is produced: {is_produced}")
                print(f"    Component locations: {component_locations}")
                
                if is_produced:
                    # Component IS produced in this order
                    # Find where it currently is
                    source_resource = None
                    
                    # Check various forms of the component identifier
                    if comp_ref in component_locations:
                        source_resource = component_locations[comp_ref]
                        print(f"    Found by comp_ref: {source_resource}")
                    elif comp_type in component_locations:
                        source_resource = component_locations[comp_type]
                        print(f"    Found by comp_type: {source_resource}")
                    elif comp_base_type in component_locations:
                        source_resource = component_locations[comp_base_type]
                        print(f"    Found by comp_base_type: {source_resource}")
                    else:
                        print(f"    NOT FOUND in component_locations")
                    
                    # If we found where it is, check if transport is needed
                    if source_resource:
                        if source_resource != resource_name:
                            print(f"    Need to transport from {source_resource} to {resource_name}")
                            result["has_all_components"] = False
                            result["missing_components"].append({
                                "component": comp_type,
                                "source_resource": source_resource,
                                "component_ref": comp_ref,
                                "from_production": True
                            })
                            
                            # Get transport route
                            transport_path = self.find_resource_connection_points(
                                source_resource,
                                resource_name,
                                comp_type
                            )
                            
                            # Always track transport, even if path is empty (to report failures)
                            result["transport_routes"].append({
                                "component": comp_type,
                                "source": source_resource,
                                "destination": resource_name,
                                "path": transport_path
                            })
                        else:
                            print(f"    Component already at {resource_name}")
                else:
                    # Component is NOT produced in this order, check storage
                    if not self._resource_has_component(resource_name, comp_type, component_inventory):
                        result["has_all_components"] = False
                        
                        # Find source resource with this component
                        source_resource = self._find_resource_with_component(comp_type, component_inventory)
                        
                        if source_resource and source_resource != resource_name:
                            result["missing_components"].append({
                                "component": comp_type,
                                "source_resource": source_resource,
                                "component_ref": comp_ref,
                                "from_production": False
                            })
                            
                            # Get transport route
                            transport_path = self.find_resource_connection_points(
                                source_resource,
                                resource_name,
                                comp_type
                            )
                            
                            # Always track transport, even if path is empty (to report failures)
                            result["transport_routes"].append({
                                "component": comp_type,
                                "source": source_resource,
                                "destination": resource_name,
                                "path": transport_path
                            })
        
        return result
    
    def _get_skill_from_parameters(self, parameters):
        """Extract skill type from parameters."""
        for param in parameters:
            if "Selected_Operation" in param:
                return param["Selected_Operation"]
        return "Unknown"
    
    def _resource_has_component(self, resource_name, component_type, component_inventory):
        """Check if a resource has a specific component in inventory."""
        if resource_name not in component_inventory:
            return False
        
        resource_inv = component_inventory[resource_name]
        
        for storage_name, storage_data in resource_inv.items():
            for model_num, comp_data in storage_data.items():
                if comp_data.get("Component_Type") == component_type and comp_data.get("Quantity", 0) > 0:
                    return True
        
        return False
    
    def _find_resource_with_component(self, component_type, component_inventory):
        """Find a resource that has a specific component."""
        for resource_name, resource_inv in component_inventory.items():
            for storage_name, storage_data in resource_inv.items():
                for model_num, comp_data in storage_data.items():
                    if comp_data.get("Component_Type") == component_type and comp_data.get("Quantity", 0) > 0:
                        return resource_name
        return None
    
    def _add_retrieve_step_after_process(self, resource_name, parameters):
        """
        Create a retrieve step to remove produced components from the resource after process completion.
        This frees up the resource for new processes. Reads Agents and Connection Points from resource skills.
        
        Args:
            resource_name: The resource that just completed the process
            parameters: The process parameters containing outputs
            
        Returns:
            Dictionary with retrieve step, or None if no outputs
        """
        outputs = []
        for param in parameters:
            if "outputs" in param:
                outputs = param["outputs"]
                break
        
        if not outputs:
            return None
        
        # Get Retrieve skill information from the resource
        agents = ["Automatic_Retriever"]
        connection_points = ["Default_Connection_Point"]
        
        try:
            resource = self.resource_nodes[resource_name]
            skills = resource["Skills"]
            if skills:
                agents_node = skills.Agents
                if agents_node:
                    for agent_name, agent in agents_node.children.items():
                        capabilities = agent.children.get("Capabilities")
                        if capabilities:
                            retrieve_cap = capabilities.children.get("Retrieve")
                            if retrieve_cap:
                                # Found Retrieve capability, extract agent and connection points
                                agents = [agent_name]
                                
                                # Get connection points from Supported_Connection_Points
                                cp_node = retrieve_cap.children.get("Supported_Connection_Points")
                                if cp_node and len(cp_node.children) > 0:
                                    connection_points = []
                                    for cp_name, cp in cp_node.children.items():
                                        cp_id_node = cp.children.get("Connection_Point_Id")
                                        if cp_id_node:
                                            connection_points.append(cp_id_node.value)
                                        else:
                                            connection_points.append(cp_name)
                                
                                break  # Found retrieve capability, use it
        except (KeyError, AttributeError, TypeError):
            pass  # Use default values if unable to read from resource
        
        # Create retrieve step for the first output (main product)
        retrieve_step = {
            resource_name: {
                "Skill": "Retrieve",
                "Agents": agents,
                "Resource_Connection_Points": connection_points,
                "Retrieved_Components": outputs
            }
        }
        
        return retrieve_step


#It should now make an ordered list of tasks based on the starting point (new function)
#Afterwards it should take those tasks one at a time and match them with resources (parameters and inputs and components) (also a new function)
#If a resource does not have the required components, then it should find a resoruce that does, and connect the two resources with our previous function find_resource_connection_points
# This way it can use the list of tasks and generate a full list of tasks with retrieve and transport and those things   



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
             {'Parameters': [{'Selected_Operation': 'Drilling'}, {"inputs" : ["Bottom_Cover_1"]}, {"outputs" : ["Bottom_Cover_1"]} ,{'Drill_Size': '3'}, {'Drill_Depth': '20'}]}]}
            ]}, 
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




#This should contain a class that we can construct with all the resources we have.
#This it should have a function that:
# allows us to insert a component and returns a list of resources that have the specific component in their internal storage
# allows us to check for at specific input and output match
# Maybe we should also have a function that just returns ALL storage for every resource which the line-controller can keep track of itself, maybe checking-in with the stations every 10 minutes to see if they agree
# Insert component into function that returns a resource and an amount
# allows us to insert two different resources and return a list, showing if and how they are connected through connection points
# Lastly, it should be able to generate a command that can later be sent over MQTT


