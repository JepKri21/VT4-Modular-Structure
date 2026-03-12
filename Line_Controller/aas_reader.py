import requests
import json
import urllib.parse
from typing import Dict, List, Any

AAS_SERVER = "http://localhost:8081"

def encode_id(aas_id: str) -> str:
    """URL encode an AAS ID for use in API paths"""
    return urllib.parse.quote(aas_id, safe='')

def get_shells() -> List[Dict[str, Any]]:
    """Get all shells from the AAS server"""
    url = f"{AAS_SERVER}/shells"
    response = requests.get(url)
    if response.ok:
        return response.json().get("result", [])
    return []

def get_all_submodels() -> List[Dict[str, Any]]:
    """Get all submodels from the AAS server"""
    url = f"{AAS_SERVER}/submodels"
    response = requests.get(url)
    if response.ok:
        return response.json().get("result", [])
    return []

def extract_property_value(element: Dict[str, Any]) -> Any:
    """Extract value from a Property element"""
    if element.get("modelType") == "Property":
        return element.get("value")
    elif element.get("modelType") == "Range":
        return {
            "min": element.get("min"),
            "max": element.get("max")
        }
    elif element.get("modelType") == "SubmodelElementCollection":
        return extract_collection_values(element.get("value", []))
    elif element.get("modelType") == "SubmodelElementList":
        return extract_list_values(element.get("value", []))
    return None

def extract_collection_values(elements: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract values from SubmodelElementCollection"""
    result = {}
    for element in elements:
        id_short = element.get("idShort")
        if id_short:
            result[id_short] = extract_property_value(element)
    return result

def extract_list_values(elements: List[Dict[str, Any]]) -> List[Any]:
    """Extract values from SubmodelElementList"""
    result = []
    for element in elements:
        if element.get("modelType") == "SubmodelElementCollection":
            result.append(extract_collection_values(element.get("value", [])))
        else:
            value = extract_property_value(element)
            if value is not None:
                result.append(value)
    return result

def extract_skills_from_submodel(skills_submodel: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract skills from a Skills submodel.
    Structure: Agents → [Agent] → [Operations] → Operation
    
    Returns:
    {
        "agent_name": {
            "operation_name": {
                "Estimated_Duration": float,
                "Parameters": {...}
            }
        }
    }
    """
    skills = {}
    elements = skills_submodel.get("submodelElements", [])
    
    # Find the Agents list
    agents_list = None
    for element in elements:
        if element.get("idShort") == "Agents":
            agents_list = element
            break
    
    if not agents_list:
        return skills
    
    # Iterate through agents
    agents = agents_list.get("value", [])
    for agent in agents:
        agent_name = agent.get("idShort")
        if not agent_name:
            continue
        
        skills[agent_name] = {}
        operations = agent.get("value", [])
        
        # Iterate through operations within this agent
        for operation in operations:
            operation_name = operation.get("idShort")
            if not operation_name:
                continue
            
            operation_data = {}
            operation_elements = operation.get("value", [])
            
            # Extract Estimated_Duration and Parameters from operation
            for elem in operation_elements:
                elem_id_short = elem.get("idShort")
                if elem_id_short == "Estimated_Duration":
                    try:
                        operation_data["Estimated_Duration"] = float(elem.get("value", 0))
                    except (ValueError, TypeError):
                        operation_data["Estimated_Duration"] = 0
                elif elem_id_short == "Parameters":
                    operation_data["Parameters"] = extract_collection_values(elem.get("value", []))
            
            skills[agent_name][operation_name] = operation_data
    
    return skills

def extract_bom_from_submodel(bom_submodel: Dict[str, Any]) -> List[str]:
    """
    Extract Bill_Of_Materials component IDs from a BoM submodel.
    Structure: List_Of_Materials → [Component] → Component_Variant property
    
    Returns list of component IDs (product IDs)
    Normalizes IDs by appending /001 if not present (to match server storage)
    """
    components = []
    elements = bom_submodel.get("submodelElements", [])
    
    # Find the List_Of_Materials list
    list_of_materials = None
    for element in elements:
        if element.get("idShort") == "List_Of_Materials":
            list_of_materials = element
            break
    
    if not list_of_materials:
        return components
    
    # Iterate through components
    materials = list_of_materials.get("value", [])
    for material in materials:
        # Each material is a SubmodelElementCollection with Component_Variant property
        props = material.get("value", [])
        for prop in props:
            if prop.get("idShort") == "Component_Variant":
                component_id = prop.get("value")
                if component_id:
                    # Normalize: add /001 if not present (server stores with /001)
                    if not component_id.endswith("/001"):
                        component_id = component_id + "/001"
                    components.append(component_id)
                break
    
    return components

def extract_processes_from_submodel(bop_submodel: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract processes from a Bill_Of_Processes submodel.
    Structure: List_Of_Processes → [Process] → Process_Id, Parameters
    
    Returns:
    [
        {
            "Process_Id": "Drilling_1",
            "Process_Type": "Drilling",  # from idShort
            "Parameters": {...}
        }
    ]
    """
    processes = []
    elements = bop_submodel.get("submodelElements", [])
    
    # Find the List_Of_Processes list
    list_of_processes = None
    for element in elements:
        if element.get("idShort") == "List_Of_Processes":
            list_of_processes = element
            break
    
    if not list_of_processes:
        return processes
    
    # Iterate through processes
    process_elements = list_of_processes.get("value", [])
    for process in process_elements:
        process_type = process.get("idShort")
        if not process_type:
            continue
        
        process_data = {"Process_Type": process_type}
        process_values = process.get("value", [])
        
        # Extract Process_Id and Parameters
        for elem in process_values:
            elem_id_short = elem.get("idShort")
            if elem_id_short == "Process_Id":
                process_data["Process_Id"] = elem.get("value")
            elif elem_id_short == "Parameters":
                process_data["Parameters"] = extract_collection_values(elem.get("value", []))
        
        processes.append(process_data)
    
    return processes

def read_aas() -> Dict[str, Any]:
    """
    Read all shells and submodels from AAS server and extract relevant data.
    
    Returns:
    {
        "stations": {
            "station_id": {
                "idShort": "Station Name",
                "skills": {
                    "agent_name": {
                        "operation_name": {
                            "Estimated_Duration": float,
                            "Parameters": {...}
                        }
                    }
                }
            }
        },
        "products": {
            "product_id": {
                "idShort": "Product Name",
                "processes": [
                    {
                        "Process_Id": "Drilling_1",
                        "Process_Type": "Drilling",
                        "Parameters": {...}
                    }
                ]
            }
        }
    }
    """
    shells = get_shells()
    submodels = get_all_submodels()
    
    # Create lookup dict for submodels by ID
    submodels_by_id = {sm.get("id"): sm for sm in submodels}
    
    result = {
        "stations": {},
        "products": {}
    }
    
    for shell in shells:
        shell_id = shell.get("id")
        asset_id = shell.get("assetInformation", {}).get("globalAssetId", "")
        id_short = shell.get("idShort")
        is_resource = "/Resource/" in asset_id
        is_product = "/Product/" in asset_id
        
        if not (is_resource or is_product):
            continue
        
        shell_data = {
            "id": shell_id,
            "idShort": id_short
        }
        
        # Process submodels for this shell
        submodel_refs = shell.get("submodels", [])
        for sm_ref in submodel_refs:
            sm_id = sm_ref.get("keys", [{}])[0].get("value")
            if not sm_id:
                continue
            
            sm = submodels_by_id.get(sm_id)
            if not sm:
                continue
            
            sm_id_short = sm.get("idShort", "")
            
            # Extract Skills from resource stations
            if is_resource and sm_id_short == "Skills":
                shell_data["skills"] = extract_skills_from_submodel(sm)
            
            # Extract Bill_Of_Processes from products
            if is_product and sm_id_short == "Bill_Of_Processes":
                shell_data["processes"] = extract_processes_from_submodel(sm)
            
            # Extract Bill_Of_Materials from products
            if is_product and sm_id_short == "Bill_Of_Materials":
                shell_data["components"] = extract_bom_from_submodel(sm)
        
        # Store in appropriate category
        if is_resource:
            result["stations"][shell_id] = shell_data
        elif is_product:
            result["products"][shell_id] = shell_data
    
    return result


if __name__ == "__main__":
    # Test the reader
    data = read_aas()
    
    print("=" * 60)
    print("STATIONS")
    print("=" * 60)
    for station_id, station_data in data["stations"].items():
        print(f"\n{station_data['idShort']} ({station_id})")
        if "skills" in station_data:
            for agent, operations in station_data["skills"].items():
                print(f"  Agent: {agent}")
                for op_name, op_data in operations.items():
                    duration = op_data.get("Estimated_Duration", "N/A")
                    print(f"    - {op_name}: {duration}s")
    
    print("\n" + "=" * 60)
    print("PRODUCTS")
    print("=" * 60)
    for product_id, product_data in data["products"].items():
        print(f"\n{product_data['idShort']} ({product_id})")
        if "processes" in product_data:
            for process in product_data["processes"]:
                print(f"  - {process.get('Process_Type')}: {process.get('Process_Id')}")