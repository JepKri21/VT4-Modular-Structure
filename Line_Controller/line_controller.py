from AAS_Reader.resource_reader import AASNode, AAS, AASShellReader 


# 1: Hent alle shells og fordel dem i Resources og Products

# 2: Hent Ordre:
    #Ordre indeholder Final product og subassemblies
    # Hent BoP
    # Constraints
    # Generér Sekvenser for BoP
    # {"Parallel_Process1: [process1, process2, .....]", "Parallel_Process2: [process3, process4,....] "}

# 3: Sammenlign Product BoP og Resource Skills
    # Hvis BoP og Skill matcher: 
        # ✅ Du kan komme i sving ka' du

        #🤖

AAS_SERVER = "http://localhost:8081"
Reader = AASShellReader(AAS_SERVER)
All_Assets, Resources, Products = Reader.return_correlated_assets()
print(f"===============================================================================================================\n")
print(Resources)
print(f"===============================================================================================================\n")
print(Products)
print(f"===============================================================================================================\n")
print(Resources["Drill_Station_Asset"].Communication.UNS_Communication.Broker_Address())
print(Resources["Drill_Station_Asset"].Skills.Agents.KUKA_Manipulator.Drilling.Parameters.DrillDepth.range)
