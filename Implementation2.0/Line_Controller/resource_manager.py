import json
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
        # Optional whitelist of full shell IRIs to keep. Set on the first
        # call to update_resource_availablility(); subsequent calls (e.g. from
        # the MQTT controller's on_connect) reuse it so templates don't leak
        # back into the registry. We filter by full IRI rather than trailing
        # segment because the line-config idShort isn't always equal to the
        # shell's last URL segment (e.g. Assembly_Screwing_01 vs.
        # Assembly_Screwing_01_<uuid>).
        self._allowed_iris: set[str] | None = None

    @staticmethod
    def topic_id_for_iri(iri: str) -> str:
        """Last URI segment of a shell IRI — the resource_id used in MQTT topics.

        Per-actor PackML state lives on the controller's
        `shared_handler_variable["state"]`, populated by
        `handle_state_message` in main.py. The scheduler reads it from there
        (see `Scheduler._wait_for_idle`). ResourceManager intentionally no
        longer owns that runtime state.
        """
        return iri.rstrip("/").split("/")[-1]

    # =========================================================================
    # Convenience queries on the AAS data
    # =========================================================================

    def has_handoff(self, shell_iri: str) -> bool:
        """True if this resource declares any skill whose capability is Handoff."""
        cap_handoff = "https://aausmartlab.org/Submodels/Capability/Handoff"
        for skill_data in self.get_resource_skills(shell_iri).values():
            if skill_data.get("CapabilityReference") == cap_handoff:
                return True
        return False

    def actors_for_skill(self, shell_iri: str, skill_name: str) -> List[str]:
        """All actor names that can perform `skill_name` on `shell_iri`."""
        actors, _ = self.get_skill_information(shell_iri, skill_name)
        return actors or []

    def find_skill_offering(
        self, skill_name: str
    ) -> List[Tuple[str, str, List[str]]]:
        """All resources offering a skill by idShort.

        Returns:
            [(shell_iri, topic_id, actors), ...].
        """
        out = []
        for iri in self.resource_shell_ids:
            skills = self.get_resource_skills(iri)
            if skill_name not in skills:
                continue
            actors = self.actors_for_skill(iri, skill_name)
            if actors:
                out.append((iri, self.topic_id_for_iri(iri), actors))
        return out



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
            # if status != "Active": #<- This was the before
            # Skip only resources we know are dead. UNREACHABLE-by-default
            # (the state assigned when the shell is first discovered) still
            # passes through — the scheduler will find out it's offline when
            # the CMD doesn't get answered.
            if status == MS.ResourceReachability.INACTIVE:
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
    def update_resource_availablility(self, allowed_iris: set[str] | None = None):
        """Pull resource shells from the AAS server and add them to the registry.

        If `allowed_iris` is provided, only shells whose full IRI is in the
        set are added — this keeps generic/template shells out of the live
        registry. Pass the IRIs from the line config's ResourceReferences,
        e.g. `{loc.resource_iri for loc in line_config.locations.values()}`.
        """
        if allowed_iris is not None:
            self._allowed_iris = set(allowed_iris)
        effective_filter = self._allowed_iris

        response = requests.get(self.SHELL_ENDPOINT)
        data = response.json()
        resource_shells = data.get("result", [])
        for resource_shell in resource_shells:
            resoruce_shell_id = resource_shell["id"]
            if not resoruce_shell_id.startswith(self.RESOURCE_URL):
                continue

            if effective_filter is not None and resoruce_shell_id not in effective_filter:
                if resoruce_shell_id not in self.resource_shell_ids:
                    print(f"Skipping resource (not in line config): {resoruce_shell_id}")
                continue

            if resoruce_shell_id not in self.resource_shell_ids:
                print(f"Updating list of resource with: {resoruce_shell_id}")
                self.resource_shell_ids[resoruce_shell_id] = MS.ResourceReachability.UNREACHABLE
            else:
                print("Resource is already known")
        #It should be able to check if an older resource might not be on the server anymore?
        #Maybe better, each resource can be shown as active or inactive. 
        #So when we update we might also send a ping to the actual resource to make sure that it is active, 
        # otherwise we mark it as inactive
        return self.resource_shell_ids  

    #def get_all_resource_readiness(self):
    #    #Call the same method that pings the resources to check if they are active
    #    return self.resource_shell_ids   

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
            skills_data = self.find_by_idshort(data, "Skills").get("submodelElements") or []

            # Two known shapes for Skills submodels:
            #   A) [DrillingCol, HandoffCol, ...]            — skills directly at top
            #   B) [SkillCol[AssembleCol, HandoffCol, ...]]  — skills nested under
            #      a single "Skill" SubmodelElementCollection (current generator)
            # If we see shape (B), descend one level.
            if (len(skills_data) == 1
                    and skills_data[0].get("idShort") in ("Skill", "Skills")
                    and isinstance(skills_data[0].get("value"), list)):
                skills_data = skills_data[0]["value"]

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

            # Two shapes for the capability identity:
            #   A) the submodel's top-level semanticId (older template), or
            #   B) a child Property element with idShort
            #      "CapabilityTypeReference" (current generator).
            if response.ok:
                data = response.json()
                capability_reference = None
                semantic_keys = (data.get("semanticId") or {}).get("keys", [])
                if semantic_keys:
                    capability_reference = semantic_keys[0].get("value")
                if not capability_reference:
                    for el in data.get("submodelElements", []) or []:
                        if (el.get("idShort") == "CapabilityTypeReference"
                                and el.get("modelType") == "Property"):
                            capability_reference = el.get("value")
                            break
                if capability_reference:
                    result[skill_name]["CapabilityReference"] = capability_reference
                else:
                    print(
                        f"No CapabilityTypeReference / top-level semanticId on "
                        f"capability submodel for skill '{skill_name}' "
                        f"({capability_submodel_reference})"
                    )
            else:
                #There was a problem finding the id or bad connection
                print(
                    f"There was a problem retrieving the Capability submodel: "
                    f"Response Status Code {response.status_code} "
                    f"(skill='{skill_name}', ref='{capability_submodel_reference}')"
                )


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
    def get_capability_parameters(self, capability_submodel_reference: str):
        """Read a capability submodel and return its declared envelope.

        Returns a 4-tuple:
            (parameters, supported_components, allowed_materials, process_transformations)

        - parameters: list of parsed Property / Range / Collection elements
          (the Parameters submodel element collection).
        - supported_components: list[str] of ComponentTypeReference IRIs.
          Empty/missing = no restriction (treated as "any" by the matcher).
        - allowed_materials: list[str] of material IRIs.
          Empty/missing = no restriction (treated as "any" by the matcher).
        - process_transformations: list[{"name", "input_types", "output_types"}]
          enumerating the discrete input/output transformations this
          capability supports. Empty list = no declared transformations.

        Returns None only if the submodel cannot be fetched.
        """
        parameters = []
        supported_components = []
        allowed_materials = []
        process_transformations: list[dict] = []

        encoded_resource_submodel_id = self.base64encode(f"{capability_submodel_reference}")
        response = requests.get(f"{self.SUBMODEL_ENDPOINT}/{encoded_resource_submodel_id}")

        if not response.ok:
            print(f"Failed to fetch Capability submodel: {response.status_code}")
            return None

        data = response.json()
        parameters_node = self.find_by_idshort(data, "Parameters")
        if parameters_node:
            for element in parameters_node.get("value", []) or []:
                parameter = self.parse_element(element)
                if parameter:
                    parameters.append(parameter)

        allowed_materials_node = self.find_by_idshort(data, "AllowedMaterials")
        if allowed_materials_node:
            for element in allowed_materials_node.get("value", []) or []:
                v = element.get("value")
                # Skip placeholder Property entries with no value — the
                # template often ships a single empty Property to advertise
                # the list's shape. Empty list ⇒ "no restriction".
                if v is None or v == "":
                    continue
                allowed_materials.append(v)

        supported_components_node = self.find_by_idshort(data, "SupportedComponents")
        if supported_components_node:
            for element in supported_components_node.get("value", []) or []:
                v = element.get("value")
                if v is None or v == "":
                    continue
                supported_components.append(v)

        process_transformations_node = self.find_by_idshort(data, "ProcessTransformations")
        if process_transformations_node:
            process_transformations = self._parse_process_transformations(
                process_transformations_node
            )

        return parameters, supported_components, allowed_materials, process_transformations

    def _parse_process_transformations(self, node: Dict) -> List[Dict]:
        """Parse a ProcessTransformations SubmodelElementCollection.

        Expected shape (after the AAS server's JSON serialisation):

            ProcessTransformations (SubmodelElementCollection)
              value:
                <NamedTransformation> (SubmodelElementCollection)
                  value:
                    InputTypes (SubmodelElementCollection)
                      value:
                        ComponentTypeReference (SubmodelElementList | list of Property)
                    OutputTypes (SubmodelElementCollection)
                      value:
                        ComponentTypeReference (SubmodelElementList | list of Property)

        Returns a list like:
            [{"name": "BottomCoverAndPCB", "input_types": [iri, iri], "output_types": [iri]}, ...]

        Tolerates both the SubmodelElementList wrapper (`ComponentTypeReference`)
        and bare Property children inside the InputTypes / OutputTypes
        collections.
        """
        results: List[Dict] = []
        for transformation in node.get("value", []) or []:
            name = transformation.get("idShort")
            inner = transformation.get("value", []) or []

            input_types = self._extract_component_type_refs(
                self.find_by_idshort(inner, "InputTypes")
            )
            output_types = self._extract_component_type_refs(
                self.find_by_idshort(inner, "OutputTypes")
            )
            results.append({
                "name": name,
                "input_types": input_types,
                "output_types": output_types,
            })
        return results

    def _extract_component_type_refs(self, types_node) -> List[str]:
        """Pull the leaf value strings out of an InputTypes/OutputTypes node.

        The capability template wraps the list in a `ComponentTypeReference`
        SubmodelElementList, but we accept bare Property children too so
        small schema variations don't break parsing.
        """
        if not types_node:
            return []
        values: List[str] = []
        for element in types_node.get("value", []) or []:
            if element.get("modelType") in ("SubmodelElementList", "SubmodelElementCollection"):
                for prop in element.get("value", []) or []:
                    v = prop.get("value")
                    if v is not None:
                        values.append(v)
            else:
                v = element.get("value")
                if v is not None and not isinstance(v, (list, dict)):
                    values.append(v)
        return values

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

# State + InfoRequest helpers used to live here. They moved:
#   - The MQTT state handler is now `handle_state_message` in main.py (V2
#     style, writes into `controller.shared_handler_variable["state"]`).
#   - The InfoRequest fan-out at startup is now `controller.request_data(...)`
#     from MQTTClientControllerV2.
# ResourceManager no longer touches MQTT directly.


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