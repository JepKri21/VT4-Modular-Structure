from aas_reader import *
from order_manager import *
from product_catalog import *

def parse_submodel_elements(elements):
    """
    Rekursivt parser alle submodelElements og nested collections/lists
    til et dictionary.
    """
    result = {}
    for el in elements:
        id_short = el.get("idShort")
        value = el.get("value")
        if isinstance(value, list):
            # rekursivt parse nested elements
            result[id_short] = parse_submodel_elements(value)
        else:
            result[id_short] = value
    return result

def main():
    print("Fetching Assets from AAS Server")

    assets = get_shells()

    stations = {}
    products = {}

    for asset in assets:
        # Hent submodels for asset
        asset_id = asset["id"]
        shell_submodels = get_submodels(asset_id)

        # --- DYNAMISK PARSING AF SUBMODELS ---
        parsed_submodels = {}
        for sm in shell_submodels:
            parsed_submodels[sm["idShort"]] = parse_submodel_elements(sm.get("submodelElements", []))

        # --- EKSTRAHER SKILLS OG PARAMETRE ---
        skills = extract_skills(parsed_submodels)
        if skills:
            stations[asset_id] = skills

        # --- EKSTRAHER PRODUKT DATA (BoP/BOM) ---
        bop, bom = extract_product_data(parsed_submodels)
        if bop:
            products[asset_id] = Product(asset_id, bop, bom)
        else:
            # fallback: hvis ingen BoP/BOM findes, brug AssetClassification eller dummy
            asset_class = parsed_submodels.get("AssetClassification", {})
            products[asset_id] = Product(
                asset_id,
                bop=["dummy_bop"],
                bom=["dummy_bom"]
            )

    print("\nStations discovered:")
    for s, skills in stations.items():
        print(s, "->", skills)

    print("\nProducts discovered:")
    for p, data in products.items():
        print(p)
        print("BoP:", data.bop)
        print("BoM:", data.bom)

    # --- OPRET TEST ORDRE ---
    if products:
        order = ProductionOrder(
            "Order_1",
            list(products.keys())[0],
            3,
            "08:00"
        )

        product_instances = generate_products(order)

        print("\nGenerated products:")
        for p in product_instances:
            print(p)
    else:
        print("\nNo products found, skipping order generation.")

if __name__ == "__main__":
    main()