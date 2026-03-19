import json 
from typing import List

class Orders:
    def __init__(self, order_messages: List):
        self.orders = {}
        self._read_orders(order_messages)
                
    def _read_orders(self, orders):
        for order in orders:
            order_name = order["order_id"]
            self.orders[order_name] = order


    def _parse_process(self, process_node):
        result = []

        for element_name, element_node in process_node.children.items():

            if element_name == "Process_Constraints":
                result.append({
                    "Process_Constraints": [child.value for child in element_node.children.values()]
                })

            elif element_name == "Required_Components":
                result.append({
                    "Required_Components": [child.value for child in element_node.children.values()]
                })

            elif element_name == "Parameters":
                params = []
                for child in element_node.children.values():
                    params.append({child.id_short: child.value})
                result.append({"Parameters": params})

        return result

    def _extract_bill_of_processes(self, bill_of_processes):
        processes = {}

        processes = {}

        for proc_name, proc_node in bill_of_processes.children.items():

            processes[proc_name] = self._parse_process(proc_node)

        return processes


    def build_order_dict(self, order, Products):

        order_id = order["order_id"]
        shell_instances = order["shell_instances"]

        result = {order_id: []}

        for name, shell_url in shell_instances.items():

            #uuid = shell_url.split("/")[-1]

            product = Products[shell_url]

            submodel = product["Bill_Of_Processes"]

            processes = self._extract_bill_of_processes(submodel)

            process_list = []
            for p_name, p_data in processes.items():
                process_list.append({p_name: p_data})

            result[order_id].append({
                shell_url: process_list
            })

        return result
    
    # Funktion får: Dictionary af alle products, en specific order_id
        # Den skal finde shell instances fra order_id
        # Den skal finde final_product ud fra final_product_type og definere resten som sub_assemblies (ud fra order)
        # Den skal kigge på final product Bill_Of_Processes og lav et dictionary
        # Kommer til at ligne TEST.json - Components kommer til at blive erstattet af specifikke component med dens properties, og assemblies bliver erstattet med den givne instance.

    # Funktion kommer til at se på Resource Capabilities, og Producktets Bill_Of_Processes, og ser på hvilke stationer der kan udføre processen.


# 1: Hent alle shells og fordel dem i Resources og Products?

# 2: Hent Ordre:
    #Ordre indeholder shells for Final product og subassemblies, dem skal vi holde styr på
    #Indeholder configuration for final product.





# 3: Hent BoP
    # Find processer
    # Constraints
    # Generér Sekvenser for BoP baseret på constraints, men også på Item_Capacity så vi ved om vi skal retrieve og transport det.
    # {"Segment1: [Process1, Process2, .....]", "Segment2: [Process3, Process4,....], Segment3: [Segment1, Segment2, Process5, .....] "}
        # Der vil altid være en endelig process hvor man så siger at final product er færdig. 
        # Men det betyder at parallele sekvenser skal mødes på et tidspunkt.


#print(f"Current order: {current_orders.orders}")

#print(f"Example Order 1 {current_orders.orders['ORD-001']}")


#final_product_type = order["final_product_type"]
#final_product_shell = order["shell_instances"][final_product_type]
#print("ORDER \n")
#print(final_product_shell)
