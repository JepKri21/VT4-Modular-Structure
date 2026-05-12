import json
from datetime import datetime
from pathlib import Path
import enum

class StepStates(str, enum.Enum):
    COMPLETED = "COMPLETED"
    IN_PROGRESS = "IN_PROGRESS"
    ASSIGNED = "ASSIGNED"
    PENDING = "PENDING"
    PLANNED = "PLANNED"

class WorkOrderHandler:

    def __init__(self):
        self.workorder = None
        self.execution_plan = None

    # =============================
    # LOAD WORKORDER
    # =============================
    def load_workorder(self, workorder_json: dict):
        self.workorder = workorder_json
        self.execution_plan = self._generate_execution_plan()

    # =============================
    # BUILD DEPENDENCY GRAPH
    # =============================
    def _build_dependency_graph(self):
        assemblies = self.workorder.get("Assemblies", {})
        graph = {}

        for ingredient, data in assemblies.items():
            graph[ingredient] = data.get("Ingredients", [])

        return graph

    # =============================
    # FIND FINAL PRODUCT INGREDIENT
    # =============================
    def _find_final_ingredient(self):
        target = self.workorder["ProductReference"]
        ingredients = self.workorder["Ingredients"]

        for name, data in ingredients.items():
            if data.get("ComponentReference", "").endswith(target):
                return name

        raise ValueError("Final product ingredient not found")

    # =============================
    # COMPUTE PRECEDENCE LEVELS
    # =============================
    def _compute_precedence_levels(self):
        graph = self._build_dependency_graph()
        final_node = self._find_final_ingredient()

        levels = {}

        def dfs(node):
            if node not in graph or not graph[node]:
                levels[node] = 0
                return 0

            max_dep = max(dfs(dep) for dep in graph[node])
            levels[node] = max_dep + 1
            return levels[node]

        dfs(final_node)
        return levels

    # =============================
    # GENERATE EXECUTION PLAN
    # =============================
    def _generate_execution_plan(self):
        precedence_map = self._compute_precedence_levels()
        steps = []

        process_steps = self.workorder.get("ProcessSteps", {})

        for ingredient, step_dict in process_steps.items():
            for step_name, step_data in step_dict.items():

                step = {
                    "step_id": step_data["ProcessStepId"],
                    "name": step_name,
                    "ingredient": ingredient,

                    "required_capability": step_data["CapabilityReference"],
                    "parameters": step_data.get("Parameters", {}),
                    "dependencies": step_data.get("Dependencies", []),

                    "precedence": precedence_map.get(ingredient, 0),

                    "state": StepStates.PENDING,
                    "assigned_resource": None,

                    "timestamps": {
                        "assigned": None,
                        "started": None,
                        "completed": None
                    }
                }

                steps.append(step)

        return {
            "workorder_id": self.workorder["OrderId"],
            "product": self.workorder["ProductReference"],
            "state": StepStates.PLANNED,
            "steps": steps
        }

    # =============================
    # GET READY STEPS
    # =============================
    def get_ready_steps(self):
        steps = self.execution_plan["steps"]
        graph = self._build_dependency_graph()

        ready_steps = []

        for step in steps:
            if step["state"] != StepStates.PENDING:
                continue

            # Sub-ingredients of this step's ingredient must be fully complete
            # (recursively, through the assembly graph).
            sub_ingredients = graph.get(step["ingredient"], [])
            if not all(self._is_ingredient_complete(dep) for dep in sub_ingredients):
                continue

            # Per-step dependencies (other step_ids that must be done first).
            if not self._dependencies_complete(step.get("dependencies", [])):
                continue

            ready_steps.append(step)

        return ready_steps

    def _is_ingredient_complete(self, ingredient):
        """
        An ingredient is complete when:
          - every sub-ingredient (assembly child) is complete, recursively, and
          - every process step that targets this ingredient is COMPLETED.
        Leaf ingredients with no steps and no sub-ingredients are considered
        raw inputs — they are always "complete" as far as the process graph
        is concerned (sourcing is the resource manager's problem, not the
        workorder's).
        """
        graph = self._build_dependency_graph()

        for child in graph.get(ingredient, []):
            if not self._is_ingredient_complete(child):
                return False

        own_steps = [s for s in self.execution_plan["steps"] if s["ingredient"] == ingredient]
        if not own_steps:
            # No transformation defined for this ingredient — it is either a
            # raw component or a pure aggregator whose readiness is decided
            # entirely by its children (already checked above).
            return True

        return all(s["state"] == StepStates.COMPLETED for s in own_steps)

    def _dependencies_complete(self, dependency_step_ids):
        if not dependency_step_ids:
            return True
        for dep_id in dependency_step_ids:
            try:
                dep_step = self._find_step(dep_id)
            except ValueError:
                return False
            if dep_step["state"] != StepStates.COMPLETED:
                return False
        return True

    # =============================
    # UPDATE STEP STATE
    # =============================
    def update_step(self, step_id, state: StepStates, resource=None):
        step = self._find_step(step_id)

        step["state"] = state

        if resource:
            step["assigned_resource"] = resource

        if state == StepStates.ASSIGNED:
            step["timestamps"][StepStates.ASSIGNED] = datetime.now()
        elif state == StepStates.IN_PROGRESS:
            step["timestamps"][StepStates.IN_PROGRESS] = datetime.now()
        elif state == StepStates.COMPLETED:
            step["timestamps"][StepStates.COMPLETED] = datetime.now()

        self._update_workorder_state()

    # =============================
    # UPDATE WORKORDER STATE
    # =============================
    def _update_workorder_state(self):
        steps = self.execution_plan["steps"]

        if all(s["state"] == StepStates.COMPLETED for s in steps):
            self.execution_plan["state"] = StepStates.COMPLETED
        elif any(s["state"] == StepStates.IN_PROGRESS for s in steps):
            self.execution_plan["state"] = StepStates.IN_PROGRESS

    # =============================
    # FIND STEP
    # =============================
    def _find_step(self, step_id):
        for step in self.execution_plan["steps"]:
            if step["step_id"] == step_id:
                return step
        raise ValueError(f"Step {step_id} not found")

    # =============================
    # PRINT PROCESS LIST
    # =============================
    def print_process_list(self):
        print("\n=== PROCESS LIST ===")

        for step in sorted(self.execution_plan["steps"], key=lambda x: x["precedence"]):
            print(f"""
                Step ID: {step['step_id']}
                Name: {step['name']}
                Ingredient: {step['ingredient']}
                Capability: {step['required_capability']}
                Precedence: {step['precedence']}
                State: {step['state']}
                Assigned Resource: {step['assigned_resource']}
                """)

    # =============================
    # EXPORT FOR OTHER SCRIPTS
    # =============================
    def get_execution_plan(self):
        return self.execution_plan

        
     #=============================
     #GET STEP PARAMETERS
     #=============================
    def get_step_parameters(self, step_id):
        step = self._find_step(step_id)
        return step["parameters"]

    def get_step_capability(self,step_id):
        step = self._find_step(step_id)
        
        return step["required_capability"]

    def get_step_execution_info(self, step_id):
        step = self._find_step(step_id)
        ingredient_name = step["ingredient"]

        ingredients = self.workorder.get("Ingredients", {})
        properties = self.workorder.get("Properties", {})

        component_reference = ingredients.get(ingredient_name, {}).get("ComponentReference")

        material = None
        material_block = properties.get(ingredient_name, {}).get("MaterialProperties", {})
        if isinstance(material_block, dict):
            material = material_block.get("Material", {}).get("value")

        return {
            "CapabilityReference": step["required_capability"],
            "Parameters": step["parameters"],
            "Ingredient": ingredient_name,
            "ComponentReference": component_reference,
            "Material": material,
        }
    

if __name__ == "__main__":

    script_dir = Path(__file__).parent
    file_path = script_dir / "WorkOrderExampleComplex.json"

    with open(file_path) as f:
        order = json.load(f)

    handler = WorkOrderHandler()
    handler.load_workorder(order)

    # Print full process list
    handler.print_process_list()
    # Get ready steps (for resource manager)
    ready = handler.get_ready_steps()
    print("\n=== READY STEPS ===")
    for step in ready:
        print(step["step_id"], step["required_capability"])
    
    print("GETTING STEP 1x1 PARAMETERS")
    print(handler.get_step_parameters("1x1"))

    print("UPDATING 1x1 PROCESS")
    handler.update_step("1x1", StepStates.ASSIGNED, resource="Drilling_1")

    handler.print_process_list()

    handler.update_step("1x1", StepStates.COMPLETED)

    handler.print_process_list()
    
    ready = handler.get_ready_steps()
    print("\n=== READY STEPS ===")
    for step in ready:
        print(step["step_id"], step["required_capability"])


#IMPORTANT NOTE: WE NEED TO FIX THE PRECEDENCE THING WITH get_ready_steps(), IT PRINTS ALL STEPS AS READY FROM THE BEGINNING
    

#Then we probably need a resource manager and inventory manager to figure out where components are located and transport them to correct positions

#We will need a script that generates these extra steps and handles them, before we then execute the steps in here. They should likely be seperate 
#So the script might get a "step-order" to perform drilling on this component/type with these properties and parameters
#And then it creates like a small execution plan that only covers a single of those value-adding steps
