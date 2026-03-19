from AAS_Reader.aas_reader import AASShellReader 
from Order_Reader.order_reader import Orders
from Resource_Manager.resource_manager import ResourceManager
import json 
import os


base_dir = os.path.dirname(__file__)

example_order1 = os.path.join(base_dir, "Order_Reader", "example_order1.json")
example_order2 = os.path.join(base_dir, "Order_Reader", "example_order2.json")
example_order3 = os.path.join(base_dir, "Order_Reader", "example_order3.json")

with open(example_order1) as f:
    example_order1 = json.load(f)

with open(example_order2) as f:
    example_order2 = json.load(f)

with open(example_order3) as f:
    example_order3 = json.load(f)

all_orders = [example_order1, example_order2,example_order3]







if __name__ == "__main__":
    AAS_SERVER = "http://192.168.38.200:8081"
    Reader = AASShellReader(AAS_SERVER)
    current_orders = Orders(all_orders)

    All_Assets, Resources, Products = Reader.return_assets()


    #print(f"===============================================================================================================\n")
    #print(Resources)
    #print(f"===============================================================================================================\n")
    #print(Products)
    #print(f"===============================================================================================================\n")

    #These has to be the actual ids, can no longer just be the idShort (as many products have the same idShort)
    #print(Resources["Drill_Station_Asset"].Communication.UNS_Communication.Broker_Address())
    #print(Resources["Drill_Station_Asset"].Skills.Agents.KUKA_Manipulator.Drilling.Parameters.DrillDepth.range)


    #print(Products["https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB/f0ab9bcf-e7e7-4418-9fb0-cdf25d290d22"])

    order_001_BOP = current_orders.build_order_dict(current_orders.orders['ORD-001'],Products=Products)

    rm = ResourceManager(Resources)

    # Check if a resource has the given skill, and can perform it on a specific component ✅
    matches = rm.check_skill_and_component("Assemble", "Bottom_Cover")
    #Now we know which resource can perform that skill, now we need to find which resoruce has that component in storage to see if we need to move it
    
    resource_inventories = rm.return_component_inventory()
    
    print("=======================================================================================")
    print("Matches:\n")

    if not matches:
        print("No resources found")

    for resource in matches:
        print(matches)

    print("======================================================================================")
    print(f"Resource Inventories: {resource_inventories}")

    print("======================================================================================")

    path = rm.est_resource_connection_points("https://aausmartlab.com/Assets/Resource/MADE/Bottom_Cover_Storage/6cac8616-a8ee-4877-b82a-3e677c6f18ac", "https://aausmartlab.com/Assets/Resource/MADE/Drill_Station/03fa4e62-d70f-4803-92ce-f8456370ac98", "https://aausmartlab.com/Assets/Product/Component/AAU/Bottom_Cover")
    
    print("======================================================================================")
    print(path)
    print("======================================================================================")

