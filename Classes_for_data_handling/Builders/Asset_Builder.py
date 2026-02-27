from Assets.Resource_Asset import ResourceAsset
from Assets.Product_Asset import ProductAsset

from Submodels.Communication import parse_communication_submodel
from Submodels.Skills import parse_skills_submodel
from Submodels.Bill_Of_Processes import parse_bill_of_processes_submodel
from Submodels.Bill_Of_Materials import parse_bill_of_materials_submodel
from Submodels.Item_Capacity import parse_item_capacity_submodel
from Submodels.Location import parse_location_submodel
from Submodels.Properties import parse_properties_submodel


def build_asset_from_shell(shell_json: dict, client):
    shell_id = shell_json["id"]
    id_short = shell_json["idShort"]


    submodel_refs = shell_json.get("submodels", [])

    submodel_ids = [
        ref["keys"][0]["value"]
        for ref in submodel_refs
    ]

    # crude detection for now
    is_resource = any("Communication" in sid for sid in submodel_ids)

    if is_resource:
        asset = ResourceAsset(shell_id, id_short)
    else:
        asset = ProductAsset(shell_id, id_short)

    submodel_counter = 0

    for sub_id in submodel_ids:
        data = client.get_submodel(sub_id)
        if data:
            sm_name = data.get("idShort")
    
            if sm_name == "Communication":
                asset.communication = parse_communication_submodel(data)
                submodel_counter += 1
    
            elif sm_name == "Skills":
                asset.skills = parse_skills_submodel(data)
                submodel_counter += 1
    
            elif sm_name == "Bill_Of_Processes":
                asset.bill_of_processes = parse_bill_of_processes_submodel(data)
                submodel_counter += 1

            elif sm_name == "Location":
                asset.location = parse_location_submodel(data)
                submodel_counter += 1
    
            elif sm_name == "Bill_Of_Materials":
                asset.bill_of_materials = parse_bill_of_materials_submodel(data)
                submodel_counter += 1
    
            elif sm_name == "Item_Capacity":
                asset.item_capacity = parse_item_capacity_submodel(data)
                submodel_counter += 1

            elif sm_name == "Properties":
                asset.properties = parse_properties_submodel(data)
                submodel_counter += 1

    if submodel_counter > 0:
        return asset
    else:
        return False