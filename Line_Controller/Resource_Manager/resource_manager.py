import sys
from pathlib import Path


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

                    io_maps = capability.children.get("Input/Output_Mappings")
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


                              
                                    

if __name__ == "__main__":
    AAS_SERVER = "http://192.168.38.200:8081"
    
    reader = AASShellReader(AAS_SERVER)

    all_assets, resources, products = reader.return_correlated_assets()

    rm = ResourceManager(resources)

    # Check if a resource has the given skill, and can perform it on a specific component ✅
    matches = rm.check_skill_and_component("Assemble", "Bottom_Cover")
    
    print("=====================")
    print("Matches:\n")

    if not matches:
        print("No resources found")

    for resource in matches:
        print(matches)


#This should contain a class that we can construct with all the resources we have.
#This it should have a function that:
# allows us to insert a requried skill and component and recieve a list of resoruces that have that skill and is compatible with that component
# allows us to insert a component and returns a list of resources that have the specific component in their internal storage
# allows us to check for at specific input and output match
# allows us to insert two different resources and return a list, showing if and how they are connected through connection points
# Lastly, it should be able to generate a command that can later be sent over MQTT