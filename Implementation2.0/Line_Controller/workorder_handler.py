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

            ingredient = step["ingredient"]
            dependencies = graph.get(ingredient, [])

            # check if all dependencies are completed
            if all(self._is_ingredient_complete(dep) for dep in dependencies):
                ready_steps.append(step)

        return ready_steps

    def _is_ingredient_complete(self, ingredient):
        for step in self.execution_plan["steps"]:
            if step["ingredient"] == ingredient:
                return step["state"] == StepStates.COMPLETED
        return True  # no process = already "ready"

    # =============================
    # UPDATE STEP STATE
    # =============================
    def update_step(self, step_id, state: StepStates, resource=None):
        step = self._find_step(step_id)

        step["state"] = state

        if resource:
            step["assigned_resource"] = resource

        if state == "assigned":
            step["timestamps"][StepStates.ASSIGNED] = datetime.now()
        elif state == "in_progress":
            step["timestamps"][StepStates.IN_PROGRESS] = datetime.now()
        elif state == "complete":
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
        return{
            "CapabilityReference": step["required_capability"],
            "Parameters": step["parameters"],
            "Ingredient": step["ingredient"]
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
