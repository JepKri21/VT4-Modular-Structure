from aas_reader import *
from order_manager import *
from process_planner import ProcessPlanner
from resource_manager import ResourceManager
from scheduler import Scheduler


def build_station_skill_map():

    assets = get_shells()

    stations = {}

    for asset in assets:

        asset_id = asset["id"]

        submodels = get_submodels(asset_id)

        parsed = {}

        for sm in submodels:

            parsed[sm["idShort"]] = parse_submodel_elements(
                sm.get("submodelElements", [])
            )

        skills = extract_skills(parsed)

        if skills:
            stations[asset_id] = skills

    return stations


def main():

    print("Starting Line Controller")

    stations = build_station_skill_map()

    print("\nStations:")
    for s in stations:
        print(s)

    # create order
    order = ProductionOrder(
        "Order_1",
        "Bottom_Cover",
        3,
        "08:00"
    )

    products = generate_products(order)

    planner = ProcessPlanner(stations)

    rm = ResourceManager(stations)

    scheduler = Scheduler(rm)

    full_schedule = []

    for product in products:

        operations = planner.generate_process_plan(product)

        schedule = scheduler.schedule_product(product, operations)

        full_schedule.extend(schedule)


    print("\nProduction Schedule\n")

    for s in full_schedule:

        print(
            s["product"],
            s["operation"],
            s["station"],
            s["start"],
            "→",
            s["end"]
        )


if __name__ == "__main__":
    main()