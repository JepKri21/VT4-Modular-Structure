import json 
from pathlib import Path
from typing import List


class Orders:
    def __init__(self, order_messages: List):
        self.orders = {}
        self._read_orders(order_messages)
                
    def _read_orders(self, orders):
        for order in orders:
            order_name = order["order_id"]
            self.orders[order_name] = order



    
    # Funktion får: Dictionary af alle products, en specific order_id
        # Den skal finde shell instances fra order_id
        # Den skal finde final_product ud fra final_product_type og definere resten som sub_assemblies (ud fra order)
        # Den skal kigge på final product Bill_Of_Processes og lav et dictionary
        # Kommer til at ligne TEST.json - Components kommer til at blive erstattet af specifikke component med dens properties, og assemblies bliver erstattet med den givne instance.

    # Funktion kommer til at se på Resource Capabilities, og Producktets Bill_Of_Processes, og ser på hvilke stationer der kan udføre processen.


# 1: Hent alle shells og fordel dem i Resources og Products?

# 2: Hent Ordre:
    #Ordre indeholder Final product og subassemblies, dem skal vi holde styr på


# 3: Hent BoP
    # Find processer
    # Constraints
    # Generér Sekvenser for BoP baseret på constraints, men også på Item_Capacity så vi ved om vi skal retrieve og transport det.
    # {"Segment1: [Process1, Process2, .....]", "Segment2: [Process3, Process4,....], Segment3: [Segment1, Segment2, Process5, .....] "}
        # Der vil altid være en endelig process hvor man så siger at final product er færdig. 
        # Men det betyder at parallele sekvenser skal mødes på et tidspunkt.

# 3: Sammenlign Product BoP og Resource Skills
    # Hvis BoP og Skill matcher: 
        # ✅ Du kan komme i sving ka' du

        #🤖



BASE_DIR = Path(__file__).resolve().parent
example_order1 = BASE_DIR / "example_order1.json"
example_order2 = BASE_DIR / "example_order2.json"
example_order3 = BASE_DIR / "example_order3.json"



with open(example_order1) as f:
    example_order1 = json.load(f)

with open(example_order2) as f:
    example_order2 = json.load(f)

with open(example_order3) as f:
    example_order3 = json.load(f)

all_orders = [example_order1, example_order2,example_order3]

current_orders = Orders(all_orders)

#print(f"Current order: {current_orders.orders}")

print(f"Example Order 1 {current_orders.orders['ORD-001']}")

#final_product_type = order["final_product_type"]
#final_product_shell = order["shell_instances"][final_product_type]
#print("ORDER \n")
#print(final_product_shell)
