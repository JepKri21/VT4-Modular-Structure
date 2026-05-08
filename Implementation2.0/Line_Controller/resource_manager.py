import json
from datetime import datetime
from pathlib import Path
import sys
import requests
import base64
from typing import Dict, List, Tuple

sys.path.append(str(Path(__file__).resolve().parent.parent))

from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS


class ResourceManager:
    """
    Resource Manager Should Read all currently available resouces at a defined producton line, from the AAS Server with their Capabilities and Parameters? 
    """

    def __init__(self,MQTT_PORT,BASE_TOPIC,AAS_BROKER, AAS_PORT, RESOURCE_URL):
    #def __init__(self, aas_capabilities): #These two were from something older?
        #self.capabilities = aas_capabilities #Not entirely sure
        self.MQTT_PORT = MQTT_PORT
        self.BASE_TOPIC = BASE_TOPIC
        self.AAS_BROKER = AAS_BROKER
        self.AAS_PORT = AAS_PORT
        self.RESOURCE_URL = RESOURCE_URL

        self.AAS_SERVER_BASE = f"http://{self.AAS_BROKER}:{self.AAS_PORT}" 
        self.SUBMODEL_ENDPOINT = f"{self.AAS_SERVER_BASE}/submodels"
        self.SHELL_ENDPOINT = f"{self.AAS_SERVER_BASE}/shells"

        self.resource_shell_ids = {}



    def find_by_capability(self, capability_semantic_id):
        """
        Walk every known resource shell, inspect its Skills submodel, and
        return all (resource, skill) pairs whose CapabilityReference matches
        the requested capability semanticId.

        Returns a list of dicts:
            {
                "resource_id": <shell_id>,
                "skill_name": <skill idShort>,
                "capability_submodel_reference": <submodel id of the capability>,
            }
        """
        candidates = []

        for shell_id, status in self.resource_shell_ids.items():
            if status != "Active":
                continue

            skills = self.get_resource_skills(shell_id)
            for skill_name, skill_data in skills.items():
                if skill_data.get("CapabilityReference") == capability_semantic_id:
                    candidates.append({
                        "resource_id": shell_id,
                        "skill_name": skill_name,
                        "capability_submodel_reference": skill_data.get("CapabilitySubmodelReference"),
                    })

        return candidates
    
    #===========
    #Helper methods
    #===========
    def base64encode(self, value: str):
        encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
        encoded = encoded.rstrip("=")  # remove padding if server expects that
        #print(f"Printing encoded string: {encoded}")
        return encoded
    
    def find_by_idshort(self, data: Dict, target: str):
        if isinstance(data, dict):
            # Check current level
            if data.get("idShort") == target:
                return data

            # Recurse into values
            for value in data.values():
                result = self.find_by_idshort(value, target)
                if result:
                    return result

        elif isinstance(data, list):
            # Recurse into each item
            for item in data:
                result = self.find_by_idshort(item, target)
                if result:
                    return result

        return None

    def parse_element(self, element):
        model_type = element.get("modelType")

        if model_type == "Range":
            return self.parse_range(element)

        elif model_type == "Property":
            return self.parse_property(element)

        elif model_type == "SubmodelElementCollection":
            return self.parse_collection(element)

        else:
            # Ignore unsupported types (MultiLanguageProperty etc.)
            return None
    
    def parse_range(self, element):
        id_short = element.get("idShort")
        min_value = element.get("min")
        max_value = element.get("max")

        semantic_id = None
        if element.get("semanticId"):
            semantic_id = element["semanticId"]["keys"][0]["value"]

        if id_short:
            return MS.RangeElement(id_short=id_short, min=min_value, max=max_value, semantic_id=semantic_id)

        return None

    def parse_property(self, element):
        id_short = element.get("idShort")
        value = element.get("value")

        semantic_id = None
        if element.get("semanticId"):
            semantic_id = element["semanticId"]["keys"][0]["value"]

        if id_short:
            return MS.PropertyElement(id_short=id_short, value=value, semantic_id=semantic_id)

        return None

    def parse_collection(self, element):
        id_short = element.get("idShort")

        semantic_id = None
        if element.get("semanticId"):
            semantic_id = element["semanticId"]["keys"][0]["value"]

        collection_elements = []

        for child in element.get("value", []):
            parsed = self.parse_element(child)
            if parsed:
                collection_elements.append(parsed)

        if id_short:
            return MS.CollectionElement(id_short=id_short, elements=collection_elements, semantic_id=semantic_id)

        return None

    #===========
    #Methods to retrieve resource shells from AAS server
    #===========
    def update_resource_availablility(self):
        #This should only really read the server and find the shells that are resources
        response = requests.get(self.SHELL_ENDPOINT)
        data = response.json()
        resource_shells = data.get("result", [])
        for resource_shell in resource_shells:
            resoruce_shell_id = resource_shell["id"]
            if resoruce_shell_id.startswith(self.RESOURCE_URL):
                if resoruce_shell_id not in self.resource_shell_ids:
                    print(f"Updating list of resource with: {resoruce_shell_id}")
                    #Right now I directly set them to active, but in reality, it should ping the resource first
                    #This could be its own seperate method that you just call at the end of this method, passing the resources to check 
                    self.resource_shell_ids[resoruce_shell_id] = "Active"
                else:
                    print("Resource is already known")
        #It should be able to check if an older resource might not be on the server anymore?
        #Maybe better, each resource can be shown as active or inactive. 
        #So when we update we might also send a ping to the actual resource to make sure that it is active, 
        # otherwise we mark it as inactive

    def get_all_resource_readiness(self):
        #Call the same method that pings the resources to check if they are active
        return self.resource_shell_ids   

    #===========
    #Methods to read the Communication submodel
    #===========
    def get_resource_MQTT_suffixes(self, resource_shell_id: str) -> Dict[str, str]:
        #We could just read the entire communication submodel, but then we would end up with an entire submodel dictionary
        #It just become unwieldy quick, so I was thinking that we could just have a method for only getting the MQTT topics
        #So it should just read the submodel, extract the MQTT, then Sufixes, and then create this list

        #I was thinking that we just return the suffixes for that specific resource
        #Then we call it every time we want to use it instead of storing it
        #I think it might just make it easier to handle rather than those large dictionaries
        """
            {
                "CommandSuffix": "",
                "StateSuffix": "",
                "InfoRequestSuffix": "",
                "JobResultSuffix": "",
                "ResourceAcknowledgementSuffix": "",
                "ControllerAcknowledgementSuffix": ""
            }
        """

        result = {}        

        #Getting the specific communication submodel from the referenced shell
        encoded_resource_submodel_id = self.base64encode(f"{resource_shell_id}/Communication")
        response = requests.get(f"{self.SUBMODEL_ENDPOINT}/{encoded_resource_submodel_id}")

        if response.ok:
            #If we get a response, then we work on the data, finding the suffixes
            data = response.json()
            mqtt= self.find_by_idshort(data, "MQTT")
            suffixes = self.find_by_idshort(mqtt,"Suffixes")
            for suffix in suffixes["value"]:
                result[suffix["idShort"]] = suffix["value"]
        else:
            #There was a problem finding the id or bad connection
            print(f"There was a problem retrieving the Communication submodel: Response Status Code {response.status_code}")

        #If it is able to find the submodel, then it returns the dictionary, else it returns and empty one
        return result


    #===========
    #Methods to read the Skills submodel
    #===========
    def get_resource_skills(self,resource_shell_id: str):
        #What if made it only return list of skills and their capability reference
        #Then in another function you say, I want that skill, what actors can perform it and waht skilltriggers can I use
        #Maybe if we add a semantic ID to the capability reference
        """
            {
                "Drilling": {"CapabilitySubmodelReference": "", "CapabilityReference": ""},
                "Handoff": {"CapabilitySubmodelReference": "", "CapabilityReference": ""}
            }
        """

        #=============== FINDING THE SKILLS FIRST =================================

        #Then a seperate method will read and return the capability submodel and extract the parameters, allowed materials, and supported components
        result = {}
        #Getting the specific communication submodel from the referenced shell
        encoded_resource_submodel_id = self.base64encode(f"{resource_shell_id}/Skills")
        response = requests.get(f"{self.SUBMODEL_ENDPOINT}/{encoded_resource_submodel_id}")
        if response.ok:
            #If we get a response, then we work on the data, finding the suffixes
            data = response.json()
            skills_data= self.find_by_idshort(data, "Skills").get("submodelElements")

            for skill in skills_data:
                name = skill.get("idShort")

                # default structure
                result[name] = {"CapabilitySubmodelReference": None,"CapabilityReference": None}

                # look inside this element's "value" list, this gives us the actors, skill triggers and submodel reference
                for item in skill.get("value", []):
                    if item.get("idShort") == "CapabilitySubmodelReference":
                        # extract the actual reference value
                        keys = item.get("value", {}).get("keys", [])
                        #If there is a value, then we put it into the result
                        if keys:
                            result[name]["CapabilitySubmodelReference"] = keys[0].get("value")
        else:
            #There was a problem finding the id or bad connection
            print(f"There was a problem retrieving the Skills submodel: Response Status Code {response.status_code}")

        #If there are skills, then we look at their capabilities
        if len(result) == 0:
            return result
        
        #============== FINDING THE CAPABILITY REFERENCES AFTERWARDS ===================

        #For each skill we want to look at the capability submodel
        for skill_name, skill_data in result.items():
            #Then we extract the CapabilitySubmodelReference from the skill
            capability_submodel_reference = skill_data.get("CapabilitySubmodelReference")

            if not capability_submodel_reference:
                continue

            encoded_resource_submodel_id = self.base64encode(f"{capability_submodel_reference}")
            response = requests.get(f"{self.SUBMODEL_ENDPOINT}/{encoded_resource_submodel_id}")

            #If we then get the capability submodel, all we want to do is read the CapabilityReference
            #Which is directly below the top level
            if response.ok:
                data = response.json()
                capability_reference= self.find_by_idshort(data, "CapabilityReference")
                if capability_reference:
                    result[skill_name]["CapabilityReference"] = capability_reference.get("value")
                else:
                    print("CapabilityReference is None for some reason")
            else:
                #There was a problem finding the id or bad connection
                print(f"There was a problem retrieving the Capability submodel: Response Status Code {response.status_code}")


        #If it is able to find the submodel, then it returns the dictionary, else it returns and empty one
        #This could be a lot shorter if the skills submodel also has the Capability Reference
        return result

    def get_skill_information(self, resource_shell_id: str, skill_name: str) -> Tuple[List[str], List[str]]:
        #Similar to the other functions, just read the skills submodel, and extract the actors, and skill triggers
        actors = []
        skill_triggers = []

        #Getting the specific communication submodel from the referenced shell
        encoded_resource_submodel_id = self.base64encode(f"{resource_shell_id}/Skills")
        response = requests.get(f"{self.SUBMODEL_ENDPOINT}/{encoded_resource_submodel_id}")

        if response.ok:
            #If we get a response, then we work on the data, finding the suffixes
            data = response.json()
            #We extract the data of the desired skill
            skill_data= self.find_by_idshort(data, skill_name).get("value")
            #Then we extract the skill triggers and the actors
            skill_triggers_data = self.find_by_idshort(skill_data, "SkillTriggers").get("value")
            actors_data = self.find_by_idshort(skill_data,"Actors").get("value")

            #Before adding them to a list
            if skill_triggers_data is not None:
                for item in skill_triggers_data:
                    skill_triggers.append(item.get("value"))
            if actors_data is not None:
                for item in actors_data:
                    actors.append(item.get("value"))
        
        else:
            print(f"There was a problem retrieving the Skills submodel: Response Status Code {response.status_code}")
        return actors, skill_triggers

    #===========
    #Methods to read the Capability submodels
    #===========
    def get_capability_parameters(self,capability_submodel_reference:str):
        #Should read the capability submodel and extract the parameters, the supported components and the allowed materials
        #Return them as seperate variables

        parameters = []
        supported_components = []
        allowed_materials = []

        """
        allowed_materials = ["https://aausmartlab.org/Materials/PLA",
                            "https://aausmartlab.org/Materials/ABS"]
        supported_components = ["https://aausmartlab.org/Shells/Component/Bottom_Cover,
                                "https://aausmartlab.org/Shells/Component/Top_Cover]
        parameters = [PropertyElement, RangeElement, RangeElement, CollectionElement]
        """

        encoded_resource_submodel_id = self.base64encode(f"{capability_submodel_reference}")
        response = requests.get(f"{self.SUBMODEL_ENDPOINT}/{encoded_resource_submodel_id}")

        #We are reading the capability submodel (that is the data), we want Parameters, AllowedMaterials and SupportedComponents
        #We could create smaller helper functions and then use those in here. 
        # That would significantly reduce the size of this method
        if response.ok:
            data = response.json()
            parameters_node = self.find_by_idshort(data, "Parameters")

            #If there are parameters, we continue looking deeper
            if parameters_node:
                for element in parameters_node.get("value",[]):
                    parameter = self.parse_element(element)
                    if parameter:
                        parameters.append(parameter)
                        
            else:
                print("Parameters is None for some reason")

            allowed_materials_node = self.find_by_idshort(data, "AllowedMaterials")
            if allowed_materials_node:
                for element in allowed_materials_node.get("value"):
                    allowed_materials.append(element.get("value"))

            else:
                print("AllowedMaterials is None for some reason")

            supported_components_node = self.find_by_idshort(data, "SupportedComponents")
            if supported_components_node:
                for element in supported_components_node.get("value"):
                    supported_components.append(element.get("value"))

            else:
                print("SupportedComponents is None for some reason")



            if parameters is not None:
                if supported_components is not None:
                    if allowed_materials is not None:
                        return parameters, supported_components, allowed_materials
                    else:
                        print("No 'AllowedMaterials' present in the capability submodel")
                        return None
                else:
                    print("No 'SupportedComponents' present in the capability submodel")
                    return None
            else:
                print("No 'Parameters' present in the capability submodel")
                return None
        
        if not response.ok:
            raise Exception(f"Failed to fetch Capability submodel: {response.status_code}")

    #The get_capability_parameters method works pretty well. 
    # We just need to figure out how to handle empty spots in value of parameters
    # Specifically with the handoff capability. How we say we want a target position
        # We could probably even remove the Component Reference and just use supported components
        # But the problem is still there for the target position
        # Maybe we could just use ranges, and just kinda use the input/output zone to define the ranges.

#What if we had a function in the resource manager that would find all the resources from the server
#Right now it is done the the main script, but should it really be done there? 
# Also it might be smart only to store the resource IDs in here. 
# And then we just call the server every time we want to look at different submodels
#That way we can update the shells on the fly, and we won't have to directly store them in here, which could be a mess.

#Second, we will need a function that looks at the communication submodel to see where to send commands
#This function could also be combined with the ability to send commands.
#So you would write something like, I need to send this package, to this resource, this actor and the message is a command.
#Then the function only needs to find the communication submodel of the resource, find the command suffix, and then it can send

    #ControllerMQTTClient class
        #dynamic on_message Method that automatically listens to all resource topics that are NOT CMD, InfoRequest and ControllerAcknowledgementSuffix cycletime, alarms, quality, throughput and publishes to DB for Data Analytics Layer
        #Method for requesting inventory levels from all resources with an InventoryLevelSuffix
        #Method that reads the state and continuously updates whether they are active or inactive based on response (if state is frequently updated it can assume that it is still active, if no update has been made in a while, it sends a state request)

#There is a MAJOR problem with how the skills and capabilities are defined. 
    # First problem: If two resources both have a drilling capability, but they have slightly different parameters for it (which is probably common)
    # How do we make sure that a product can go through both? How do we tell it what parameters to use for each of them. Unless we make it very specific to one specific type of resource
        # We think that a solution could be achieved by defining required and optional parameters both on the product and the capability
        #That way, you can define even custom parameters as requried in the product and that way you ONLY go to the specific resources with the required parameters
        #But you can also define
        #Resource with a specific capability like Drilling should ALWAYS have the same required parameters, but you can add as many optional as you want
        #Either that OR the resourece will ALWAYS have the same required parameters, BUT you can also add custom required parameters as well as optional
        # The resource should be able to perform drilling, even without the optional parameters
        #NOTE: IF two actors on the same resource have the same capability just with different parameters then they should likely still have unique capability submodels

    #Second problem: If there are two actors on the same resource that have the same capability, but NOT the same skilltriggers availble, then how do you tell them apart?
    # And then we just assume that EVERY resource runs PackML or at least uses the PackML triggers. Does not make sense to allow different names here, like it would the suffixes
        #If we simply switch the skill around to look a bit more like how we structured it the first time around
        #So it would be skillName -> ActorName -> SkillTriggers and CapabilitySubmodelReference.
        #This does take up more space, but it allows actors to have different skilltriggers and reference unique capability submodels, even if they are for the same skill

if __name__ == "__main__":
    AAS_BROKER = "localhost"
    MQTT_PORT = 1883
    BASE_TOPIC = "AAUSmartLab/ProductionLine1"
    AAS_PORT = "8081"
    resources_url = "https://aausmartlab.org/Shells/Resources"

    rm = ResourceManager(MQTT_PORT, BASE_TOPIC, AAS_BROKER, AAS_PORT, resources_url)

    #Updating the list of resource based on the AAS server
    rm.update_resource_availablility()

    #A function that should update whether the resources are active or not and return the full list of resources
    Resources = rm.get_all_resource_readiness()

    Resource_ids = list(Resources.keys())

    #print(Resource_ids)

    #print(rm.get_resource_MQTT_suffixes(Resource_ids[0]))

    resource_skills = rm.get_resource_skills(Resource_ids[0])

    resource_skill_names = list(resource_skills.keys())

    #print(resource_skills)

    for skill_name in resource_skill_names:
    #    actors, skill_triggers = rm.get_skill_information(Resource_ids[0],skill_name)
    #    print(actors)
    #    print(skill_triggers)
        print(rm.get_capability_parameters(resource_skills[skill_name].get("CapabilitySubmodelReference")))