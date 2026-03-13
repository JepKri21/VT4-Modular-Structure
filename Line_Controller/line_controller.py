from AAS_Reader.resource_reader import AASNode, AAS, AASShellReader 
import json 
from pathlib import Path

#VIGTIG: Hvis vi laver resources til at have sub-assemblies/modelnumre som inputs og outputs så ville det være muligt at give alle resource calls abitrære navne og stadig vide hvad vi får ud af at sende den command


# 1: Hent alle shells og fordel dem i Resources og Products?

# 2: Hent Ordre:
    #Ordre indeholder Final product og subassemblies, dem skal vi holde styr på
BASE_DIR = Path(__file__).resolve().parent
example_order = BASE_DIR / "example_order.json"
def read_orders(file=example_order):
    with open(file) as f:
        orders = json.load(f)
        return orders

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

orders = read_orders()
order = orders[0]

final_product_type = order["final_product_type"]
final_product_shell = order["shell_instances"][final_product_type]
print("ORDER \n")
print(final_product_shell)

# AAS_SERVER = "http://localhost:8081"
# Reader = AASShellReader(AAS_SERVER)
# All_Assets, Resources, Products = Reader.return_correlated_assets()
# print(f"===============================================================================================================\n")
# print(Resources)
# print(f"===============================================================================================================\n")
# print(Products)
# print(f"===============================================================================================================\n")
# print(Resources["Drill_Station_Asset"].Communication.UNS_Communication.Broker_Address())
# print(Resources["Drill_Station_Asset"].Skills.Agents.KUKA_Manipulator.Drilling.Parameters.DrillDepth.range)

