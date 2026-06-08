from pydantic import BaseModel

#====================================
#======== Parsing Helpers ===========
#====================================

class AASParserUtils:

    def __init__(self):
        pass

    def find_element(self, elements: list,id_short: str) -> dict:

        for element in elements:
            if element.get("idShort") == id_short:
                return element

        raise ValueError(f"Element '{id_short}' not found")
    
    def find_optional_element(self, elements: list,id_short: str) -> dict | None:

        for element in elements:
            if element.get("idShort") == id_short:
                return element

        return None
    
    def _get_property(self, elements: list[dict], id_short: str):
        try:
            prop = self.find_element(elements, id_short)

            value = prop.get("value")
            value_type = prop.get("valueType")

            return self.cast_value(value, value_type)

        except Exception:
            return None
        
    def cast_value(self, value: str, value_type: str | None):
        if value is None:
            return None

        if value_type is None:
            return value

        try:
            if value_type == "xs:boolean":
                return str(value).lower() == "true"

            if value_type in ["xs:integer", "xs:int"]:
                return int(value)

            if value_type in ["xs:float", "xs:double", "xs:decimal"]:
                return float(value)

            if value_type == "xs:string":
                return str(value)

        except Exception:
            # fallback: return raw value if parsing fails
            return value

        return value
        
class SubmodelSemanticIDs:
    CAPABILITY = "https://aausmartlab.org/Semantics/SubmodelTypes/Capability"
    SKILLS = "https://aausmartlab.org/Semantics/SubmodelTypes/Skills"
    INVENTORY = "https://aausmartlab.org/Semantics/SubmodelTypes/Inventory"
    COMMUNICATION = "https://aausmartlab.org/Semantics/SubmodelTypes/Communication"
    RESOURCEZONES = "https://aausmartlab.org/Semantics/SubmodelTypes/ResourceZones"

#====================================
#======== For loading AAS ===========
#====================================

class RawShell(BaseModel):
    id_short: str
    shell_id: str
    data: dict

class RawSubmodel(BaseModel):
    id_short: str
    submodel_id: str
    semantic_id: str
    data: dict

class RawResourceModel(BaseModel):
    shell: RawShell
    submodels: dict[str, RawSubmodel]

#====================================
#=== For Parsing Communication ======
#====================================

class MQTTSuffixes(BaseModel):
    command_suffix: str
    state_suffix: str
    job_result_suffix: str
    info_request_suffix: str
    resource_acknowledgement_suffix: str
    controller_acknowledgement_suffix: str
    inventory_level_suffix: str | None = None
    occupancy_suffix: str | None = None
    cargo_suffix: str | None = None

class MQTTConfig(BaseModel):
    production_line_prefix: str | None = None
    broker_id: str | None = None
    broker_port: int | None = None
    suffixes: MQTTSuffixes

#====================================
#====== For Parsing Skills ==========
#====================================

class SkillTriggerModel(BaseModel):
    triggers: list[str]

class CapabilityLinkModel(BaseModel):
    capability_submodel_id: str
    capability_type_id: str

class SkillModel(BaseModel):
    name: str
    capability: CapabilityLinkModel
    triggers: list[str]
    actors: list[str]

class SkillsCollectionModel(BaseModel):
    skills: dict[str, SkillModel]

#====================================
#====== For Parsing Capability ======
#====================================

class CapabilityParameter(BaseModel):
    name: str
    parameter_type: str

class PropertyParameter(CapabilityParameter):
    value: str| bool | int | float | None = None
    unit: str | None = None

class RangeParameter(CapabilityParameter):
    min_value: int | float | None = None
    max_value: int | float | None = None
    unit: str | None = None

class MultiLanguageParameter(CapabilityParameter):
    values: dict[str, str]

class CollectionParameter(CapabilityParameter):
    parameters: dict[str, CapabilityParameter]

class ProcessTransformationModel(BaseModel):
    name: str
    input_types: list[str]
    output_types: list[str]

class CapabilityModel(BaseModel):
    name: str
    capability_category: str | None = None
    capability_type: str
    parameters: dict[str, CapabilityParameter]
    process_transformations: dict[str, ProcessTransformationModel]
    supported_components: list[str]
    allowed_materials: list[str]

#====================================
#====== For Parsing Inventory =======
#====================================

class InventorySlot(BaseModel):
    component_id: str | None = None
    reserved: bool = False


class InventoryData(BaseModel):
    inventory_size: int
    supported_components: list[str]
    accessible_actors: list[str]
    storage: dict[str, InventorySlot]


class InventoryModel(BaseModel):
    inventories: dict[str, InventoryData]