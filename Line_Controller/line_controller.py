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
    # AAS_SERVER = "http://192.168.38.200:8081"
    AAS_SERVER = "http://100.117.139.24:8081"
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

    #print(f"Printing Order 001: {order_001_BOP}")

    rm = ResourceManager(Resources)# SKAL IKKE UDKOMMENTERES

    # Check if a resource has the given skill, and can perform it on a specific component ✅
    
    #Now we know which resource can perform that skill, now we need to find which resoruce has that component in storage to see if we need to move it
    
    
    #print("======================================================================================")
    matches = rm.check_skill_and_component("Assemble", "Bottom_Cover")# SKAL IKKE UDKOMMENTERES
    # if not matches:
    #     print("No resources found")

    # for resource in matches:
    #     print(matches)

    #print("======================================================================================")
    resource_inventories = rm.return_component_inventory() # SKAL IKKE UDKOMMENTERES
    #print(f"Resource Inventories: {resource_inventories}")
    
    # print("======================================================================================")
    #path = rm.find_resource_connection_points("https://aausmartlab.com/Assets/Resource/MADE/Bottom_Cover_Storage/6cac8616-a8ee-4877-b82a-3e677c6f18ac", "https://aausmartlab.com/Assets/Resource/MADE/Drill_Station/03fa4e62-d70f-4803-92ce-f8456370ac98", "https://aausmartlab.com/Assets/Product/Component/AAU/Bottom_Cover") # SKAL IKKE UDKOMMENTERES
    # print(path)
    # print("======================================================================================")

    phone_starting_process = [{'product': 'https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max/e739eb46-b993-4bed-a46d-6ac6793db1cb', 'process': 'Assemble_1', 'required_external_components': ["https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB-Fuse", 'https://aausmartlab.com/Assets/Product/Component/AAU/Top_Cover']}]

    starting_point = rm.find_lowest_starting_processes(order_001_BOP)
    #print(f"STARTING PROCESS: {starting_point}")
    ordered_task_list = rm.build_ordered_task_list(starting_point, order_001_BOP)
    #print(f"ORDERED TASK LIST: {ordered_task_list}")

    complete_execution_plan = rm.build_complete_execution_plan(ordered_task_list,resource_inventories)
    print(f"COMPLETE EXECUTION PLAN: {complete_execution_plan}")
    
"""
    {'ORD-001': [{'https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB/f0ab9bcf-e7e7-4418-9fb0-cdf25d290d22': [{'Assemble_1': [{'Process_Constraints': ['Drilling_1']}, {'Required_Components': [{'PCB_1': 'https://aausmartlab.com/Assets/Product/Component/AAU/PCB'}, {'Bottom_Cover_1': 'https://aausmartlab.com/Assets/Product/Component/AAU/Bottom_Cover'}]}, {'Parameters': [{'Selected_Operation': 'Assemble'}, {'inputs': ['PCB_1', 'Bottom_Cover_1']}, {'outputs': ['https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB']}]}]}, {'Drilling_1': [{'Process_Constraints': []}, {'Required_Components': [{'Bottom_Cover_1': 'https://aausmartlab.com/Assets/Product/Component/AAU/Bottom_Cover'}]}, {'Parameters': [{'Selected_Operation': 'Drilling'}, {'Drill_Size': '3'}, {'Drill_Depth': '20'}, {'inputs': ['Bottom_Cover_1']}, {'outputs': ['Bottom_Cover_1']}]}]}]}, {'https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB-Fuse/edff53e0-8150-430a-90b0-1553d888591b': [{'Assemble_1': [{'Process_Constraints': []}, {'Required_Components': [{'Bottom_Cover-PCB_1': 'https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB'}, {'Fuse_1': 'https://aausmartlab.com/Assets/Product/Component/AAU/Fuse'}]}, {'Parameters': [{'Selected_Operation': 'Assemble'}, {'inputs': ['Bottom_Cover-PCB_1', 'Fuse_1']}, {'outputs': ['https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB-Fuse']}]}]}]}, {'https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max/e739eb46-b993-4bed-a46d-6ac6793db1cb': [{'Assemble_1': [{'Process_Constraints': []}, {'Required_Components': [{'Bottom_Cover-PCB-Fuse_1': 'https://aausmartlab.com/Assets/Product/Sub_Assembly/AAU/Bottom_Cover-PCB-Fuse'}, {'Top_Cover_1': 'https://aausmartlab.com/Assets/Product/Component/AAU/Top_Cover'}]}, {'Parameters': [{'Selected_Operation': 'Assemble'}, {'inputs': ['Bottom_Cover-PCB-Fuse_1', 'Top_Cover_1']}, {'outputs': ['https://aausmartlab.com/Assets/Product/Final_Product/Telefon/Telefon_Pro_Max']}]}]}]}]}
"""

