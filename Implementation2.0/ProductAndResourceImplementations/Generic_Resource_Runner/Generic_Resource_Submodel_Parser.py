import requests
import base64
import logging
import json

import Generic_Resource_Models as GRM


logging.basicConfig(
    level=logging.WARNING,  # <-- controls what you see
    format="%(levelname)s | %(name)s | %(message)s"
)

#This should be a class or number of classes that are used to generate and run a single resource 
#It should in take the resource shell id (which will be provided to it by the app)
#Step 1: Take the id and read the shell on the AAS server (The info for the server will be provided to it as well)
#Step 2: Read the individual submodels on the server
#Step 3: From each submodel, extract the relevant information
#Step 4: Use that information to create station behaviors for each of the resources actors (These will be defined somewhere, maybe as a different class)
#Step 5: The resource should then automatically start, BUT it is only able to actually perform any tasks IF the Communication submodel has some specific values. So it should poll for those values every 10 seconds.
#Bonus Step: If the resource is running, it updates the "ResourceActive" property in documentation, and if the resource is connected to an MQTT broker, it updates the "ResourceConnected" property in documentation.
# ALSO, if the resource is told it needs to terminate, then it updates "ResourceActive" and "ResourceConnected" to false before shutting down.

#So, I think maybe we should start by creating the generic parameter reading, execution and job_result creating, for each of the capability types.
#Could be in a class, but there might also be a better way of storing it.


class AASResourceLoader:

    def __init__(self, SERVER_BASE, SUBMODEL_ENDPOINT, SHELL_ENDPOINT):
        self.server_base = SERVER_BASE
        self.submodel_endpoint = SUBMODEL_ENDPOINT
        self.shell_endpoint = SHELL_ENDPOINT

    def _base64encode(self, value: str):

        encoded = base64.urlsafe_b64encode(
            value.encode("utf-8")
        ).decode("ascii")

        return encoded.rstrip("=")

    def load(self,shell_id: str) -> GRM.RawResourceModel:

        shell = self.read_shell(shell_id)

        
        submodels = self.read_submodels(shell)

        resource_model = GRM.RawResourceModel(shell=shell, submodels=submodels)
        self.print_summary(resource_model)

        return resource_model
    
    def read_shell(self, resource_shell_id:str) -> GRM.RawShell:
        encoded_shell_id = self._base64encode(resource_shell_id)

        response = requests.get(f"{self.shell_endpoint}/{encoded_shell_id}")

        if not response.ok:
            raise Exception(f"Failed to fetch shell: "f"{response.status_code}")

        shell = GRM.RawShell(id_short=response.json()["idShort"], shell_id=resource_shell_id, data=response.json())
        return shell
    
    def read_submodel(self, resource_submodel_id: str) -> GRM.RawSubmodel:

        encoded_submodel_id = self._base64encode(resource_submodel_id)
        response = requests.get(f"{self.submodel_endpoint}/{encoded_submodel_id}")
        if not response.ok:
            raise Exception(f"Failed to fetch submodel: {response.status_code}")
        data = response.json()

        semantic_id = None
        try:
            semantic_id = (data.get("semanticId", {}).get("keys", [{}])[0].get("value"))
        except Exception:
            semantic_id = None

        return GRM.RawSubmodel(
            id_short=data["idShort"],
            submodel_id=resource_submodel_id,
            semantic_id=semantic_id,
            data=data
        )
    
    def read_submodels(self,shell: GRM.RawShell) -> dict[str, GRM.RawSubmodel]:

        result = {}

        references = shell.data.get("submodels", [])

        for reference in references:

            keys = reference.get("keys", [])

            if not keys:
                continue

            submodel_id = keys[0]["value"]

            submodel = self.read_submodel(submodel_id)

            result[submodel.id_short] = submodel

        return result
    
    def print_summary(self,resource: GRM.RawResourceModel):

        logging.info(f"Shell: {resource.shell.id_short}")

        logging.info("Submodels:")

        for submodel in resource.submodels.values():
            logging.info(f"  - {submodel.id_short}")


class ResourceParser:

    def __init__(self):
        self.parsers = {}
        self.register_defaults()

    def register_defaults(self):
        self.register(GRM.SubmodelSemanticIDs.COMMUNICATION, CommunicationParser())
        self.register(GRM.SubmodelSemanticIDs.SKILLS, SkillsParser())
        self.register(GRM.SubmodelSemanticIDs.CAPABILITY, CapabilityParser())
        self.register(GRM.SubmodelSemanticIDs.INVENTORY, InventoryParser())

    def get_parser(self, semantic_id: str):
        return self.parsers.get(semantic_id)
        
    def register(self, semantic_id, parser):
        self.parsers[semantic_id] = parser

    def parse(self, raw: GRM.RawResourceModel):
        parsed_submodels = {}

        for submodel in raw.submodels.values():
            parsed = self._route_and_parse(submodel)
            if parsed is not None:
                parsed_submodels[submodel.id_short] = parsed

        return parsed_submodels

    def _route_and_parse(self, submodel: GRM.RawSubmodel):
        parser = self.parsers.get(submodel.semantic_id)

        if parser is None:
            logging.warning(f"[WARN] No parser registered for semanticId "f"{submodel.semantic_id}")
            return None

        return parser.parse(submodel)



class CommunicationParser:
    def __init__(self):
        self.utils = GRM.AASParserUtils()

    def parse(self, communication: GRM.RawSubmodel) -> GRM.MQTTConfig:

        elements = communication.data.get("submodelElements", [])

        mqtt_collection = self.utils.find_element(elements, "MQTT")
        mqtt_values = mqtt_collection.get("value", [])

        production_line_prefix = self.utils._get_property(mqtt_values, "ProductionLinePrefix")
        broker_id = self.utils._get_property(mqtt_values, "BrokerID")
        broker_port_raw = self.utils._get_property(mqtt_values, "BrokerPort")

        broker_port = int(broker_port_raw) if broker_port_raw else None

        suffixes_collection = self.utils.find_element(mqtt_values, "Suffixes")
        suffix_values = suffixes_collection.get("value", [])

        suffixes = GRM.MQTTSuffixes(
            command_suffix=self.utils._get_property(suffix_values, "CommandSuffix"),
            state_suffix=self.utils._get_property(suffix_values, "StateSuffix"),
            job_result_suffix=self.utils._get_property(suffix_values, "JobResultSuffix"),
            info_request_suffix=self.utils._get_property(suffix_values, "InfoRequestSuffix"),
            resource_acknowledgement_suffix=self.utils._get_property(suffix_values, "ResourceAcknowledgementSuffix"),
            controller_acknowledgement_suffix=self.utils._get_property(suffix_values, "ControllerAcknowledgementSuffix"),
            inventory_level_suffix=self.utils._get_property(suffix_values, "InventoryLevelSuffix"),
            occupancy_suffix=self.utils._get_property(suffix_values, "OccupancySuffix"),
            cargo_suffix=self.utils._get_property(suffix_values, "CargoSuffix"),
        )

        return GRM.MQTTConfig(
            production_line_prefix=production_line_prefix,
            broker_id=broker_id,
            broker_port=broker_port,
            suffixes=suffixes
        )
    


class SkillsParser:
    def __init__(self):
        self.utils = GRM.AASParserUtils()

    def parse(self, submodel: GRM.RawSubmodel) -> GRM.SkillsCollectionModel:

        skills = {}

        elements = submodel.data.get("submodelElements", [])

        for skill_block in elements:

            if skill_block.get("modelType") != "SubmodelElementCollection":
                continue

            skill_name = skill_block["idShort"]

            capability_ref = self._extract_capability_ref(skill_block)

            capability_type = self._extract_capability_type(skill_block)

            triggers = self._extract_triggers(skill_block)

            actors = self._extract_actors(skill_block)

            skills[skill_name] = GRM.SkillModel(
                name=skill_name,
                capability=GRM.CapabilityLinkModel(
                    capability_submodel_id=capability_ref,
                    capability_type_id=capability_type
                ),
                triggers=triggers,
                actors=actors
            )

        return GRM.SkillsCollectionModel(skills=skills)
    
    def _extract_capability_ref(self, skill_block):
        ref = self.utils.find_element(skill_block["value"],"CapabilitySubmodelReference")
        return (ref.get("value", {}).get("keys", [{}])[0].get("value"))
    
    def _extract_capability_type(self, skill_block):
        ref = self.utils.find_element(skill_block["value"],"CapabilityTypeReference")
        return (ref.get("value", {}).get("keys", [{}])[0].get("value"))
    
    def _extract_triggers(self, skill_block):
        trigger_list = self.utils.find_element(skill_block["value"],"SkillTriggers")
        return [trigger.get("value")for trigger in trigger_list.get("value", [])]

    def _extract_actors(self, skill_block):
        actor_list = self.utils.find_element(skill_block["value"],"Actors")
        return [actor.get("value")for actor in actor_list.get("value", [])]



class CapabilityParser:

    def __init__(self):
        self.utils = GRM.AASParserUtils()

    def parse(self,submodel: GRM.RawSubmodel) -> GRM.CapabilityModel:

        elements = submodel.data.get("submodelElements", [])
        category = self.utils._get_property(elements,"CapabilityCategory")
        capability_type_id = self.utils._get_property(elements,"CapabilityTypeReference")

        parameters = self._parse_parameters(elements)

        transformations = self._parse_transformations(elements)

        supported_components = self._parse_property_list(elements,"SupportedComponents")

        allowed_materials = self._parse_property_list(elements,"AllowedMaterials")

        return GRM.CapabilityModel(
            name=submodel.id_short,
            capability_category=category,
            capability_type=capability_type_id,
            parameters=parameters,
            process_transformations=transformations,
            supported_components=supported_components,
            allowed_materials=allowed_materials
        )

    def _parse_parameters(self,elements: list[dict]) -> dict[str, GRM.CapabilityParameter]:
        parameters_collection = self.utils.find_optional_element(elements,"Parameters")
        result = {}

        if not parameters_collection:
            return result

        for element in parameters_collection.get("value", []):
            parsed = self._parse_parameter_element(element)
            if parsed is None:
                continue

            result[parsed.name] = parsed

        return result

    def _parse_parameter_element(self,element: dict) -> GRM.CapabilityParameter:
        model_type = element.get("modelType")

        if model_type == "Property":
            return self._parse_property_parameter(element)

        elif model_type == "Range":
            return self._parse_range_parameter(element)

        elif model_type == "SubmodelElementCollection":
            return self._parse_collection_parameter(element)

        else:
            logging.warning(f"[WARN] Skipping unsupported parameter type: {model_type}")
            return None

    def _parse_property_parameter(self,element: dict) -> GRM.PropertyParameter:
        value_type = element.get("valueType")

        return GRM.PropertyParameter(
            name=element["idShort"],
            parameter_type="Property",
            value=self.utils.cast_value(element.get("value"),value_type),
            unit=element.get("semanticId", {}).get("keys", [{}])[0].get("value")
        )

    def _parse_range_parameter(self,element: dict) -> GRM.RangeParameter:
        value_type = element.get("valueType")

        return GRM.RangeParameter(
            name=element["idShort"],
            parameter_type="Range",
            min_value=self.utils.cast_value(element.get("min"),value_type),
            max_value=self.utils.cast_value(element.get("max"),value_type),
            unit=element.get("semanticId", {}).get("keys", [{}])[0].get("value")
        )

    def _parse_collection_parameter(self,element: dict):
        parameters = {}

        for child in element.get("value", []):
            parsed = self._parse_parameter_element(child)
            if parsed is None:
                continue
            parameters[parsed.name] = parsed

        return GRM.CollectionParameter(
            name=element["idShort"],
            parameter_type="Collection",
            parameters=parameters
        )

    def _parse_transformations(self,elements: list[dict]) -> dict[str, GRM.ProcessTransformationModel]:
        transformations_collection = self.utils.find_optional_element(elements,"ProcessTransformations")

        result = {}

        if not transformations_collection:
            return result

        for transformation in transformations_collection.get("value", []):
            name = transformation.get("idShort")
            input_types = self._extract_component_types(transformation,"InputTypes")

            output_types = self._extract_component_types(transformation,"OutputTypes")

            result[name] = GRM.ProcessTransformationModel(
                name=name,
                input_types=input_types,
                output_types=output_types
            )

        return result

    def _extract_component_types(self,transformation: dict,io_type: str) -> list[str]:

        io_collection = self.utils.find_optional_element(transformation.get("value", []),io_type)

        if not io_collection:
            return []

        list_container = self.utils.find_optional_element(io_collection.get("value", []),"ComponentTypeReference")

        if not list_container:
            return []

        return [item.get("value")for item in list_container.get("value", [])if item.get("value")]

    def _parse_property_list(self,elements: list[dict],list_name: str) -> list[str]:

        collection = self.utils.find_optional_element(elements,list_name)

        if collection is None:
            return []

        return [item.get("value")for item in collection.get("value", [])if item.get("value")]



class InventoryParser:

    def __init__(self):
        self.utils = GRM.AASParserUtils()
        self.raw_submodel = None

    def parse(self, submodel: GRM.RawSubmodel) -> GRM.InventoryModel:
        self.raw_submodel = submodel

        elements = submodel.data.get("submodelElements", [])
        inventories_element = self.utils.find_optional_element(elements, "Inventories")

        if not inventories_element:
            return GRM.InventoryModel(inventories={})

        inventories = {}

        for inventory in inventories_element.get("value", []):
            inventory_name = inventory["idShort"]

            inventories[inventory_name] = self._parse_inventory(inventory)

        return GRM.InventoryModel(inventories=inventories)

    def _parse_inventory(self, inventory: dict) -> GRM.InventoryData:

        # -------------------------
        # Specifications
        # -------------------------
        specs = self.utils.find_optional_element(inventory.get("value", []),"Specifications")

        inventory_size = 0

        if specs:
            inventory_size = int(
                self.utils._get_property(specs.get("value", []),"InventorySize") or 0)

        # -------------------------
        # Supported Components
        # -------------------------
        supported_element = self.utils.find_optional_element(inventory.get("value", []),"SupportedComponents")

        supported_components = []

        if supported_element:
            supported_components = [item.get("value")for item in supported_element.get("value", [])if item.get("value")]

        # -------------------------
        # Storage
        # -------------------------
        storage_element = self.utils.find_optional_element(inventory.get("value", []),"StoredComponents")

        storage = self._parse_storage(storage_element)

        return GRM.InventoryData(
            inventory_size=inventory_size,
            supported_components=supported_components,
            accessible_actors=[],  # not in submodel currently
            storage=storage
        )

    def _parse_storage(self, storage_element: dict | None) -> dict:

        storage = {}

        if not storage_element:
            return storage

        for slot in storage_element.get("value", []):

            slot_id = slot["idShort"]

            # Each SlotEntry contains:
            # - SlotReserved
            # - ComponentShellReference

            slot_elements = slot.get("value", [])

            reserved = self.utils._get_property(slot_elements, "SlotReserved")

            component_ref_element = self.utils.find_optional_element(
                slot_elements,
                "ComponentShellReference"
            )

            component_id = None

            if component_ref_element:
                value = component_ref_element.get("value")
                if value:
                    component_id = value.get("keys", [{}])[0].get("value")

            storage[slot_id] = GRM.InventorySlot(
                component_id=component_id,
                reserved=reserved
            )

        return storage

    def update_slot(self,inventory_name: str,slot_id: str,component_id: str | None):

        if self.raw_submodel is None:
            raise ValueError("Raw submodel not initialized. Call parse() first.")

        # -------------------------
        # Step 1: locate Inventories
        # -------------------------
        elements = self.raw_submodel.data.get("submodelElements", [])
        inventories_element = self.utils.find_element(elements,"Inventories")

        # -------------------------
        # Step 2: find correct inventory
        # -------------------------
        target_inventory = None

        for inv in inventories_element.get("value", []):
            if inv["idShort"] == inventory_name:
                target_inventory = inv
                break

        if not target_inventory:
            raise ValueError(f"Inventory '{inventory_name}' not found")

        # -------------------------
        # Step 3: find StoredComponents
        # -------------------------
        stored = self.utils.find_optional_element(target_inventory.get("value", []),"StoredComponents")
        if not stored:
            raise ValueError(f"StoredComponents not found in {inventory_name}")

        # -------------------------
        # Step 4: find slot
        # -------------------------
        target_slot = None

        for slot in stored.get("value", []):
            if slot["idShort"] == slot_id:
                target_slot = slot
                break

        if not target_slot:
            raise ValueError(f"Slot '{slot_id}' not found in {inventory_name}")

        # -------------------------
        # Step 5: update ComponentShellReference
        # -------------------------
        slot_elements = target_slot.get("value", [])

        component_ref = self.utils.find_optional_element(slot_elements,"ComponentShellReference")

        if component_ref is None:
            raise ValueError("ComponentShellReference missing in slot")

        # -------------------------
        # Step 6: write value (AAS format)
        # -------------------------
        if component_id is None:
            # clear slot
            component_ref.pop("value", None)
        else:
            component_ref["value"] = {
                "type": "ExternalReference",
                "keys": [
                    {
                        "type": "GlobalReference",
                        "value": str(component_id)
                    }
                ]
            }


