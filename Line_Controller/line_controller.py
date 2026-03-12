from AAS_Reader.resource_reader import AASNode, AAS, AASShellReader 


# 1: Hent alle shells og fordel dem i Resources og Products

# 2: Hent Ordre:
    #Ordre indeholder Final product og subassemblies, dem skal vi holde styr på

# 3: Hent BoP
    # Find processer
    # Constraints
    # Generér Sekvenser for BoP baseret på constraints, men også på Item_Capacity så vi ved om vi skal retrieve og transport det.
    # {"Sequence1: [Process1, Process2, .....]", "Senquence2: [Process3, Process4,...., Sequence1] "}
        # Der vil altid være en endelig process hvor man så siger at final product er færdig. 
        # Men det betyder at parallele sekvenser skal mødes på et tidspunkt.

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
